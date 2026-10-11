# Laravel Octane backend

Same Laravel 12 app as `apps/laravel` (same routes, SQL, validation, error contract, JWT middleware), but served by **Laravel Octane on Swoole** instead of nginx + PHP-FPM. The framework boots once per worker and stays in memory, so the per-request boot cost that dominates the FPM variant disappears.

- **Server.** `php artisan octane:start --server=swoole`, no nginx. `OCTANE_WORKERS` (default 4, set in `infra/compose.yaml`) Swoole workers, `--max-requests=100000` recycling, `--log-level=error`. Swoole is built with PECL in the Dockerfile; `procps` is needed because `octane:start` shells out to `pgrep`.
- **Connection model.** Each worker keeps one PDO connection for its whole life (no `ATTR_PERSISTENT` needed), so PostgreSQL sees at most `OCTANE_WORKERS` sessions, within the 20-connection budget. Workers are blocking (no coroutine hooks). 4 beat 2 and 8 in a quick check on 2 vCPU (8 workers pushed p95 to ~80 ms through CFS throttling); tune with `OCTANE_WORKERS`.
- **Same as the FPM variant.** Routes at the root without the web group, default global middleware removed, no `SET` statements on connect, `config:cache` / `route:cache` at container start, raw SQL via `DB`, non-root user.
- **Octane safety.** No request state is stored in statics (`Sql::$batch` only memoises SQL text). `QUERY_STRING` is read from the server bag, which Octane fills per request, so duplicate query parameters are still rejected.
- **Verified.** Contract smoke test 38/38 and JWT auth test 29/29 + 38/38.

Run: `docker compose -f infra/compose.yaml --profile octane up -d --build app-octane`
Benchmark: included in the default `STACKS` of every script (`STACKS=octane scripts/run-benchmark.sh` to run it alone).
