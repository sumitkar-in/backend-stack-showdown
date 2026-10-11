# Results

Generated output, git-ignored except this file. Open **`index.html`** for a list of every run with links to its report.

```
results/
  index.html                          catalogue of every run, rebuilt after every run
  report.html                         everything combined: scorecard, benchmark, ramps, auth (python3 scripts/report.py all)
  benchmarks/<date>_<time>_<label>/   100-VU runs        -> report.html
  ramps/<date>_<time>_<label>/        ramp tests         -> ramp-report.html
  auth/<date>_<time>_<label>/         auth tests         -> summary.md
```

Inside a run folder: `report.html` (or `ramp-report.html`), `env.txt` (host, Docker VM, settings), `cells.tsv` (one row per measured run), `run.log`, and the raw data in `k6/` (summaries and logs), `stats/` (docker stats samples), `postgres/` (statement stats), `contract/` (smoke test output) and `logs/` (build and app logs).

Old flat-layout results can be moved into this structure with `python3 scripts/organize-results.py`.
Don't publish performance rankings without complete metadata and repeated runs.
