# Local resource profile — 3 November 2026

Task P1 baseline: memory and time of startup imports, native PDF extraction and
the offline visual render on the development PC. No inference, Telegram message,
network request, restart or configuration change. This is a measurement, not a
fix; P2 picks an improvement from it.

## How it was measured

```powershell
.venv-win/Scripts/python.exe -m src.commands.profile_resources --output tests/test_output/resource-profile-20261103/report.json --repeat 5 --pdf data/study/sources/b4a081248864de48638444aec3a678250d63e10d77b0d824160c77017bccdf39.pdf
```

Each run is a fresh Python process with a minimal environment (no `.env`
secrets). On Windows the real interpreter joins a kill-on-close Job Object
before any work, so peaks include its worker descendants. (The venv
`python.exe` is only a ~4 MiB launcher; the first draft measured it by mistake,
and a unit test now guards against that.)

- **Job commit peak**: highest combined committed memory of the probe and all
  its workers. Exact, kernel-tracked.
- **Largest process commit**: the biggest single process in that tree.
- **Python working set peak**: physical RAM of the probe interpreter only.

Commit is not the same as physical RAM; the working set is physical but covers
only the Python process. The PowerShell PNG worker's working set is not
measured separately.

Host: Windows 11 10.0.26300, Intel family 6 model 165, 12 logical CPUs, 16 GiB
installed, Python 3.12.6. Free RAM before runs: 1,691–1,780 MiB. Source
commit `7464e32` plus the uncommitted profiling command. PDF: arXiv
2005.11401v4 (SHA256 `23e3249e…f21233`, the reviewed RAG fixture), 19 pages,
51 blocks.

## Results (median of runs 2–5; 0 failed runs)

| Probe | Time in probe | Wall | Job commit peak | Largest process | Python working set |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bare interpreter | 0.00 s | 0.15 s | 11.3 MiB | 11.3 MiB | 18.0 MiB |
| Bot + study imports | 2.07 s | 2.39 s | 79.2 MiB | 79.2 MiB | 96.9 MiB |
| API (`src.main`) import | 2.66 s | 3.06 s | 110.9 MiB | 110.9 MiB | 128.7 MiB |
| PDF extraction (worker) | 0.82 s | 1.01 s | 57.1 MiB | 33.5 MiB | 44.4 MiB |
| Visual SVG + 2 PNG | 1.47 s | 1.65 s | 105.9 MiB | 80.4 MiB | 35.2 MiB |

First runs were at most 0.55 s slower (API import: 3.21 s) and within
0.5 MiB of these. Disk cache was already warm from earlier runs, so the first run
is **not** a true cold start after reboot.

## What this shows

- The API import is the largest Python footprint (~129 MiB working set);
  the bot plus study imports load 1,468 modules in about 2 s.
- In the visual render, the PowerShell PNG worker is the largest process
  (~80 MiB commit), more than the Python renderer itself (~35 MiB working set).
- PDF extraction's caller and parser worker together peak at 57 MiB commit;
  neither process alone exceeds 33.5 MiB.
- All measured peaks are far below the 600 MiB free-RAM gates. The real risk
  on this PC is other applications: free RAM was only ~1.7 GiB of 16 GiB.

Not measured: live Telegram/API serving, model calls, Deep's isolated
environment, Docker services, a true post-reboot cold start, or other hardware.
Raw per-run data is in the ignored `tests/test_output/resource-profile-20261103/`.
