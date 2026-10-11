# Performance review and optimisations

Goal: find CPU waste in each stack's hot path and fix it **without breaking the lab's rules** (same SQL, 20 DB connections or fewer, no cache, byte-exact responses, framework still in the loop). Every change below was checked against the 38-check API contract and, where it touched request handling, the 29-check auth contract. Every kept change was measured **interleaved** against the previous code (see "How it was measured").

Baseline is run `2026-10-11_1244`; the optimisation measurements use PK lookup and range list at 100 VUs, 30 s, 3 alternating rounds per variant on the same machine (app 2 vCPU, PostgreSQL 2 vCPU).

## Kept

| Stack | Change | PK lookup | Range list (50 rows) |
| --- | --- | --- | --- |
| **NestJS** | Return `timestamptz` as text (`types.setTypeParser(1184, v => v)`) and format the string, instead of letting `pg` build a `Date` for every row and then re-serializing it | 22.6k → 22.2k req/s (-2%, noise) | 8.6k → **12.6k req/s (+46%)**, p95 13.9 → 11.2 ms |
| **Laravel Octane** | Hot path uses PDO directly (`App\Support\Pg`) with **one prepared statement per SQL text, kept for the life of the worker**, instead of the `DB` facade that prepares and discards a statement on every request. Framework providers trimmed to the ones the API needs (plus Translation and View, which Octane's reset listeners touch). `PDOException` is mapped to 422 for FK/CHECK violations | 3.5k → **4.1k req/s (+15%)** | 2.7k → **3.4k req/s (+26%)** |

Why they work: Nest's gain is concentrated on lists because parsing a timestamp per row is the dominant per-row cost (50 per list, 1 per PK lookup). Octane's gain comes from skipping a parse/plan step per request, which the other persistent-connection stacks (pgx, asyncpg, SQLx, JDBC) already did.

## Tried and rejected

| Stack | Change | Result | Decision |
| --- | --- | --- | --- |
| **FastAPI** | Parse `scope["query_string"]` directly instead of building Starlette `QueryParams` | PK +1.5%, range -2.5% (noise) | Reverted: no measurable gain, more code |
| **Go** | Hand-written JSON appender for `reading` and the list response (byte-identical to `encoding/json`, verified by test) | PK -4.6%, range -3.1% | Reverted: slower in practice (a 4 KiB buffer allocation per request outweighed the saved reflection) |
| **Laravel (PHP-FPM)** | Same PDO helper and provider trim | +1% to +6% in a sequential comparison that was not interleaved | Reverted: not proven, and statements cannot be reused across FPM requests anyway |
| **Laravel Octane** | `opcache.jit=tracing` (64 MB buffer) | +0% PK, -1% range, +0% mixed | Not adopted |
| **Laravel Octane** | Response compression check | Swoole does not compress these responses (checked with `Accept-Encoding: gzip, deflate, br` on a 5.8 KB body) | Nothing to fix |
| **Spring Boot (JVM)** | Garbage collector: G1 vs Parallel vs Serial (3 reps each) | see below | Keep G1 |

### Spring Boot GC experiment

Median of 3 runs, 2 vCPU, `-XX:MaxRAMPercentage=65`:

| Workload | G1 (default) | Parallel | Serial |
| --- | --- | --- | --- |
| PK lookup | **27,128** req/s, p99 49.9 ms, 570 MiB | 25,163, p99 46.4 ms, 819 MiB | 20,818, p99 54.1 ms, 432 MiB |
| Range list | **19,456**, p99 60.0 ms, 799 MiB | 16,851, p99 62.3 ms, 1,040 MiB | 9,915, p99 73.7 ms, 438 MiB |
| Mixed | **12,922**, p99 72.3 ms, 799 MiB | 11,904, p99 71.6 ms, 1,316 MiB | 10,882, p99 67.0 ms, 444 MiB |

G1 is fastest. **Serial costs 23% on PK lookups and 49% on range lists**, which is direct evidence for why the GraalVM native image (Serial GC only in the community build) trails the JVM on reads. Serial does use about 40% less memory. Parallel is worse than G1 and uses more memory.

## Reviewed, no safe change found

- **Go and Rust**: already at the CPU quota with the smallest memory footprint (27 MiB and 8 MiB); the remaining cost is HTTP and driver code.
- **Spring Boot Native**: the missing pieces are G1 and profile-guided optimisation, which need Oracle GraalVM. Not tried here.
- **Laravel (PHP-FPM)**: about 1.3 ms of CPU per request is the Laravel kernel booting per request. Without Octane or a preloaded kernel this is the floor.
- **Octane**: still CPU-bound at the 2-vCPU quota (every request runs the Laravel kernel, router and response pipeline). `Octane::route()` would skip the kernel entirely, but that stops measuring Laravel, so it was not used.

## How it was measured (and a trap to avoid)

A first attempt compared old and new code **sequentially** (all old runs, then all new runs). That produced a wrong picture: Go and FastAPI looked 3% to 6% slower and NestJS PK 12% slower, simply because this laptop slows down over a long session. The same code measured 20 minutes apart differed by up to 8%.

The final comparison alternates variants in rounds (old, new, old, new, old, new for each stack) and compares medians, so drift hits both equally:

- Octane: old 3,528 / 2,732 vs new 4,055 / 3,441 (PK / range), every round agreed.
- NestJS range: old 8.6k vs new 12.6k, every round agreed.
- Go, FastAPI and the NestJS PK differences stayed inside the run-to-run spread, so they were not counted as gains or losses.

Rule of thumb for this lab: do not trust a code-change comparison unless the variants alternate and the rounds agree.

## Other fixes made during the review

- `scripts/lib.sh`: `db_rows` is retried. A one-off failed row-count query left an empty field in `cells.tsv`, and the report generator then crashed (`ValueError: invalid literal for int() with base 10: ''`), taking down the combined report.
- `scripts/reporting/bench.py`: a blank field in `cells.tsv` is read as 0 instead of aborting the whole report.
- `infra/compose.yaml`: `SPRING_JAVA_OPTS` can override the JVM flags (used for the GC experiment).
