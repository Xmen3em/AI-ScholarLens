import json
import os
import subprocess
import sys

import pytest
from src.commands import profile_resources
from src.commands.profile_resources import ROOT, main, measure, summarize

windows_only = pytest.mark.skipif(os.name != "nt", reason="Job Object accounting is Windows-specific")


def test_summary_separates_the_first_run_from_later_runs_and_skips_failures():
    runs = [{"seconds": 3.0, "peak_job_commit_mib": 90.0}, {"error": "probe_timeout"},
            {"seconds": 1.0, "peak_job_commit_mib": 70.0}, {"seconds": 2.0, "peak_job_commit_mib": 80.0}]
    assert summarize(runs) == {"first": {"seconds": 3.0, "peak_job_commit_mib": 90.0},
                               "later_median": {"seconds": 1.5, "peak_job_commit_mib": 75.0}, "failed_runs": 1}


def test_an_existing_report_is_never_overwritten(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text("keep", encoding="utf-8")
    assert main(["--output", str(report), "--probe", "interpreter", "--repeat", "1"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "output_exists"}
    assert report.read_text(encoding="utf-8") == "keep"


def test_pdf_extraction_requires_a_local_pdf(tmp_path, capsys):
    assert main(["--output", str(tmp_path / "report.json"), "--probe", "extract_pdf", "--repeat", "1"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "pdf_required"}
    assert not (tmp_path / "report.json").exists()


def test_report_records_host_runs_and_zero_inference(tmp_path, capsys):
    report = tmp_path / "nested" / "report.json"
    assert main(["--output", str(report), "--probe", "interpreter", "--repeat", "2"]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert (data["inference_calls"], data["network_requests"], data["repeat"]) == (0, 0, 2)
    assert data["host"]["logical_cpus"] and data["host"]["installed_ram_mib"] > 0
    probe = data["probes"]["interpreter"]
    assert len(probe["runs"]) == 2 and probe["failed_runs"] == 0
    assert probe["first"]["wall_seconds"] > 0 and probe["later_median"]["wall_seconds"] > 0


@windows_only
def test_the_real_interpreter_is_measured_not_the_venv_launcher():
    result = measure("interpreter", None)
    assert "error" not in result
    # A venv launcher alone stays near 4 MiB; the interpreter it starts is larger.
    assert result["peak_working_set_mib"] > 8
    assert result["peak_job_commit_mib"] >= result["peak_process_commit_mib"] > 5


@windows_only
def test_job_peak_includes_worker_descendants():
    windows = profile_resources._Windows()
    job, name = windows.create_job()
    script = ("import subprocess, sys\n"
              "from src.commands.profile_resources import _Windows\n"
              f"_Windows().join({name!r})\n"
              "subprocess.run([sys.executable, '-c', 'b = bytearray(96 * 1048576); b[::4096] = b\"x\" * len(b[::4096])'], check=True)\n")
    try:
        subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, timeout=60)
        peaks = windows.job_peaks(job)
    finally:
        windows.kernel.CloseHandle(job)
    assert peaks["peak_process_commit_mib"] >= 96
    assert peaks["peak_job_commit_mib"] >= peaks["peak_process_commit_mib"]


def test_a_slow_probe_times_out_without_a_partial_measurement(monkeypatch):
    monkeypatch.setattr(profile_resources, "CHILD_TIMEOUT_SECONDS", 0.01)
    result = measure("import_bot", None)
    assert result["error"] == "probe_timeout"
    assert "peak_job_commit_mib" not in result and "seconds" not in result
