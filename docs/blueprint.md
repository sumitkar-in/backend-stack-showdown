# SensorPulse Benchmark Lab — Original Blueprint (design notes, kept for reference)

**Status:** Architecture and runnable PostgreSQL/k6/Compose starter configuration. The five backend implementations are **not included**; their `apps/*` folders contain implementation contracts. Docker app profiles will work once each service's Dockerfile and code are implemented.

**Goal:** compare Go/Gin, Java/Spring MVC, TypeScript/NestJS+Fastify, Python/FastAPI and Rust/Axum against the *same PostgreSQL database design*, initial **1,000 devices / 1,000,000 readings** and **100 constant k6 VUs**. No authentication, cache, queue, ORM, UI, or business-domain features.

## 1. Comparison methodology

- Measure a complete stack (framework + language runtime + database driver), **not pure language speed**.
- Fix baseline application container limit to **2 CPUs and 1 GiB**, PostgreSQL to **2 CPUs and 2 GiB**. Keep CPU architecture, platform, host, image digests, DB version and storage identical. Quotas cap utilization but do not isolate noisy neighbors: preferably use a dedicated Linux host and CPU pinning.
- Run **one app + one PostgreSQL instance at a time**; load-generator and telemetry should have separately provisioned resources, ideally on another physical/virtual host. For local learning, k6 on the same host is acceptable but results are non-publication-grade.
- Total effective DB connection budget **20** for all apps. Spring Hikari 20; Go pgxpool 20; Rust SQLx 20; NestJS two Node workers × pool 10; FastAPI two Uvicorn workers × asyncpg pool 10. Start with cold/min pool=0 where supported or consistently prewarm all 20 connections before measured runs. Record connection counts and queue wait.
- Use JSON serialization with identical keys and types, Asia/Kolkata (`+05:30`) millisecond timestamps, equivalent status/error semantics, no endpoint-specific caching and no API-layer compression.
- **No ORM in the primary comparisons.** Use raw parameterized SQL and, for batch, one parameterized `INSERT ... VALUES (...), ...` containing 10 readings per API call.
- HTTP/1.1, keep-alive enabled, no TLS/proxy during primary comparisons. Benchmark single host port 8080 over the same Docker bridge/network path.
- App health has **no DB query**. Log errors only; disable per-request access logs, development watchers, profilers and tracing during the timed runs.

## 2. Versions / runtime guidance

| Stack | Framework/server | Database access | Recommended runtime |
| --- | --- | --- | --- |
| Go | Gin, `net/http` | pgxpool | One process; `GOMAXPROCS=2`, pool max 20 |
| Java | Spring Boot MVC/Tomcat | JDBC + HikariCP | One JVM; Tomcat `maxThreads=200`, Hikari 20, 2 active processors, production build |
| TypeScript | NestJS Fastify adapter | `pg.Pool` | 2 Node cluster workers; each pool max 10; serve on port 8080 |
| Python | FastAPI/Uvicorn | asyncpg | `uvicorn app:app --host 0.0.0.0 --port 8080 --workers 2`, pool max 10 per process |
| Rust | Axum/Tokio | SQLx | Release binary, Tokio multithread runtime 2 worker threads, pool max 20 |

These are **recommended baseline configurations**, not universally optimal tunings. Publish a second, independently tuned comparison if desired. Pin exact dependency versions and Docker image digests once implementation begins; never upgrade midway through a benchmark matrix.

## 3. Canonical database

Schema: [`db/00-schema.sql`](db/00-schema.sql). One thousand deterministic devices and one million readings: [`db/01-seed.sql`](db/01-seed.sql). Indexed after loading: [`db/02-indexes.sql`](db/02-indexes.sql). `reading.id` is a database-generated BIGINT; `device_id` a foreign key; temperature stored as signed integer **centi-degrees Celsius**; humidity stored as integer **basis points (0–10000)**. Integers avoid inconsistent JSON floating-point rounding and are practical sensor units.

All measurements have `observed_at TIMESTAMPTZ(3)`, returned as Asia/Kolkata RFC3339 millisecond timestamps. The seed starts on **2026-01-01 at 00:00:00 +05:30 (Asia/Kolkata)**, increments one second for each reading and spans approximately **11.6 days**. Each of the 1,000 devices gets **1,000 readings**. One composite B-tree index handles device/range/ordering; the primary key index handles ID lookups. Avoid per-stack extra indexes.

Recommended critical SQL statements (identical logical shape across languages):

```sql
-- By ID
SELECT id, device_id, temperature_centi, humidity_bp, observed_at
FROM readings WHERE id = $1;

-- By device, time and page
SELECT id, device_id, temperature_centi, humidity_bp, observed_at
FROM readings
WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3
ORDER BY observed_at DESC, id DESC
LIMIT $4 OFFSET $5;

-- Aggregation (return integers, not DB-dependent average JSON formatting)
SELECT COUNT(*)::bigint AS count,
       COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi,
       COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp,
       MIN(temperature_centi) AS temperature_min_centi,
       MAX(temperature_centi) AS temperature_max_centi
FROM readings
WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3;

-- Single insert, returning the new ID and canonical payload
INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at)
VALUES ($1, $2, $3, $4)
RETURNING id, device_id, temperature_centi, humidity_bp, observed_at;
```

For batch INSERT, generate exactly 10 parameterized groups in **one INSERT statement** on the hot path; a single PostgreSQL statement is atomic, so separate `BEGIN/COMMIT` traffic is not needed. The API accepts 1–100 items; comparison workload uses 10.

## 4. Canonical HTTP API

The formal machine-readable contract is [`api/openapi.yaml`](api/openapi.yaml).

**Path order:** implement `/readings/stats` before `/readings/{id}` where framework routing needs it. All content type `application/json`. All JSON field names camelCase. Successful reads return 200; creates 201. `id` and `deviceId` are JSON numbers. 64-bit SQL aggregation values must be converted from driver-specific text/BigInt into safe JSON numbers for this known seed size. Do not bypass safety for arbitrary >2^53 inputs.

| Method | Path | Behavior | Result |
| --- | --- | --- | --- |
| GET | `/health` | Return immediately, no DB query | `{"status":"ok"}` |
| GET | `/readings/{id}` | Primary-key lookup | `Reading` or 404 |
| GET | `/readings?deviceId=17&from=...&to=...&limit=50&offset=0` | Device/time scan, descending timestamp/id | `{"items":[Reading...],"limit":50,"offset":0}` |
| GET | `/readings/stats?deviceId=17&from=...&to=...` | Count, sums, min/max across device/time | `Stats` |
| POST | `/readings` | Insert one reading | `Reading` including generated id |
| POST | `/readings/batch` | Atomically insert 1–100 readings | `{"inserted":n}` |

`Reading` example:

```json
{"id":100,"deviceId":17,"temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-06T12:34:56.000+05:30"}
```

Single create request (same fields excluding `id`):

```json
{"deviceId":17,"temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}
```

Batch request:

```json
{"readings":[
  {"deviceId":17,"temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"},
  {"deviceId":18,"temperatureCenti":2400,"humidityBp":5500,"observedAt":"2026-01-12T00:00:01.000+05:30"}
]}
```

Stats response:

```json
{"deviceId":17,"count":1000,"temperatureSumCenti":2650000,"humiditySumBp":6000000,"temperatureMinCenti":1800,"temperatureMaxCenti":3500}
```

(The sample stats numbers are illustrative; the actual expected values must come from seed queries.) For zero matching rows return `count=0`, `temperatureSumCenti=0`, `humiditySumBp=0`, and null for both minimum and maximum.

### Validation and error contract

- `deviceId`: positive integer; known 1–1000 for valid benchmark traffic; non-existent FK on insert maps to 422.
- `id`: positive integer; nonexistent reading returns 404.
- `temperatureCenti`: integer between -5000 and +10000.
- `humidityBp`: integer between 0 and 10000.
- `observedAt`: RFC3339 with timezone, millisecond precision at most; convert to Asia/Kolkata, serialize precisely 3 fractional digits and `+05:30`.
- Range: `from` and `to` required RFC3339 strings, **from < to**, inclusive lower/exclusive upper; `deviceId` required.
- Pagination: `limit` 1–100, default 50; `offset` 0–1000, default 0.
- Batch: 1–100 readings; all valid and committed, or no rows inserted.
- Bad/malformed JSON -> `400`; invalid/missing fields, unknown device FK or invalid query -> `422`; missing reading -> `404`. All errors JSON `{ "error": "bad_request|validation_error|not_found" }`. Framework-default exception outputs must be normalized.

## 5. Repo layout

```text
sensorpulse-benchmark-blueprint/
  README.md
  .env.example
  db/
    00-schema.sql
    01-seed.sql
    02-indexes.sql
    verify.sql
  infra/compose.yaml
  api/openapi.yaml      # machine-readable six-route API contract
  k6/bench.js
  docs/
    contract-tests.md
    runner.md
    stack-implementation.md
    results-schema.json
  apps/
    go/README.md         # implement app and Dockerfile here
    spring/README.md
    nest/README.md
    fastapi/README.md
    rust/README.md
  results/
```

## 6. Running Docker and k6

1. Confirm `docker compose version` and Docker engine are available; use Linux containers. Run `docker compose -f infra/compose.yaml up -d postgres` to start PostgreSQL and initialize the **empty** named volume. Init scripts run only on first DB initialization.
2. Validate with `docker compose -f infra/compose.yaml exec -T postgres psql -U bench -d sensorpulse -f /docker-entrypoint-initdb.d/verify.sql`.
3. Implement each backend in its folder with a multistage production Dockerfile. `docker compose -f infra/compose.yaml --profile go up -d --build app-go` starts Go; swap profile and service for others, and **stop the previous app first** since all share host port 8080.
4. Probe `curl -fsS http://localhost:8080/health` and run shared contract tests before load.
5. Run k6 with Docker Compose (from project root):

```bash
docker compose -f infra/compose.yaml --profile tools run --rm \
  -e BASE_URL=http://app-go:8080 \
  -e WORKLOAD=pk -e VUS=100 -e DURATION=2m \
  -e RUN_ID=go-pk-01 \
  k6 run /scripts/bench.js
```

The included k6 script supports `WORKLOAD=health|pk|range|stats|insert|batch|mixed`. Its `mixed` mode uses 50% PK, 30% range, 10% aggregate, 9% single writes, 1% 10-row batches. It emits `results/<RUN_ID>.json` with RPS, latency distribution and error/check metrics.

**Important:** this directory is a **blueprint/scaffold**: only PostgreSQL, its schema/seed, and the load script are implemented. Backend app profiles require your five applications and Dockerfiles. `grafana/k6:latest` in the sample Compose is a convenience while developing; pin by exact version/digest for actual published comparisons.

## 7. Measurement protocol

**Preflight:** check OS/CPU architecture, host idle load, swap activity, Docker quotas, DB pool availability, filesystem mode, indexes, exactly 1M rows, no errors, consistent result JSON, Linux DNS/network. Use one app at a time. Ensure 100 VUs do not saturate the k6 client itself. Set benchmark clock in UTC.

**Warm-up:** after bringing up an app, warm its JIT/runtime, routes, driver pools, statement plans and PostgreSQL cache for at least 30 seconds on a representative workload. Mark this period excluded from measured results.

**Measured test:** primary scenario is k6 `constant-vus` at 100 VUs for 120 seconds, with HTTP keep-alive enabled. Repeat each workload **5 independent times**, rotate stack order to mitigate systematic thermal/cache effects, and report **median and dispersion**. Keep per-run raw JSON.

**Reset discipline:** A pure read workload can start from an identical 1M snapshot and read-only warm-up. For INSERT/batch/mixed runs, **restore the same 1M baseline before every measured run**, otherwise data size and index depth drift differently as faster frameworks write more rows. Warm write workloads and then restore the baseline again before measurement; this also changes database cache conditions, so document and control a fixed cache-conditioning/read-primer procedure. Prefer prebuilt compressed `pg_dump -Fc` or a restored volume snapshot rather than running the seeder differently per language. Never count seed/restore activity in the timed period. Note that even within a time-based write test, the database grows faster for faster stacks; include a separate fixed-total-operations test for a cleaner DB-state comparison.

**Two complementary workload models:**

- `constant-vus` uses a **closed workload model**: 100 VUs each issue the next request when ready. This exposes maximal throughput for a fixed client population, but can conceal capacity under external fixed arrival demand.
- Run a **separate constant-arrival-rate sweep** at fixed offered RPS (for example 100, 300, 500, 1,000, 2,000, continuing while sustainable), sized with enough preallocated/max VUs so `dropped_iterations` stay zero; compare P95/P99 and error rate at the *same offered rate*. This phase can require >100 VUs; it must be labeled as a distinct test, not the 100-VU benchmark.

**Write-stable companion test:** use `shared-iterations` at 100 VUs with a fixed count such as 100,000 single-insert iterations; compare elapsed time, succeeded writes and total DB growth. Reset to 1M each repetition. This isolates a constant number of new rows per implementation.

## 8. Metrics and dashboard

**Per app stack/workload/run:** successful RPS, failed RPS, P50/P90/P95/P99, request duration histograms, k6 check failures, 4xx/5xx, connection errors and timeout rate, app CPU cores consumed, peak and mean RSS/container memory, CPU throttling and OOM counts, pool usage/waits, garbage collection where available, bytes served/request.

**PostgreSQL:** DB CPU/RSS/I/O, `pg_stat_statements` calls/mean/total/max query time, shared cache hits/misses, transaction commits/rollbacks, temp files, locks/waiting sessions, `pg_stat_activity` connection counts, table row count before and after, dead tuples, disk bytes written. Collect Pg stats separately from measured traffic; use a low-overhead monitor and reset counters at start. PostgreSQL extension's statistics collection itself introduces some overhead: keep identical across stacks and consider an instrumentation-off control run.

**Derived:** successful requests per CPU-second, P95 at a matched RPS, estimated successful writes/sec, KB response size, PostgreSQL query time share vs request latency, RSS at target RPS. Do not call the fastest raw RPS alone the best stack if it violates the latency/error SLO.

## 9. Fairness traps to avoid

- NestJS's default Express and NestJS+Fastify are distinct configurations. The primary specification explicitly uses **Fastify**; benchmark Express separately if desired.
- FastAPI/Uvicorn two workers and NestJS two Node cluster workers consume separate per-process DB pools. Do not accidentally allow 40 DB connections when the others get 20.
- JDBC synchronous, asyncpg asynchronous, pgxpool and SQLx differ materially; record them as part of the evaluated stack. Keep connection pool cap consistent even if async models differ.
- PostgreSQL TIMESTAMPTZ and JSON encoders may format dates and BIGINT differently. Contract tests require identical semantics and canonical JSON.
- Ensure all response bodies are actually consumed/returned. Returning only `{ok:true}` for a query that should return 50 rows is not an equal benchmark.
- Ensure all request payload fields are validated consistently. Database FK/check violations are not a substitute for full HTTP validation except where contract explicitly accepts the mapping.
- Stop app containers not under test; remove leftover listeners, automatic container healthcheck HTTP load, debug trace collectors, proxies and OS background jobs where practical.
- Seed no SQL index advantage for any language. Use identical SQL query shape (`EXPLAIN ANALYZE` preflight), consistent transaction boundaries, and same table/index statistics.
- Compare not just average latency: report tail latencies and errors. CPU quota hit, memory OOM and k6 source saturation are invalid benchmark runs or important qualifications.
- For Mac/Windows Docker Desktop, VM overhead, filesystem and CPU scheduling can alter results; use a native Linux machine for published rankings.

## 10. Implementation milestones and acceptance gates

**M1 — Database + exact contract.** Apply seed; assert device count=1000 and reading count=1,000,000; inspect index; define canonical request/response fixtures; generate shared contract test dataset. **Gate:** schema checks and 15–20 contract assertions pass.

**M2 — Reference Go version.** Implement all six APIs with Gin/pgxpool; ensure fixed SQL, pool=20, production Dockerfile and graceful shutdown. **Gate:** 0 contract divergence, 100-VU read test works.

**M3 — Other backends.** Implement Java/Spring MVC+JDBC, NestJS+Fastify+pg, Python/FastAPI+asyncpg, Rust/Axum+SQLx without changing semantics. **Gate:** same error handling and serialized bodies as Go.

**M4 — Deterministic k6 suite.** One workload per endpoint, mixed traffic; automated baseline restore before mutating workloads; record artifact metadata. **Gate:** identical test shape and starting DB population across all stacks.

**M5 — Monitoring.** Prometheus + Grafana + cAdvisor + PostgreSQL exporter (or equivalent low-overhead collectors), k6 summary JSON, per-run manifest. **Gate:** can attribute CPU and latency separately to client/app/database.

**M6 — Reliable matrix.** Five repetitions per cell and randomized stack order, first 100-VU closed-model results then open-model offered-load sweep and fixed-workload writes. **Gate:** reproducible report with medians, variance, tail latency, error rate, resources and limitations.

**M7 — Dashboard/report.** Filter by stack, workload, run and version; chart RPS, P95/P99, CPU/RSS, database timings, error counts. Include hardware, OS, CPU architecture, source commit, image digests, DB snapshot hash, k6 script hash, driver versions and all tunables.

## 11. Official documentation consulted

- [Docker Compose service resource limits](https://docs.docker.com/reference/compose-file/services/)
- [Docker Compose profiles](https://docs.docker.com/reference/compose-file/profiles/)
- [k6 constant VUs](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-vus/)
- [k6 constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [k6 custom summary](https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/)
- [PostgreSQL pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [NestJS Fastify adapter](https://docs.nestjs.com/techniques/performance)
- [FastAPI Uvicorn workers](https://fastapi.tiangolo.com/deployment/server-workers/)
