"""Measure local startup, PDF extraction and visual render memory. No inference or network.

Each probe runs in a fresh child process. On Windows the child joins a named
Job Object before any work, so the peak covers its worker descendants (PDF
parser, PNG worker); elsewhere the child reports its own and its descendants'
maximum RSS.
"""

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBES = ("interpreter", "import_bot", "import_api", "extract_pdf", "render_visual")
NUMERIC = ("seconds", "wall_seconds", "peak_job_commit_mib", "peak_process_commit_mib", "peak_working_set_mib", "peak_rss_mib")
CHILD_TIMEOUT_SECONDS = 120
MIB = 1048576


def _run_probe(name: str, pdf: Path | None) -> dict:
    if name == "interpreter":
        return {}
    if name == "import_bot":
        import src.services.study.service  # noqa: F401
        import src.services.telegram_bot  # noqa: F401
        return {"modules": len(sys.modules)}
    if name == "import_api":
        import src.main  # noqa: F401
        return {"modules": len(sys.modules)}
    if name == "extract_pdf":
        if pdf is None:
            raise ValueError("pdf_required")
        # The same isolated parser subprocess the study service uses.
        from src.services.study.content import _worker

        raw = _worker(pdf, "extract", timeout=90)
        return {"pages": raw["page_count"], "blocks": len(raw["blocks"])}
    if name == "render_visual":
        from src.services.study.visual_learning.catalog import load_curated_method
        from src.services.study.visual_learning.renderer import render_png, render_svg
        from src.services.study.visual_learning.validation import default_spec

        catalog = load_curated_method()
        spec = default_spec(catalog)
        detail: dict = {"svg_bytes": 0, "png_phases": []}
        for phase in ("inference", "training"):
            detail["svg_bytes"] += len(render_svg(spec, catalog, phase=phase).encode("utf-8"))
            if render_png(spec, catalog, phase=phase) is not None:
                detail["png_phases"].append(phase)
        return detail
    raise ValueError("unknown_probe")


class _Windows:
    """Job Object and process-counter calls; only constructed on Windows."""

    def __init__(self):
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("user_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                        ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6), ("process_limit", ctypes.c_size_t),
                        ("job_limit", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak_ws", ctypes.c_size_t),
                        *[(name, ctypes.c_size_t) for name in ("ws", "peak_paged", "paged", "peak_nonpaged", "nonpaged",
                                                                 "pagefile", "peak_pagefile")]]

        self.Extended, self.Counters = Extended, Counters
        kernel = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for function in ("CreateJobObjectW", "OpenJobObjectW", "GetCurrentProcess"):
            getattr(kernel, function).restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                     ctypes.c_void_p]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    def create_job(self) -> tuple[int, str]:
        name = f"Local\\ScholarLensProfile-{uuid.uuid4().hex}"
        handle = self.kernel.CreateJobObjectW(None, name)
        if not handle:
            raise OSError("job_create_failed")
        info = self.Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.kernel.CloseHandle(handle)
            raise OSError("job_configure_failed")
        return handle, name

    def join(self, name: str) -> None:
        job = self.kernel.OpenJobObjectW(0x0001, False, name)  # JOB_OBJECT_ASSIGN_PROCESS
        try:
            if not job or not self.kernel.AssignProcessToJobObject(job, self.kernel.GetCurrentProcess()):
                raise OSError("job_join_failed")
        finally:
            if job:
                self.kernel.CloseHandle(job)

    def job_peaks(self, handle: int) -> dict:
        info = self.Extended()
        if not self.kernel.QueryInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            raise OSError("job_query_failed")
        return {"peak_job_commit_mib": round(info.peak_job / MIB, 1),
                "peak_process_commit_mib": round(info.peak_process / MIB, 1)}

    def own_peak_working_set_mib(self) -> float | None:
        counters = self.Counters()
        counters.cb = ctypes.sizeof(counters)
        if not self.kernel.K32GetProcessMemoryInfo(self.kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.peak_ws / MIB, 1)


def _child(name: str, pdf: Path | None, job_name: str | None) -> int:
    # Wait for the parent, then join its job before any work. On Windows the venv
    # python.exe is only a launcher; this process is the real interpreter.
    sys.stdin.readline()
    windows = _Windows() if os.name == "nt" else None
    result: dict = {}
    try:
        if windows is not None and job_name:
            windows.join(job_name)
        started = time.perf_counter()
        detail = _run_probe(name, pdf)
        result = {"seconds": round(time.perf_counter() - started, 4), "detail": detail}
    except Exception as exc:
        result = {"error": str(exc) if str(exc) in {"job_join_failed", "pdf_required"} else type(exc).__name__}
    if windows is not None:
        result["peak_working_set_mib"] = windows.own_peak_working_set_mib()
    elif sys.platform != "win32":
        import resource

        # ru_maxrss is KiB on Linux.
        own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        descendants = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        result["peak_rss_mib"] = round(max(own, descendants) / 1024, 1)
    print(json.dumps(result), flush=True)
    return 0


def _free_memory() -> float | None:
    from src.resources import free_memory_mib

    try:
        return round(free_memory_mib(), 1)
    except OSError:
        return None


def measure(name: str, pdf: Path | None) -> dict:
    # Minimal environment: no secrets or tracing; no probe needs PATH or network.
    env = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    command = [sys.executable, "-m", "src.commands.profile_resources", "--child", name]
    if pdf is not None:
        command += ["--pdf", str(pdf.resolve())]
    windows = _Windows() if os.name == "nt" else None
    job = 0
    if windows is not None:
        job, job_name = windows.create_job()
        command += ["--job-name", job_name]
    free_before = _free_memory()
    started = time.perf_counter()
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            output, _ = process.communicate(b"go\n", timeout=CHILD_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            if windows is not None:
                windows.kernel.TerminateJobObject(job, 1)  # The real interpreter and workers, not only the launcher.
            process.kill()
            process.wait()
            result: dict = {"error": "probe_timeout"}
        else:
            try:
                result = json.loads(output)
                if type(result) is not dict:
                    raise ValueError
            except ValueError:
                result = {"error": "probe_output_invalid"}
            if process.returncode:
                result.setdefault("error", "probe_exit_nonzero")
            result["wall_seconds"] = round(time.perf_counter() - started, 4)
            if windows is not None:
                result.update(windows.job_peaks(job))
    finally:
        if windows is not None:
            windows.kernel.CloseHandle(job)  # Kill-on-close ends any leftover worker descendants.
    result["free_ram_mib_before"] = free_before
    return result


def summarize(runs: list[dict]) -> dict:
    def pick(rows: list[dict]) -> dict:
        values = {}
        for key in NUMERIC:
            numbers = [row[key] for row in rows if isinstance(row.get(key), int | float)]
            if numbers:
                values[key] = round(statistics.median(numbers), 4)
        return values

    good = [run for run in runs if "error" not in run]
    return {"first": pick(good[:1]), "later_median": pick(good[1:]), "failed_runs": len(runs) - len(good)}


def _host() -> dict:
    total = None
    if sys.platform == "win32":
        kib = ctypes.c_ulonglong()
        if ctypes.WinDLL("kernel32").GetPhysicallyInstalledSystemMemory(ctypes.byref(kib)):
            total = round(kib.value / 1024, 1)
    else:
        total = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / MIB, 1)
    return {"os": platform.platform(), "machine": platform.machine(), "processor": platform.processor() or None,
            "logical_cpus": os.cpu_count(), "installed_ram_mib": total, "python": platform.python_version()}


def _commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout.strip() or None) if result.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure local resource envelopes without inference or network.")
    parser.add_argument("--output", type=Path, help="New JSON report path; an existing file is never overwritten.")
    parser.add_argument("--probe", action="append", choices=PROBES, help="Repeatable; defaults to every probe with its inputs.")
    parser.add_argument("--repeat", type=int, default=3, choices=range(1, 11), metavar="1-10")
    parser.add_argument("--pdf", type=Path, help="Local PDF for extract_pdf; it is read, never uploaded.")
    parser.add_argument("--child", choices=PROBES, help=argparse.SUPPRESS)
    parser.add_argument("--job-name", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        return _child(args.child, args.pdf, args.job_name)
    if args.output is None:
        parser.error("--output is required")
    if args.output.exists() or args.output.is_symlink():
        print(json.dumps({"error": "output_exists"}))
        return 1
    probes = args.probe or [name for name in PROBES if name != "extract_pdf" or args.pdf]
    if "extract_pdf" in probes and (args.pdf is None or not args.pdf.is_file()):
        print(json.dumps({"error": "pdf_required"}))
        return 1
    report: dict = {"schema_version": 1, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "source_commit": _commit(), "host": _host(), "inference_calls": 0, "network_requests": 0,
                    "repeat": args.repeat, "probes": {}}
    if args.pdf is not None:
        import hashlib

        report["pdf"] = {"sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(), "bytes": args.pdf.stat().st_size}
    for name in probes:
        runs = [measure(name, args.pdf) for _ in range(args.repeat)]
        report["probes"][name] = {"runs": runs, **summarize(runs)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(args.output.resolve()),
                      "probes": {name: value["later_median"] or value["first"] for name, value in report["probes"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
