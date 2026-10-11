# Laravel (PHP-FPM) vs Laravel Octane (Swoole)

Same Laravel 12 application, same routes, same SQL, same validation and error contract. Only the way PHP serves it differs. Source: run `2026-10-11_1244` (local Docker, Apple Silicon, 100 constant VUs, 10 s warm-up, 30 s measured, 1 repetition, app 2 vCPU / 4 GiB, PostgreSQL 2 vCPU / 2 GiB; all eight stacks in one run, Asia/Kolkata contract). **Indicative only**: one local run, no dispersion estimate.

## 1. What differs

| | Laravel (`apps/laravel`) | Laravel Octane (`apps/laravel-octane`) |
| --- | --- | --- |
| Server | nginx (2 workers) + PHP-FPM | `octane:start --server=swoole`, no nginx |
| Workers | 20 static FPM children | 4 Swoole workers (`OCTANE_WORKERS`) |
| Framework boot | on **every request** | **once per worker**, kept in memory |
| DB connection | `PDO::ATTR_PERSISTENT`, 1 per FPM child (up to 20) | 1 PDO connection per worker for its lifetime (up to 4) |
| Prepared statements | server-side, but re-parsed each request (PDO cannot reuse across requests) | same PDO behaviour; the connection is long-lived |
| Process model | request-isolated; state cannot leak | shared worker state; code must not keep request data in statics |
| Image | `php:8.3-fpm-bookworm` + nginx | `php:8.3-cli-bookworm` + Swoole (PECL) + `procps` |
| Container `TZ` | `Asia/Kolkata` | `Asia/Kolkata` |

Identical in both: routes at the root without the web group, default global middleware removed, no `SET` statements on connect, `config:cache` and `route:cache` at container start, opcache on with JIT off, raw SQL via the `DB` facade, JWT middleware, non-root user.

## 2. Throughput (successful req/s, higher is better)

| Workload | Laravel | Octane | Speed-up | Laravel limit | Octane limit |
| --- | ---: | ---: | ---: | --- | --- |
| Health (no DB) | 1,464 | 6,009 | 4.1x | app CPU | app CPU |
| PK lookup | 1,293 | 4,793 | 3.7x | app CPU | app CPU |
| Range list (50 rows) | 1,216 | 4,173 | 3.4x | app CPU | app CPU |
| Aggregate | 1,546 | 3,061 | 2.0x | app CPU | database CPU |
| Single insert | 1,317 | 4,610 | 3.5x | app CPU | app CPU |
| Batch insert (10) | 1,318 | 3,481 | 2.6x | app CPU | app CPU |
| Mixed | 1,249 | 3,896 | 3.1x | app CPU | app CPU |

PHP-FPM Laravel was bound by app CPU on every workload, including `/health`. Octane gains the most where the framework dominates (health 4.1x, PK lookup 3.7x) and the least where PostgreSQL is the limit (aggregate 2.0x): once the database saturates, the PHP side stops mattering. Octane's aggregate result (3,061 req/s) is also the highest of all eight stacks. That is most likely because it holds 4 DB sessions against 20 for the other stacks, and a saturated 2-vCPU PostgreSQL does less context switching with fewer sessions. It is a hint to test the connection count, not a PHP result.

## 3. Latency (ms, p50 / p95 / p99, lower is better)

| Workload | Laravel | Octane |
| --- | --- | --- |
| Health (no DB) | 90.8 / 106.5 / 110.8 | 7.5 / 64.9 / 71.2 |
| PK lookup | 93.0 / 107.5 / 114.8 | 13.0 / 53.2 / 59.8 |
| Range list (50 rows) | 95.3 / 106.3 / 115.6 | 15.6 / 55.0 / 60.2 |
| Aggregate | 87.4 / 97.6 / 100.6 | 28.2 / 44.2 / 48.0 |
| Single insert | 92.8 / 101.9 / 105.9 | 17.0 / 42.2 / 46.4 |
| Batch insert (10) | 92.7 / 101.8 / 105.2 | 25.4 / 41.9 / 45.2 |
| Mixed | 94.7 / 104.9 / 109.8 | 19.0 / 49.4 / 54.7 |

Median latency drops 3.1x to 12x. The tail improves much less (p95 about 1.6x to 2.4x better) because Octane's p95 sits far above its p50: four blocking workers compete for a 2-CPU CFS quota, and the container is throttled in bursts. With 100 closed-loop users, latency is mostly queueing, so it tracks throughput.

## 4. Resources (mixed workload)

| | Laravel | Octane |
| --- | ---: | ---: |
| App CPU (cores of 2) | 2.01 | 2.03 |
| Requests per CPU core | ~623 | ~1,921 |
| Peak memory | 75 MiB | 187 MiB |
| PostgreSQL CPU (cores of 2) | 0.43 | 0.78 |
| DB sessions used | up to 20 | up to 4 |

Both saturate the 2-CPU quota, so the real comparison is work per core: Octane serves about 3.1x more requests per core. It pays about 2.5x the memory, since every worker holds a booted framework and an opcache-warm copy of the app. Octane also drives PostgreSQL harder simply because it sends more queries per second.

## 5. Worker-count check (Octane)

A short check (PK lookup and mixed, 8 s measured) on the 2 vCPU container, before the full run:

| Workers | PK req/s | PK p95 (ms) | Mixed req/s | Mixed p95 (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 3,037 | 35.7 | 2,398 | 45.7 |
| 4 | 3,511 | 56.9 | 3,207 | 53.6 |
| 8 | 2,976 | 81.6 | 2,663 | 81.0 |

Four workers gave the best throughput, so that is the default. Two workers have the best tail but too little parallelism to hide database waits; eight add CFS throttling and context switching. These were very short runs, so treat the exact figures loosely.

## 6. Correctness and cost of switching

- Contract: 38/38 API checks and 29/29 JWT checks pass for Octane, as for Laravel. Zero failed requests in all measured runs.
- Octane safety: the app keeps no per-request data in statics (`Sql::$batch` only memoises SQL text), and `QUERY_STRING` is read from the server bag that Octane refills for each request, so duplicate query parameters are still rejected.
- Operational differences: Octane needs the Swoole extension and `procps` (`octane:start` shells out to `pgrep`); workers are recycled after `--max-requests` (default 100,000); a code change needs a worker reload because opcache never revalidates.
- Timezone: both containers, the Laravel application timezone and PostgreSQL run in `Asia/Kolkata`, and the API returns `+05:30` timestamps (`...000+05:30`), confirmed byte-for-byte against the database by the smoke test.

## 7. Takeaways

1. Keeping the framework booted removes most of the per-request cost: 2.0x to 4.1x more throughput and a much lower median, with no code changes beyond the server.
2. The gain shrinks as PostgreSQL becomes the bottleneck (aggregate: 2.0x). Fix slow queries before swapping servers.
3. Octane is still CPU-bound at 2 vCPU on `/health`: the Laravel kernel, router and middleware pipeline still run for every request (about 0.3 to 0.5 ms of CPU, against about 1.4 ms under FPM).
4. It remains well behind the other stacks on cheap routes (Go does about 40k PK lookups/s in the same run, 8x Octane).
5. The price is memory (about 2.5x) and the discipline of writing code that is safe to share between requests.

## 8. Limitations

One local machine with the load generator, database and app sharing it; 1 repetition and 30 s runs; closed-loop load only; stacks ran one after another in a fixed (not randomised) order; baseline tuning only (Octane with blocking workers and no coroutine hooks, no RoadRunner or FrankenPHP comparison). Swoole's coroutine mode with a pooled async driver would change the picture and is not measured here.

## 9. Reproduce

```bash
# Octane only, added to an existing run (comparable with its Laravel numbers)
RUN_ID=2026-10-11_1244 STACKS=octane scripts/run-benchmark.sh

# Both, fresh run
STACKS="laravel octane" scripts/run-benchmark.sh

# Change the Octane worker count
OCTANE_WORKERS=2 STACKS=octane scripts/run-benchmark.sh
```
