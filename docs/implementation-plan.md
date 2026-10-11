# SensorPulse Docker Benchmark — Complete Implementation Plan

Scope: Go/Gin, Spring Boot MVC, NestJS+Fastify, FastAPI, Rust/Axum on one PostgreSQL 17 database, 1,000 devices / 1,000,000 readings, 100 constant k6 VUs.
This plan builds on `README.md`, `api/openapi.yaml`, `db/*`, `infra/compose.yaml`, `k6/bench.js`, `docs/*`. It does **not** repeat them; it fixes gaps, assigns work and defines gates.

---

## 0. Review of the existing scaffold — defects to fix before any app is written

| # | Where | Problem | Fix |
|---|-------|---------|-----|
| D1 | `compose.yaml` postgres healthcheck | `pg_isready -U bench` uses the unix socket. The entrypoint's temporary init server listens on the socket only, so health goes green **while the 1M seed is still loading**; apps then start against a half-seeded DB. | `pg_isready -h 127.0.0.1 -U bench -d sensorpulse` (TCP only opens after init finishes). |
| D2 | `compose.yaml` app-common | `mem_limit: 1g` without `memswap_limit` lets the container swap on hosts with swap, hiding memory pressure. | Add `memswap_limit: 1g`; same for postgres (`2g`). |
| D3 | `compose.yaml` | No `platform`, `cpuset`, `ulimits`, `pids_limit`, `shm_size`. k6 container has no CPU cap and competes with app/DB. | See §4. |
| D4 | `k6/bench.js` mixed mode | `slot = k % 100` and `deviceId = k % 1000 + 1` are correlated: list requests (slots 50–79) only ever hit devices with `(id-1) % 100 ∈ 50..79`, i.e. 30% of devices. Skewed cache/index locality. | Pick operation from a separate counter (§6). |
| D5 | `k6/bench.js` | Only `constant-vus`. README §7 also requires constant-arrival-rate sweep and shared-iterations write test. No response-body validation (README §9 "ensure bodies consumed" is not enforced). | Add `SCENARIO` env + sampled deep checks (§6). |
| D6 | README §1 | "min pool=0 where supported **or** prewarm" is ambiguous; pools growing under load add latency to some stacks only. | Rule: **min = max** pool on every stack, plus a post-start prewarm (§5.3). |
| D7 | `runner.md` restore | `pg_restore` into an already-populated DB duplicates/conflicts. Slow (rebuilds 1M rows + index each run, ×175). | Use a template database (§5.4). |
| D8 | `compose.yaml` k6 | `grafana/k6:latest`, `postgres:17` unpinned. | Pin digests in `.env` (§4.3). |
| D9 | Contract | JSON malformed → 400 but type errors → 422 needs a two-step parse; every framework collapses these by default (Pydantic/Jackson/serde all return one code). | Mandatory rule in §3.3. |

---

## 1. Work breakdown and order

```
P0  Scaffold repairs (D1–D9)                       half day
P1  Contract test suite + golden fixtures           1 day     <- before any app
P2  Go reference app + Dockerfile                   1 day     gate: 20/20 contract
P3  Rust, Spring, NestJS, FastAPI (parallelizable)  1 day each; gate: byte-identical bodies vs Go
P4  k6 v2 + orchestrator + collectors               1.5 days
P5  Smoke matrix (health, pk, insert x 1 rep)       0.5 day  gate: no errors, k6 CPU < 70% of its cap
P6  Full matrix 5 stacks x 7 workloads x 5 reps     ~7 h machine time (175 x ~2.5 min incl. restore/warmup)
P7  Open-model sweep + fixed-ops write test         ~3 h
P8  Report + dashboard                              1 day
```

Rule: P3 apps are only started after P2 passes; the contract suite is the single source of truth, not Go's behavior.

---

## 2. Repository additions

```
contract/
  run.sh                     # runs against BASE_URL, restores DB template before and after
  fixtures/*.json            # golden request/response pairs, derived by SQL from seed
  contract.test.js           # k6 or Node script, 20 assertions from docs/contract-tests.md + extras (§3.4)
scripts/
  restore-baseline.sh        # template-DB restore (§5.4)
  prime-cache.sh             # pg_prewarm + read primer (§5.5)
  collect-cgroup.sh          # 1 Hz cgroup sampler (§7)
  collect-pg.sh              # pg_stat_* before/after snapshots (§7)
  run-one.sh                 # one cell: stack x workload x rep
  run-matrix.sh              # randomized order, resumable
  manifest.sh                # builds results/<RUN_ID>.manifest.json (matches docs/results-schema.json)
  report.py                  # medians, IQR, charts -> results/report.html
infra/monitor.compose.yaml   # optional Prometheus/Grafana profile (not used in primary runs)
apps/<stack>/{Dockerfile,.dockerignore,src...,lockfile}
```

---

## 3. Identical API contract

### 3.1 Source of truth
`api/openapi.yaml` + README §4. Six routes, camelCase, `id`/`deviceId` as JSON numbers, timestamps `YYYY-MM-DDTHH:mm:ss.SSS+05:30`, errors `{"error":"bad_request|validation_error|not_found"}`.

### 3.2 Byte-level response rules (so body size and serialization work are equal)
- Compact JSON, **fixed key order**: `id, deviceId, temperatureCenti, humidityBp, observedAt`; stats: `deviceId, count, temperatureSumCenti, humiditySumBp, temperatureMinCenti, temperatureMaxCenti`; list: `items, limit, offset`.
- `Content-Type: application/json` (charset suffix allowed, but all five must match — pick `application/json`, verify in contract test).
- No `Content-Encoding`, no extra headers beyond framework defaults (`Date`, `Content-Length` or chunked — **require `Content-Length`**; no chunked responses. Contract test asserts it).
- Golden-file test compares **raw body bytes** to fixtures, not parsed JSON. This catches spacing, key order, `1e3`, `1000.0`, `+05:30` vs `+0530`.
- Unknown request fields: ignored (all five). Duplicate query params: first wins; not benchmarked, just tested to be 422 or first-wins uniformly (decide: 422).

### 3.3 Two-stage request handling (mandatory in every stack — fixes D9)
1. Read body bytes. Parse into a generic JSON value. Failure → **400 bad_request**. Also 400: empty body, non-object top-level, wrong Content-Type is *not* checked (k6 always sends JSON).
2. Validate parsed value against rules (types strict: `2375.0`, `"2375"`, `true`, `null` rejected for integer fields) → failure **422 validation_error**.
3. FK violation (SQLSTATE `23503`) → 422. CHECK violation (`23514`) is unreachable if step 2 is right; map to 422 anyway. Any other DB error → 500 `{"error":"internal"}` (not in OpenAPI, counted as a failure).
4. Path/query validation errors → 422. Unknown route → 404 `not_found`. Wrong method → 404 as well (decision; avoids 405 variance).
5. `observedAt`: must match `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,3})?(Z|[+-]\d\d:\d\d)$`; more than 3 fractional digits → 422. Convert to Asia/Kolkata (+05:30).
6. `from`/`to` same parser; `from < to` else 422.
7. Batch: validate **all** items before touching the DB; error index not reported.

### 3.4 Extra contract cases beyond the 20 in `docs/contract-tests.md`
21. Body byte-equality against golden for routes 2, 5, 8, 10.
22. `Content-Length` present, no `Transfer-Encoding`.
23. `observedAt` with offset `+05:30` → returned as `+05:30`; a `Z` input is converted.
24. `observedAt` with 4 fractional digits → 422.
25. Batch of 0 and 101 items → 422; batch of 100 → 201.
26. `temperatureCenti` −5001 / 10001, `humidityBp` −1 / 10001 → 422.
27. `/readings/stats` with `deviceId=0` → 422; unknown device 1001 on stats → 200 with count 0.
28. `/readings?...&limit=0` → 422.
29. Large body (>1 MiB) → 400 or 413 (decide 413 is out of contract → use 400); tests max body for 100 items (~12 KB) passes.
30. SIGTERM → process exits within 10 s with exit code 0.

---

## 4. Docker design

### 4.1 Resource limits (all stacks identical)

| Container | CPU | Memory | Swap | Extras |
|-----------|-----|--------|------|--------|
| app-* | `cpus: 2.0` | `mem_limit: 1g` | `memswap_limit: 1g` | `pids_limit: 1024`, `ulimits.nofile: 65536`, `init: true`, `stop_grace_period: 15s` |
| postgres | `cpus: 2.0` | `mem_limit: 2g` | `memswap_limit: 2g` | `shm_size: 256m`, `ulimits.nofile: 65536` |
| k6 | `cpus: 4.0` (Linux: cpuset) | `mem_limit: 2g` | same | Must stay < 70% of its cap; otherwise run invalid |

Linux dedicated host (published results): ≥ 12 physical cores. Pin with `cpuset`: DB 0–1, app 2–3, k6 4–7, collectors/OS 8+. SMT siblings must not be split across roles. Disable CPU frequency scaling (`performance` governor). macOS/Windows Docker Desktop: allowed for development only, labeled `grade: local`.

`cpus: 2.0` is a CFS quota (throttling), not 2 dedicated cores. Runtimes see **host** core count: therefore explicit runtime caps (§5).

### 4.2 Compose changes (patch to `infra/compose.yaml`)

```yaml
x-app-common: &app-common
  platform: ${PLATFORM:-linux/amd64}
  cpus: 2.0
  mem_limit: 1g
  memswap_limit: 1g
  pids_limit: 1024
  init: true
  stop_grace_period: 15s
  ulimits: { nofile: { soft: 65536, hard: 65536 } }
  # cpuset: "2,3"        # Linux publication runs only (set via override file)
  restart: "no"
  logging: { driver: json-file, options: { max-size: 10m, max-file: "2" } }

services:
  postgres:
    image: postgres@${POSTGRES_DIGEST}          # pinned
    platform: ${PLATFORM:-linux/amd64}
    memswap_limit: 2g
    shm_size: 256m
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -h 127.0.0.1 -U bench -d sensorpulse']
    command: >
      postgres -c shared_buffers=512MB -c effective_cache_size=1536MB
      -c max_connections=100 -c work_mem=4MB -c maintenance_work_mem=128MB
      -c max_wal_size=4GB -c checkpoint_timeout=15min
      -c synchronous_commit=on -c fsync=on
      -c shared_preload_libraries=pg_stat_statements,pg_prewarm
      -c pg_stat_statements.track=top -c track_io_timing=on
      -c autovacuum=on -c log_min_messages=error
```

Notes: keep durability on (`fsync`, `synchronous_commit`) — turning them off would inflate write results. Large `max_wal_size` + 15-min checkpoint avoids a checkpoint landing inside only some write runs; the restore script issues an explicit `CHECKPOINT` before each run. Data volume should be a bind mount on the host SSD/NVMe (not Docker Desktop's VM disk) for published runs; same device for every run.

Ports: remove `127.0.0.1:8080:8080` publishing from the load path. k6 reaches `http://app:8080` over the bridge. Publish only for contract tests/manual probes (via `compose.override.yaml`). Use one stable network alias `app` on every app service so `BASE_URL=http://app:8080` is identical across stacks.

Add an app healthcheck? **No** (README §1: no background HTTP load). The orchestrator polls `/health` itself.

### 4.3 Pinning (`.env`)
```
PLATFORM=linux/amd64
POSTGRES_DIGEST=sha256:...    # resolved once, committed
K6_DIGEST=sha256:...          # grafana/k6:<exact version>
GO_BASE_DIGEST=... RUST_BASE_DIGEST=... TEMURIN_DIGEST=... NODE_DIGEST=... PYTHON_DIGEST=...
```
Dockerfiles take `ARG BASE_DIGEST`. Build with `--no-cache` for the published matrix; record resulting image IDs.

---

## 5. Per-stack implementation spec

Common to all: listen `0.0.0.0:8080`; env `DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD DB_POOL_TOTAL`; pool **min = max**; **server-side prepared statements ON for the five fixed queries** (named/cached statements; the batch INSERT statement is a fixed 10-row shape, with a dynamic path for other sizes); no ORM; no access log; error-level logs only; no compression; SIGTERM → stop accepting, drain in-flight, close pool, exit 0; non-root user; read-only rootfs optional.

Statement-cache parity matters: asyncpg and pgx prepare automatically, SQLx caches, JDBC prepares after `prepareThreshold=5` (set `prepareThreshold=1`), `pg` (Node) only with `name:` on the query (set it).

### 5.1 Go — `apps/go`
- Go 1.23+, `gin` (release mode `GIN_MODE=release`, `gin.New()` + `Recovery` only), `pgx/v5` `pgxpool` (`MaxConns=MinConns=20`, default extended protocol + statement cache).
- Env `GOMAXPROCS=2` (also `GOMEMLIMIT=800MiB`). Build `CGO_ENABLED=0 go build -trimpath -ldflags="-s -w"`.
- Runtime image `gcr.io/distroless/static-debian12:nonroot`.
- Time: scan into `time.Time`, format with `t.In(ist).Format("2006-01-02T15:04:05.000-07:00")` with `ist = time.FixedZone("IST", 19800)`. JSON: hand-assemble with `strconv.AppendInt` into a pooled buffer **or** `encoding/json` on fixed structs — choose `encoding/json` structs (idiomatic; document).
- Body: `io.ReadAll` → `json.Unmarshal` into `any` (400) → manual validation (422). Gin's `ShouldBindJSON` is not used.

### 5.2 Rust — `apps/rust`
- Rust stable (pin), `axum 0.8`, `tokio` (`#[tokio::main(flavor="multi_thread", worker_threads=2)]`), `sqlx 0.8` (`runtime-tokio`, `postgres`, `time`), `PgPoolOptions::new().min_connections(20).max_connections(20)`, `sqlx::query` (runtime, not compile-time macros → no offline cache needed).
- `Cargo.toml`: `[profile.release] opt-level=3, lto="fat", codegen-units=1, panic="abort", strip=true`. No `target-cpu=native` (image must be portable; record flags in manifest).
- Handlers take `Bytes`; parse `serde_json::Value` → 400; validate → 422. Custom `Json` extractor rejections are not used. Fallback handler → 404 JSON.
- Build with cargo-chef layering for fast rebuilds; runtime `gcr.io/distroless/cc-debian12:nonroot`.
- Graceful shutdown via `axum::serve(...).with_graceful_shutdown(signal)`.

### 5.3 Spring — `apps/spring`
- Java 21 LTS, Spring Boot 3.x `spring-boot-starter-web` (Tomcat) + `spring-boot-starter-jdbc`, `NamedParameterJdbcTemplate`/`JdbcTemplate`, PostgreSQL JDBC with `?prepareThreshold=1&reWriteBatchedInserts=false`.
- `application.properties`: `server.tomcat.threads.max=200`, `server.tomcat.accept-count=100`, `server.tomcat.max-connections=8192`, `spring.datasource.hikari.minimum-idle=20`, `maximum-pool-size=20`, `logging.level.root=ERROR`, `spring.main.banner-mode=off`, `spring.jmx.enabled=false`, `spring.mvc.log-request-details=false`, `server.compression.enabled=false`, `spring.jackson.default-property-inclusion=always`. No actuator, no devtools, no Spring Security. `spring.threads.virtual.enabled=false` (record; run virtual threads as a *variant* later).
- JVM: `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -XX:MaxRAMPercentage=65` with the default G1 collector (production default), no `AlwaysPreTouch`, `-Xss512k`. Record flags. Native image / CDS / AppCDS excluded from baseline.
- Controllers take `@RequestBody byte[]`; `ObjectMapper.readTree` → 400; manual validation → 422. A `@RestControllerAdvice` normalizes `NoHandlerFoundException`, `MethodArgumentTypeMismatchException` etc.
- JVM warm-up: JIT needs more than 30 s; require **90 s warm-up for Spring** *or* a uniform 60 s for all stacks (recommended: uniform 60 s; stop-condition: p95 over the last 10 s within ±5% of the previous 10 s).
- Runtime image `eclipse-temurin:21-jre`; layered jar extraction.

### 5.4 NestJS — `apps/nest`
- Node 22 LTS, `@nestjs/core`, `@nestjs/platform-fastify`, `fastify` (pinned), `pg`. Controllers + one service. No `class-validator` pipes on the hot path (reflection overhead differs by version); use a hand-written validator shared by all routes, or `ajv` compiled once.
- `main.ts`: Node `cluster`; primary forks `APP_WORKERS=2`; each worker builds its own Nest app with `FastifyAdapter({ logger: false, bodyLimit: 1048576 })`, own `pg.Pool({ max: 10, min: 10 })`. On Linux cluster uses round-robin from primary (extra hop; accepted, documented). `NODE_ENV=production`, `UV_THREADPOOL_SIZE=4`, `--max-old-space-size=384`.
- `pg` type parsers: `types.setTypeParser(20, Number)` (int8 → number; safe for seed scale), timestamptz → keep `Date` and shift by 5h30m, `toISOString()`, then replace `Z` with `+05:30`. Queries use `{ name, text, values }` for server-side prepare.
- Fastify JSON parser replaced with a text/buffer parser (custom `addContentTypeParser('application/json', {parseAs:'buffer'}, ...)`) to implement the 400/422 split; `setErrorHandler` and `setNotFoundHandler` normalized.
- Compile TS with `tsc` (or SWC) to JS; run `node dist/main.js`. Final image `node:22-slim` with `npm ci --omit=dev`.

### 5.5 FastAPI — `apps/fastapi`

- Python 3.12, `fastapi`, `uvicorn[standard]` (uvloop + httptools), `asyncpg`, `orjson`, `pydantic` v2. Exact pins in `requirements.txt` with hashes (`pip-compile --generate-hashes`).
- Command:
  ```
  uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2 \
          --loop uvloop --http httptools --no-access-log --log-level error \
          --backlog 2048 --timeout-graceful-shutdown 10
  ```
- Lifespan: `asyncpg.create_pool(min_size=10, max_size=10, command_timeout=10, max_inactive_connection_lifetime=0)` per worker → 20 total. `DB_POOL_PER_WORKER=10` from env; startup asserts `DB_POOL_PER_WORKER * APP_WORKERS == DB_POOL_TOTAL`.
- Each route is `async def` with one `await pool.fetchrow/fetch(...)` — asyncpg's automatic prepared-statement cache is the parity mechanism. No sync DB calls, no thread offloading.
- Responses: `ORJSONResponse`/raw `Response(orjson.dumps(dict), media_type="application/json")`; **no `response_model`** (skips Pydantic re-validation; document as deviation: both sides are fixed-shape dicts built from DB rows). Build `observedAt` with `dt.astimezone(IST).isoformat(timespec="milliseconds")` (IST = a fixed +05:30 `timezone`).
- Validation: route handlers receive `Request`, `await request.body()` → `orjson.loads` (fail → 400) → Pydantic v2 model with `StrictInt` + range constraints (fail → 422). Don't use FastAPI body binding (it merges the two cases into 422). Alternative: register `RequestValidationError` handler that checks `error["type"] == "json_invalid"` → 400 — acceptable and closer to idiom; pick this one **if** the contract suite passes. Query params use `Query(ge=..., le=...)` with the same handler returning 422 `{"error":"validation_error"}`.
- Route order: `/readings/stats` registered before `/readings/{id}`; `id` typed `str` and validated manually (so `1.5`, `-1`, `abc` → 422 uniformly).
- Normalize defaults: custom handlers for `RequestValidationError`, `StarletteHTTPException` (404/405 → `not_found`), `Exception` (500). Disable `/docs`, `/redoc`, `/openapi.json` (`docs_url=None, redoc_url=None, openapi_url=None`).
- Env: `PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`, no `--reload`, no `gc` tuning in baseline (variant: `gc.freeze()` after startup).
- Dockerfile (multi-stage):
  ```dockerfile
  ARG PYTHON_IMAGE=python:3.12-slim
  FROM ${PYTHON_IMAGE} AS build
  ENV PIP_NO_CACHE_DIR=1
  RUN python -m venv /opt/venv
  COPY requirements.txt .
  RUN /opt/venv/bin/pip install --require-hashes -r requirements.txt
  FROM ${PYTHON_IMAGE}
  RUN useradd -r -u 10001 app
  COPY --from=build /opt/venv /opt/venv
  COPY app /srv/app
  ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
  WORKDIR /srv
  USER 10001
  EXPOSE 8080
  STOPSIGNAL SIGTERM
  CMD ["sh","-c","exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers ${APP_WORKERS:-2} --loop uvloop --http httptools --no-access-log --log-level error --backlog 2048"]
  ```
  Memory budget: ~120–180 MiB per worker idle; must stay < 1 GiB at 100 VUs (record peak RSS).
- Known FastAPI traps: Uvicorn multi-worker restarts a dead worker silently (check logs for restarts → invalid run); default `Starlette` JSON handling of floats for integer fields; `Decimal`/`datetime` in `jsonable_encoder` is slow — never route responses through it.

### 5.6 SQL (verbatim from README §3, all stacks)
Same text, same parameter order, `$n`/`?` placeholders only. Batch: one `INSERT INTO readings (device_id,temperature_centi,humidity_bp,observed_at) VALUES ($1,$2,$3,$4),($5,$6,$7,$8),...` with no RETURNING; response `{"inserted":n}`. Pre-flight `EXPLAIN (ANALYZE, BUFFERS)` per query via `pg_stat_statements` and a shared `explain.sql`; require identical plans (Index Scan using `idx_readings_device_time_id`, PK scan for by-id).

---

## 6. k6 design

### 6.1 Scenarios (single script, env `SCENARIO`)
- `closed` (default): `constant-vus`, `VUS=100`, `DURATION=120s`, `gracefulStop=15s`. **Primary benchmark.**
- `warmup`: same but 60 s, results discarded (separate `RUN_ID`).
- `open`: `constant-arrival-rate`, `RATE`, `DURATION=120s`, `preAllocatedVUs=200`, `maxVUs=2000`; run is invalid if `dropped_iterations > 0`. Sweep `RATE ∈ {100,300,500,1000,2000,...}` until p95 SLO (e.g. 100 ms) or error > 1% breaks.
- `fixed`: `shared-iterations`, `vus=100`, `iterations=100000`, `maxDuration=10m`, `WORKLOAD=insert`.
- `smoke`: 10 VUs, 10 s.

### 6.2 Script fixes (D4, D5)
```js
// operation choice decoupled from device/key choice
const iter = exec.scenario.iterationInTest;
const slot = (iter * 37 + 11) % 100;             // 37 is coprime to 100: exact 50/30/10/9/1 mix
const key  = exec.vu.idInTest * 7919 + exec.vu.iterationInScenario * 104729; // large primes
const device = (key % 1000) + 1;
const readingId = (Math.imul(key, 2654435761) >>> 0) % 1000000 + 1;  // spread over whole table
```
- Deep check on every 100th iteration (`iter % 100 === 0`): parse JSON and assert shape/types (pk: `id` equals requested; range: `items.length === 50` and strictly descending; stats: `count === 1000` when full range; insert: `deviceId` echoed). Keeps k6 CPU low while enforcing "bodies are real".
- Tag every request `operation`, `stack`, `scenario`. `discardResponseBodies: false`.
- Thresholds: `http_req_failed < 0.01`, `checks > 0.99` (mark run invalid, not abort). `dropped_iterations == 0` for open model.
- `insert` payload: spread `observedAt` over a 30-day window beyond seed (`2026-02-01 + (key % 2_592_000) s`) so inserts hit varied index positions instead of one hot leaf page. Document: identical across stacks.
- Known-good IDs: pk uses 1..1,000,000 only → all 200; after writes still fine.
- Summary: also export `data` plus a compact `results/<RUN_ID>.summary.json` (rps, successful rps, p50/p90/p95/p99, max, fail rate, iterations, dropped, bytes).

### 6.3 Run validity rules (auto-checked by orchestrator)
Invalid and re-run if: k6 container CPU > 70% of cap; any `dropped_iterations` in open model; app container OOM-killed or restarted; Uvicorn/Node worker respawn in logs; error rate > 1%; DB row count start ≠ 1,000,000 (write workloads) or ≠ end for read workloads; cgroup `nr_throttled` > 0 in k6/DB; host load/steal outside bounds.

---

## 7. Fair-benchmark controls (checklist enforced by `run-one.sh`)

Environment
1. One physical host (or VM) type for all runs; CPU model, kernel, Docker version, governor, THP setting recorded.
2. Native architecture; no emulation (Apple Silicon → `linux/arm64` for everything).
3. Same Docker network (bridge), same DB container, same PG settings, same data directory device.
4. Only the stack under test is running (`docker compose ps` assert). Nothing else publishes port 8080.
5. Asia/Kolkata clock; NTP off during runs; no host cron/backup/indexing (macOS Spotlight, Time Machine off).

Application
6. Identical limits (§4.1); runtime-visible CPU count capped (`GOMAXPROCS`, `ActiveProcessorCount`, 2 workers, 2 Tokio threads).
7. Total DB connections = 20, verified from `pg_stat_activity` after prewarm (`count(*) WHERE usename='bench' AND datname='sensorpulse'` must equal 20 for every stack). Prewarm: orchestrator fires 40 concurrent `/readings/1` requests (or `SELECT 1` through the app if a hidden endpoint were allowed — it is not) before warm-up; with min=max pools connections are opened at startup anyway.
8. Same logging level (error), no access log, no tracing/profilers/debug, no compression, same keep-alive behavior (k6 default keep-alive; server idle timeout ≥ 60 s on all stacks: Tomcat `connection-timeout=60s`, Fastify `keepAliveTimeout=60000`, Uvicorn `--timeout-keep-alive 60`, Axum/hyper default, Go `IdleTimeout=60s`).
9. Dependency lockfiles and image digests recorded; no upgrade during matrix.

Database
10. Same baseline snapshot (`sha256` recorded). Template-DB restore before **every** measured run of **every** workload (read workloads too — cheap, removes dead tuples/hint-bit/visibility-map differences).
11. After restore: `VACUUM (FREEZE, ANALYZE)` baked into the template, `CHECKPOINT`, `pg_stat_statements_reset()`, `pg_stat_reset()`.
12. Cache state: `pg_prewarm('readings')`, `pg_prewarm('readings_pkey')`, `pg_prewarm('idx_readings_device_time_id')` (≈ 90 MB table + indexes, fits in 512 MB shared_buffers) → all stacks start with fully hot buffers. Report DB cache hit ratio; flag < 99%.
13. Disk growth identical start; autovacuum on but baseline has no dead tuples.

Procedure
14. Order: randomized with a seeded shuffle (Latin-square across 5 reps so each stack appears in each position once). Seed recorded.
15. Per cell: restore → start app → health wait → contract smoke (10 VUs, 10 s, **separate** run, followed by second restore) → prewarm → 60 s warm-up → (write workloads: restore again + prime) → reset stats → measured 120 s → collect → stop app → 20 s cool-down.
16. 5 repetitions; report median + min/max (+ IQR); discard none unless invalid by §6.3 (then re-run, log the invalid run).
17. Closed-model result is reported with its limitation (coordinated omission); open-model sweep and fixed-ops write test are published as separate tables.
18. Instrumentation-off control: one extra rep per stack with `pg_stat_statements.track=none` to estimate collector overhead.
19. Sanity yardsticks (optional): run a trivial `/health` hello world per stack to show framework ceiling and DB-free overhead; run `pgbench` on the same DB with 20 clients to show the DB ceiling for the equivalent query.

Interpretation guards
20. Rank only on runs meeting SLO (p99 < 250 ms, error < 0.1%). Report successful RPS per app CPU-second and p95 at matched RPS.
21. A stack hitting the 2-CPU quota is expected; a stack limited by **DB CPU** (PG at ~2 cores) means the test measures PostgreSQL, not the app — flag it. With 2 DB cores and 20 connections, light queries like PK lookup may saturate PG for the fast stacks; check this before concluding.
22. Declare which comparisons are "baseline config" vs "tuned config".

---

## 8. Orchestration and data collection

`scripts/run-one.sh <stack> <workload> <rep> <scenario>` (sketch):
```bash
RUN_ID="${STACK}-${WORKLOAD}-${SCENARIO}-r${REP}"
./scripts/restore-baseline.sh                       # stop apps, drop/create from template, CHECKPOINT
docker compose --profile $STACK up -d --build app    # build once per matrix, not per run
wait_health http://localhost:8080/health 60
./contract/run.sh --smoke && ./scripts/restore-baseline.sh
./scripts/prime-cache.sh
k6 run -e SCENARIO=warmup -e DURATION=60s ... && { [ "$MUTATING" ] && ./scripts/restore-baseline.sh && ./scripts/prime-cache.sh; }
./scripts/collect-pg.sh start $RUN_ID
./scripts/collect-cgroup.sh start $RUN_ID            # 1 Hz: app, db, k6
k6 run -e SCENARIO=$SCENARIO -e RUN_ID=$RUN_ID ...
./scripts/collect-cgroup.sh stop; ./scripts/collect-pg.sh stop $RUN_ID
./scripts/manifest.sh $RUN_ID
validate_run $RUN_ID || mark_invalid
docker compose stop app; sleep 20
```

### 8.1 Template-DB restore (fixes D7)
One-time: after seed+index+`VACUUM FREEZE ANALYZE`, `CREATE DATABASE sensorpulse_tpl TEMPLATE sensorpulse; ALTER DATABASE sensorpulse_tpl IS_TEMPLATE true ALLOW_CONNECTIONS false;` and `pg_dump -Fc` for archival hash.
Per run (apps stopped): `DROP DATABASE sensorpulse WITH (FORCE); CREATE DATABASE sensorpulse TEMPLATE sensorpulse_tpl OWNER bench; CHECKPOINT;` ≈ 3–5 s (file copy), re-create `pg_stat_statements` extension is carried by the template. Identity sequence is restored with the data (next id 1,000,001) — assert.

### 8.2 Collectors (low overhead)
- cgroup v2 sampler reading `cpu.stat` (`usage_usec`, `nr_throttled`, `throttled_usec`), `memory.current`, `memory.peak`, `memory.events` (`oom_kill`) for app/db/k6 at 1 Hz, written to CSV. Docker Desktop fallback: `docker stats --no-stream` at 1 Hz (coarser; label accordingly).
- PG snapshot before/after: `pg_stat_database` (xact_commit, blks_hit/read, tup_*, temp_files), `pg_stat_statements` top 10, `pg_stat_bgwriter`/`pg_stat_io`, `pg_stat_activity` counts, `count(*) FROM readings`, `pg_relation_size` for table/indexes, dead tuples.
- App-side: pool queue wait where cheap (Hikari metrics disabled by default → record final pool stats from `/proc`-free logs on shutdown only; do not add per-request metrics).
- Optional `monitor` profile (Prometheus + cAdvisor + postgres-exporter + Grafana) for exploration runs only; not active during published runs.

### 8.3 Manifest (extends `docs/results-schema.json`)
Add: `scenario`, `rate`, `rep`, `order`, `shuffleSeed`, `valid`, `invalidReasons[]`, `runtimeFlags`, `poolMin/Max`, `workers`, `pgConnections`, `cacheHitRatio`, `k6CpuPeakPct`, `hostGrade (publication|local)`, `warmupSeconds`, `kernel`, `governor`. Generated by script, never hand-edited.

---

## 9. Acceptance gates (supersede README §10 where stricter)

| Gate | Criteria |
|------|----------|
| G0 | D1–D9 fixed; `docker compose up postgres` blocks until 1M rows present (`verify.sql` passes, healthcheck-driven). |
| G1 | Contract suite 30/30 on Go; golden bodies byte-identical; suite itself reviewed. |
| G2 | Each other stack 30/30 with **zero** change to tests; SIGTERM exit ≤ 10 s; image runs as non-root; `docker stats` idle memory recorded. |
| G3 | Plan equality: `EXPLAIN` of all five query shapes identical per stack (from `pg_stat_statements` queryid parity: each stack yields the same 5–6 queryids). |
| G4 | Pool parity: exactly 20 DB sessions per stack after start. |
| G5 | Smoke matrix (health, pk, insert × 1 rep) zero errors, k6 CPU < 70%, no throttling in k6/DB. |
| G6 | Full matrix complete, ≥ 95% runs valid first time; spread (max−min)/median of RPS < 10% for reads, else investigate before publishing. |
| G7 | Report includes medians, dispersion, tails, errors, CPU/RSS, DB ratio, limitations, all digests/versions/flags. |

---

## 10. Per-run cost and matrix size

Closed-model matrix: 5 stacks × 7 workloads × 5 reps = 175 cells × (restore 10 s + start 15 s + smoke 30 s + prime 15 s + warm-up 60 s + [restore+prime 25 s for mutating] + measured 120 s + collect/stop 30 s) ≈ 5 min → **≈ 14.5 h** (not 7 h; the earlier estimate ignores warm-up and restores). Reduce with: 3 reps in exploration; skip per-cell contract smoke after the first rep per stack; reuse warm-up across reads. Open sweep (≈ 5 rates × 5 stacks × 3 workloads × 3 reps) and fixed-ops tests are extra.

---

## 11. Risks and decisions needed from the owner

1. Linux host available for publication-grade runs? (Mac Docker Desktop results = `grade: local` only.)
2. Warm-up duration: uniform 60 s recommended (JVM). README says 30 s.
3. orjson in FastAPI and `encoding/json` in Go: allowed "idiomatic fast path" or force same-class serializer? Recommendation: idiomatic per stack, documented.
4. Read workloads restored before each run (recommended) vs only write workloads (README).
5. Is PG at 2 CPUs expected to be the bottleneck for fast stacks? If yes, consider reporting a second tier with DB 4 CPUs so app differences remain visible.
6. Spring virtual threads, NestJS Express, FastAPI sync/threadpool, Go fasthttp as optional "variant" tracks only after the baseline is done.
