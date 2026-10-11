# scripts

## Why auth, benchmark and ramp are separate

They answer different questions and need different conditions, so they are separate scripts that `scripts/run.sh` chains:

| Test | Question it answers | Why it is its own run |
| --- | --- | --- |
| **auth** (`run-auth-test.sh`) | Is the JWT behaviour correct and identical in every stack? | A pass/fail *correctness* test, not a measurement. It starts each app with `AUTH_MODE=jwt`, runs the 29 auth checks plus the 38 API checks, then restarts with `AUTH_MODE=none`. Auth is off in the benchmarks, so mixing it in would change what they measure. |
| **bench** (`run-benchmark.sh`) | How fast is each stack under a fixed 100-VU load, per workload? | Closed model (users wait for replies), so the system sets the pace. It resets the database to the exact 1M-row baseline before every run, which is slow and must not be disturbed. |
| **ramp** (`run-ramp.sh`) | Where does each stack break, and what is the highest rate with p95 under the target? | Open model (fixed arrival rate that climbs in steps), so it overloads the app on purpose. Overload leaves the database and app in a different state, and a run takes about 4 min per stack, so it must not share a run with the steady benchmark. |
| **authcost** (`FULL=1`) | What does JWT verification cost? | The same workloads twice (auth off, then on) as an A/B pair, so it needs its own paired runs. |

Keeping them apart means a failing correctness check cannot hide inside throughput numbers, you can rerun only the slow or noisy part, and each stage writes its own report (`results/auth/`, `results/benchmarks/`, `results/ramps/`). `scripts/run.sh` runs them in order under one run id and refreshes the combined `results/report.html`; one stage failing does not stop the next, but the exit code is non-zero.

## Running tests: one, some, or everything

Stack keys: `nest spring go rust fastapi laravel octane graalvm`. Stage keys: `auth bench ramp authcost report`. All scripts read `STACKS` (space-separated; default is all eight).

| I want to run | Command |
| --- | --- |
| Everything, all stacks (auth + bench + ramp + report) | `scripts/run.sh` |
| Everything, selected stacks | `STACKS="go rust octane" scripts/run.sh` |
| One stage, all stacks | `scripts/run.sh bench` (or `auth`, `ramp`) |
| Some stages, selected stacks | `STACKS="go laravel" scripts/run.sh auth bench` |
| Everything plus the JWT-cost A/B | `FULL=1 scripts/run.sh` |
| Quick sanity check (about 2 min) | `QUICK=1 STACKS=go scripts/run.sh` |
| Only the benchmark, one stack | `STACKS=graalvm scripts/run-benchmark.sh` |
| Only some workloads | `STACKS="go rust" WORKLOADS="pk mixed" scripts/run-benchmark.sh` (workloads: `health pk range stats insert batch mixed`) |
| Longer, repeated benchmark | `DURATION=60s REPS=3 scripts/run-benchmark.sh` |
| Only the ramp, one stack | `STACKS=go scripts/run-ramp.sh` |
| Ramp with another target or steps | `P95_TARGET_MS=1 RATES="1000,2000,4000,8000" STACKS=go scripts/run-ramp.sh` |
| Only the JWT correctness tests | `scripts/run-auth-test.sh` or `STACKS="go rust" scripts/run-auth-test.sh` |
| Benchmark with JWT turned on | `AUTH_MODE=jwt LABEL=jwt scripts/run-benchmark.sh` |
| Add a stack to an earlier run | `RUN_ID=<existing run> STACKS=octane scripts/run-benchmark.sh` |
| Rebuild the reports only | `scripts/run.sh report` or `python3 scripts/report.py refresh` |

The 38-check API contract (`scripts/smoke.sh`) runs automatically for every stack inside `bench` and `auth`; a stack that fails it is reported as failed and not measured. `LABEL=name` appends a name to the run folders, and `RUN_ID=...` pins them.

## Files

| File | Purpose |
| --- | --- |
| `run.sh` | Orchestrator: chains the stages under one run id, then the combined report |
| `run-auth-test.sh` | JWT correctness on every stack (`smoke-auth.sh` + `smoke.sh`) |
| `run-benchmark.sh` | Closed-model 100-VU benchmark, 7 workloads per stack |
| `run-ramp.sh` | Open-model ramp: breaking point and p95 threshold |
| `smoke.sh`, `smoke-auth.sh` | The 38-check API contract and the 29-check auth contract |
| `lib.sh` | Shared helpers (compose, database reset, health, k6, cleanup trap) |
| `report.py`, `reporting/` | HTML report generation (`report.py refresh` rebuilds everything) |
| `pg/` | Baseline template, restore and row reset SQL |
| `jwt.py` | Mints test tokens |
| `organize-results.py` | Result folder housekeeping |
