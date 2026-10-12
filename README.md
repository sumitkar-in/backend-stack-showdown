# SensorPulse Benchmark Lab

[![GitHub stars](https://img.shields.io/github/stars/sumitkar-in/backend-stack-showdown?style=social)](https://github.com/sumitkar-in/backend-stack-showdown/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/sumitkar-in/backend-stack-showdown?style=social)](https://github.com/sumitkar-in/backend-stack-showdown/network/members)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sumitkar-in/backend-stack-showdown)

A like-for-like load-test comparison of eight web stacks serving **the same REST API** over **the same PostgreSQL database**, everything running in Docker with identical resource limits:

| Stack | Framework | DB access |
| --- | --- | --- |
| **NestJS** | NestJS 10 + Fastify, Node 22 (2 cluster workers) | `pg` |
| **Spring Boot** | Spring Boot 3.4 MVC (Tomcat), Java 21 | JDBC `JdbcTemplate` + HikariCP |
| **Go** | Gin 1.10, Go 1.23 | `pgx/v5` `pgxpool` |
| **Rust** | Axum 0.8, Tokio, Rust 1.98 | SQLx 0.8 |
| **FastAPI** | FastAPI 0.115 + Uvicorn (2 workers), Python 3.12 | `asyncpg` |
| **Laravel** | Laravel 12 on nginx + PHP-FPM (20 static workers), PHP 8.3 | PDO `pgsql` (persistent) |
| **Laravel Octane** | Laravel 12 on Octane + Swoole (4 workers), PHP 8.3 | PDO `pgsql` (one connection per worker) |
| **Spring Boot Native** | Spring Boot 3.4 MVC (Tomcat) compiled to a GraalVM native image, Java 21 | JDBC `JdbcTemplate` + HikariCP |

Two side-by-side write-ups: Laravel (PHP-FPM) vs Laravel Octane in [`docs/laravel-vs-octane.md`](docs/laravel-vs-octane.md), and Spring Boot on the JVM vs as a GraalVM native image in [`docs/spring-jvm-vs-graalvm.md`](docs/spring-jvm-vs-graalvm.md).

Dataset: **1,000 devices and 1,000,000 sensor readings**. Load: **100 constant k6 virtual users** (closed model) plus an **open-model ramp** that finds where each stack breaks and the highest load that keeps p95 under a latency threshold (default **0.5 ms**).

> Everything here measures a *whole stack* (language runtime + framework + driver), not "language speed". No ORM, cache, queue, auth, TLS, proxy or compression is involved.

---

## Contents

1. [Quick start](#1-quick-start)
2. [Repository layout](#2-repository-layout)
3. [The API contract](#3-the-api-contract)
4. [Database](#4-database)
5. [Stack implementations](#5-stack-implementations)
6. [Docker setup and resource limits](#6-docker-setup-and-resource-limits)
7. [Benchmark: how a run works](#7-benchmark-how-a-run-works)
8. [Ramp test: finding the breaking point](#8-ramp-test-finding-the-breaking-point)
9. [Reports](#9-reports)
10. [Contract smoke test](#10-contract-smoke-test)
11. [Fairness controls](#11-fairness-controls)
12. [Results snapshot](#12-results-snapshot)
13. [Bugs found while building this (and fixed)](#13-bugs-found-while-building-this-and-fixed)
14. [Limitations](#14-limitations)
15. [Configuration reference](#15-configuration-reference)
16. [Troubleshooting](#16-troubleshooting)
17. [Extending: add another stack](#17-extending-add-another-stack)
18. [Authentication (JWT)](#18-authentication-jwt)

---

## 1. Quick start

**Prerequisites:** Docker (Compose v2) with a VM of **≥ 8 CPUs and ≥ 8 GiB RAM** (app 2 vCPU + PostgreSQL 2 vCPU + k6 4+ vCPU), `bash`, `curl`, `python3` (3.9+, standard library only). Nothing else is installed on the host: builds, k6 and database tools all run in containers. macOS is the tested host; the scripts use `sysctl`/`caffeinate` when present.

```bash
cp .env.example .env          # set PLATFORM to match your CPU: linux/arm64 (Apple Silicon) or linux/amd64

# Everything in one command: auth tests -> 100-VU benchmark -> ramp test -> combined report (~35 min after first builds)
scripts/run.sh

# Or by stage / size
scripts/run.sh bench ramp                  # stages: auth | bench | ramp | authcost | report
QUICK=1 STACKS=go scripts/run.sh           # ~2 min smoke-sized run to check the setup
FULL=1 scripts/run.sh                      # also measure the cost of JWT (authcost stage)

# The stage scripts also run on their own
scripts/run-benchmark.sh                   # NestJS -> Spring Boot -> Go -> Rust -> FastAPI -> Laravel -> Laravel Octane, 7 workloads each
scripts/run-ramp.sh                        # breaking point and the p95 <= 0.5 ms threshold (~4 min per stack)
scripts/run-auth-test.sh                   # JWT contract on every stack
```

The first run pulls images, builds the eight apps, starts PostgreSQL and seeds 1,000,000 rows (about 30 s). Each script finishes by writing an HTML report, refreshing `results/index.html` (every run) and `results/report.html` (everything combined), and printing the report path (`results/benchmarks/<run>/report.html`, `results/ramps/<run>/ramp-report.html`).

Useful variations:

```bash
STACKS="go rust" WORKLOADS="pk mixed" DURATION=60s REPS=3 scripts/run-benchmark.sh
RUN_ID=2026-10-10_1530_full STACKS=fastapi scripts/run-benchmark.sh   # add a stack to an earlier run
AUTH_MODE=jwt LABEL=jwt scripts/run-benchmark.sh                      # benchmark with JWT auth on
scripts/run-auth-test.sh                                              # auth contract test, all stacks
P95_TARGET_MS=1 RATES="1000,2000,4000,8000" STACKS=go scripts/run-ramp.sh
```

### Why auth, benchmark and ramp are separate

They answer different questions and need different conditions, so they are separate scripts that `scripts/run.sh` chains:

| Test | Question it answers | Why it is its own run |
| --- | --- | --- |
| **auth** (`run-auth-test.sh`) | Is the JWT behaviour correct and identical in every stack? | A pass/fail *correctness* test, not a measurement. It starts each app with `AUTH_MODE=jwt`, runs the 29 auth checks plus the 38 API checks, then restarts with `AUTH_MODE=none`. Auth is off in the benchmarks, so mixing it in would change what they measure. |
| **bench** (`run-benchmark.sh`) | How fast is each stack under a fixed 100-VU load, per workload? | Closed model (users wait for replies), so the system sets the pace. It resets the database to the exact 1M-row baseline before every run, which is slow and must not be disturbed. |
| **ramp** (`run-ramp.sh`) | Where does each stack break, and what is the highest rate with p95 under the target? | Open model (fixed arrival rate that climbs in steps), so it overloads the app on purpose. Overload leaves the database and app in a different state, and a run takes about 4 min per stack, so it must not share a run with the steady benchmark. |
| **authcost** (`FULL=1`) | What does JWT verification cost? | The same workloads twice (auth off, then on) as an A/B pair, so it needs its own paired runs. |

Keeping them apart means a failing correctness check cannot hide inside throughput numbers, you can rerun only the slow or noisy part, and each stage writes its own report (`results/auth/`, `results/benchmarks/`, `results/ramps/`). `scripts/run.sh` runs them in order under one run id and refreshes the combined `results/report.html`; one stage failing does not stop the next, but the exit code is non-zero.

### Running tests: one, some, or everything

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

Start only the database and try an app by hand:

```bash
docker compose -f infra/compose.yaml -f infra/compose.dev.yaml up -d --wait postgres
docker compose -f infra/compose.yaml -f infra/compose.dev.yaml --profile go up -d --build app-go
curl -s localhost:8080/readings/1
```

Reset everything (also forces a re-seed): `docker compose -f infra/compose.yaml down -v`.

---

## 2. Repository layout

```text
.
├── README.md                  this file
├── .env.example               copy to .env (PLATFORM, image pins); .env is git-ignored
├── api/openapi.yaml           machine-readable API contract
├── db/                        init scripts run by PostgreSQL on first start
│   ├── 00-schema.sql          tables + pg_stat_statements
│   ├── 01-seed.sql            1,000 devices, 1,000,000 readings (deterministic)
│   ├── 02-indexes.sql         the single composite index, built after loading
│   └── verify.sql             row-count / index sanity query
├── infra/
│   ├── compose.yaml           postgres, 8 app services (profiles), k6, db tools, runner
│   └── compose.dev.yaml       optional override: publish app on localhost:8080
├── apps/
│   ├── nest/  spring/  go/  rust/  fastapi/  laravel/  laravel-octane/  spring-with-graalvm/    one folder per stack
│   │                       (Dockerfile, pinned deps, README with stack-specific notes)
├── k6/
│   ├── bench.js               closed-model workloads at 100 VUs
│   └── ramp.js                open-model stepped ramp
├── scripts/
│   ├── run-benchmark.sh       end-to-end benchmark driver (AUTH_MODE=jwt for the auth variant)
│   ├── run-ramp.sh            end-to-end ramp driver
│   ├── run-auth-test.sh       JWT auth test for every stack
│   ├── smoke.sh               byte-exact API contract checks (38 checks)
│   ├── smoke-auth.sh          JWT auth contract checks (29 checks)
│   ├── jwt.py                 mints valid/expired/forged tokens for the tests
│   ├── run.sh                 single entry point: auth + bench + ramp + combined report
│   ├── lib.sh                 helpers shared by the run scripts (compose, psql, logging, cleanup, sampling)
│   ├── report.py              all reporting: bench | ramp | auth | all | index | refresh
│   ├── reporting/             report code: common (theme, parsers, charts), bench, ramp, auth, runs, combined
│   ├── organize-results.py    moves old flat results into the layout below
│   └── pg/                    restore.sql, reset.sql, make-template.sql
├── docs/
│   ├── blueprint.md           original design notes
│   ├── implementation-plan.md detailed plan, fairness rules, risks
│   ├── contract-tests.md      original contract checklist
│   ├── stack-implementation.md, runner.md, results-schema.json
└── results/                   generated output (git-ignored except its README)
    ├── index.html             start here: every run, newest first, with links to the reports
    ├── benchmarks/<date>_<time>_<label>/   100-VU runs
    ├── ramps/<date>_<time>_<label>/        ramp tests
    └── auth/<date>_<time>_<label>/         auth tests
        each run: report.html · env.txt · cells.tsv · run.log
                  k6/ (summaries, logs) · stats/ (docker stats) · postgres/ (statement stats)
                  contract/ (smoke output) · logs/ (build, app)
```

---

## 3. The API contract

Six routes, identical in every stack (optionally behind JWT auth, [section 18](#18-authentication-jwt)). JSON only, camelCase keys, compact bodies with a **fixed key order**, `Content-Length` always set (no chunked responses). Formal spec: [`api/openapi.yaml`](api/openapi.yaml).

| Method | Path | Behaviour | Success |
| --- | --- | --- | --- |
| GET | `/health` | static body, **no DB access** | 200 `{"status":"ok"}` |
| GET | `/readings/{id}` | primary-key lookup | 200 Reading / 404 |
| GET | `/readings?deviceId&from&to&limit&offset` | device + time range, newest first | 200 `{"items":[...],"limit":50,"offset":0}` |
| GET | `/readings/stats?deviceId&from&to` | count, sums, min, max over the range | 200 Stats |
| POST | `/readings` | insert one reading | 201 Reading (with generated `id`) |
| POST | `/readings/batch` | insert 1–100 readings atomically | 201 `{"inserted":n}` |

```json
{"id":1,"deviceId":1,"temperatureCenti":1837,"humidityBp":3011,"observedAt":"2026-01-01T00:00:00.000+05:30"}
{"deviceId":17,"count":1000,"temperatureSumCenti":2650000,"humiditySumBp":6000000,"temperatureMinCenti":1800,"temperatureMaxCenti":3500}
```

Units: temperature in **centi-degrees Celsius** (integer), humidity in **basis points** (0–10000), timestamps in **Asia/Kolkata with exactly 3 fractional digits and the fixed offset `+05:30`** (India has no DST; there is no UTC and no `Z` in any response). Integers avoid float-formatting differences between languages.

### Validation and errors

| Rule | Limit |
| --- | --- |
| `deviceId` | integer ≥ 1 (unknown device on insert → 422 via foreign key) |
| `temperatureCenti` | integer −5000 … 10000 |
| `humidityBp` | integer 0 … 10000 |
| `observedAt` | RFC 3339 with timezone, ≤ 3 fractional digits; any offset (a trailing `Z` too) is accepted and converted to Asia/Kolkata. In a query string write the `+` as `%2B` |
| list/stats range | `from` and `to` required, `from < to`, lower bound inclusive, upper exclusive |
| paging | `limit` 1–100 (default 50), `offset` 0–1000 (default 0) |
| batch | 1–100 readings, all-or-nothing |

Error bodies are always `{"error": "..."}`:

| Situation | Status | Body |
| --- | --- | --- |
| Missing/invalid/expired bearer token (only with `AUTH_MODE=jwt`) | 401 | `unauthorized` |
| Malformed or empty JSON, non-object body | 400 | `bad_request` |
| Missing field, wrong type (including `2375.5` or a numeric string), out of range, bad query/path value, unknown device | 422 | `validation_error` |
| Unknown reading id, unknown route, wrong method | 404 | `not_found` |
| Unexpected server error | 500 | `internal` |

Every stack reads the body as raw bytes, parses JSON first (failure → 400), then validates fields (failure → 422), because frameworks otherwise collapse both cases into one status.

---

## 4. Database

PostgreSQL 17, one instance, same configuration for every run.

```sql
devices(id int identity PK, name varchar(64) unique, location varchar(64))
readings(id bigint identity PK,
         device_id int NOT NULL REFERENCES devices(id),
         temperature_centi smallint CHECK (-5000..10000),
         humidity_bp smallint CHECK (0..10000),
         observed_at timestamptz(3) NOT NULL)
INDEX idx_readings_device_time_id ON readings (device_id, observed_at DESC, id DESC)
```

- **Seed** (`db/01-seed.sql`): 1,000 devices `sensor-0001…`, 1,000,000 readings, deterministic. Reading *g* belongs to device `((g-1) % 1000) + 1`, observed at `2026-01-01T00:00:00+05:30 + (g-1) seconds` (about 11.6 days). Each device has exactly 1,000 readings. The index is created **after** loading.
- **Queries** (identical text in every stack): one `SELECT … WHERE id = $1`; one `SELECT … WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3 ORDER BY observed_at DESC, id DESC LIMIT $4 OFFSET $5` (no `COUNT(*)` for paging); one aggregate `SELECT COUNT/SUM/MIN/MAX`; `INSERT … RETURNING`; and a single multi-row `INSERT` for batches.
- **Server settings** (`infra/compose.yaml`): `shared_buffers=512MB`, `effective_cache_size=1536MB`, `max_connections=100`, `max_wal_size=4GB`, `checkpoint_timeout=15min`, `pg_stat_statements` on, durability **on** (`fsync`, `synchronous_commit`), so write results are not inflated.
- **Baseline template.** After the first start the benchmark scripts create a `sensorpulse_tpl` template database. Before every stack the database is recreated from it in seconds (`scripts/pg/restore.sql`). Between runs `scripts/pg/reset.sql` deletes rows with `id > 1000000`, restarts the identity sequence at 1,000,001, vacuums, checkpoints, pre-warms the table and indexes into shared buffers, and zeroes statistics.

---

## 5. Stack implementations

All eight: listen on `0.0.0.0:8080`, read `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD/DB_POOL_TOTAL`, use raw parameterized SQL with server-side prepared statements, log errors only (no access log), disable docs/dev tooling, open **all pool connections at startup** (min = max), and shut down gracefully on SIGTERM. **Total DB connections = 20** in every stack.

| | NestJS | Spring Boot | Go | Rust | FastAPI | Laravel | Laravel Octane | Spring Boot Native |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime | Node 22 | Java 21 (G1) | Go 1.23 | Rust 1.98, release (fat LTO, `panic=abort`) | Python 3.12 | PHP 8.3 (opcache, JIT off) | PHP 8.3 (opcache, JIT off) | GraalVM native image (Java 21 source), no JIT |
| Server | Fastify adapter, Node `cluster` ×2 | Tomcat, 200 threads | `net/http` via Gin (release mode) | Hyper via Axum 0.8, 2 Tokio threads | Uvicorn ×2 workers, uvloop + httptools | nginx (2 workers) + PHP-FPM, 20 static workers | Octane on Swoole, no nginx, 4 workers | Tomcat, 200 threads (same as Spring) |
| Driver | `pg` 8.13 (named queries) | PostgreSQL JDBC (`prepareThreshold=1`) | pgx v5 (statement cache) | SQLx 0.8 (statement cache) | asyncpg 0.30 | PDO pgsql, native prepares (no cross-request statement cache) | PDO pgsql, native prepares (same as Laravel) | PostgreSQL JDBC (`prepareThreshold=1`) |
| Pool | 2 × 10 | Hikari 20 | pgxpool 20 | 20 | 2 × 10 | 20 workers × 1 persistent connection | 4 workers × 1 connection | Hikari 20 |
| JSON | `JSON.stringify` | Jackson → `byte[]` | `encoding/json` | `serde_json` | `orjson` | `json_encode` | `json_encode` | Jackson → `byte[]` |
| Runtime caps | `--max-old-space-size=1536` | `ActiveProcessorCount=2`, `MaxRAMPercentage=65` | `GOMAXPROCS=2`, `GOMEMLIMIT=3GiB` | `TOKIO_WORKER_THREADS=2` | – | `PHP_FPM_CHILDREN=20` | `OCTANE_WORKERS=4` | `NATIVE_OPTS=-Xmx2600m`, Serial GC |
| Image | `node:22-slim` | `eclipse-temurin:21-jre` | distroless static | distroless cc | `python:3.12-slim` | `php:8.3-fpm-bookworm` + nginx | `php:8.3-cli-bookworm` + Swoole | `debian:bookworm-slim` + native executable |

Deliberate choices worth knowing:

- **Hand-written validation** everywhere (no `class-validator`, Pydantic body binding, Bean Validation, or serde derive on request types) so the 400/422 split and exact error bodies are identical.
- **Response bodies are built explicitly** (serialized to bytes, with a fixed key order) so all stacks send the same bytes. This is checked byte-for-byte against values read from PostgreSQL.
- **Spring** keeps Tomcat's keep-alive unlimited (`max-keep-alive-requests=-1`); the default of 100 would recycle connections and penalize it.
- **Rust** enables `TCP_NODELAY` (the other runtimes already default to it) and disables SQLx's `test_before_acquire` (see [section 13](#13-bugs-found-while-building-this-and-fixed)).
- **NestJS** uses a raw-buffer content-type parser and `bodyParser: false`; a worker crash exits the primary with code 1 instead of respawning. Known gap: `JSON.parse` can't tell `2375.0` from `2375`, so only non-integer numbers like `2375.5` are rejected.
- **FastAPI** returns raw `Response` objects (no `response_model`), disables `/docs`/`/openapi.json`, and asserts at startup that pool × workers = 20.
- **Laravel** is full Laravel (kernel, router, container, exception handler) with raw `DB::select`/`DB::insert`, not Eloquent. The web middleware group and the default global middleware are removed (sessions, cookies, CSRF and input trimming are not part of the contract), and the DB config avoids the per-request `SET search_path/timezone` statements Laravel would otherwise send. PHP cannot share a pool across workers, so 20 static FPM workers each hold one persistent connection (opened on first use). `Content-Length` is set explicitly, otherwise nginx replies chunked.
- **Laravel Octane** (`apps/laravel-octane`) is the same Laravel app and SQL served by `octane:start --server=swoole` instead of nginx + PHP-FPM, so the framework boots once per worker rather than per request. 4 Swoole workers (`OCTANE_WORKERS`) each hold one PDO connection for life (4 DB sessions, within the 20-connection budget). Workers are blocking; in a quick check on 2 vCPU, 4 beat 2 and 8 (8 workers inflated p95 to ~80 ms through CFS throttling). No nginx, no `ATTR_PERSISTENT`. It passes the same 38 API checks and 29 auth checks. Image: `php:8.3-cli-bookworm` + Swoole (PECL) + `procps` (Octane needs `pgrep`).
- **Spring Boot Native** (`apps/spring-with-graalvm`) is the same app compiled ahead of time with `native-maven-plugin` (`-O2`, Serial GC; the community build has no G1 and no PGO). Native images ignore `JAVA_TOOL_OPTIONS`, so compose passes `NATIVE_OPTS=-Xmx2600m`. Spring AOT resolves `@ConditionalOnProperty` at build time, so the JWT interceptor is registered unconditionally and enabled at runtime, and the model records are registered for reflection because `Json.respond()` serializes them with a plain `ObjectMapper`. First build takes several minutes and about 6 GiB of RAM.
- **Dependencies are pinned**: `Cargo.lock`, `go.sum`, `package-lock.json`, `composer.lock` are committed; Python and Maven versions are pinned in `requirements.txt` / `pom.xml`.

### Runtime setup: Java and Rust in detail

**Spring Boot (JVM) - `apps/spring`**

| Setting | Value |
| --- | --- |
| Java | **21** (LTS), Eclipse Temurin JRE (`eclipse-temurin:21-jre`; `21.0.12.1` in the measured build, since the tag floats with patch releases) |
| Spring Boot | 3.4.1 (`spring-boot-starter-parent`), Spring MVC on embedded Tomcat |
| Threading model | **Platform threads, not virtual threads.** Tomcat runs a pool of up to **200 platform request threads** (`server.tomcat.threads.max=200`); `spring.threads.virtual.enabled` is not set, so it stays `false`. One request occupies one thread for its whole life, including the blocking JDBC call. |
| Database access | Blocking JDBC (`JdbcTemplate`) on **HikariCP, 20 connections** (min = max, opened at startup). With 200 request threads and 20 connections, up to 180 threads can wait for a connection under load. |
| GC | **G1** (the ergonomic default on 2 CPUs: `ParallelGCThreads=2`, `ConcGCThreads=1`) |
| JVM flags | `-XX:MaxRAMPercentage=65.0 -XX:ActiveProcessorCount=2` (via `JAVA_TOOL_OPTIONS` in compose) and `-Xss512k` (thread stack size) |
| Memory | container limit 4 GiB, so the heap ceiling is about 2.6 GiB; measured peak about 840 MiB |
| JIT | default tiered C1/C2; the 10 s warm-up is short for a JIT, which favours the other runtimes slightly |

Virtual threads were **not** used. They would remove the 200-thread cap and make blocked threads cheap, but the 20-connection database budget and the fixed 2-vCPU quota are the real limits here, so the expected gain is small; it has not been measured. To try it, set `spring.threads.virtual.enabled=true` in `apps/spring/src/main/resources/application.properties` and rerun `STACKS=spring scripts/run-benchmark.sh`. The GraalVM variant uses the same threading model (platform threads).

**Rust - `apps/rust`**

| Setting | Value |
| --- | --- |
| Rust | **1.98.0** (`rust:1.98.0-slim`), edition 2021, `--locked` builds from `Cargo.lock` |
| HTTP | **Axum 0.8.1** on Hyper, **HTTP/1.1 only** (`http1` feature), `TCP_NODELAY` on |
| Runtime and threading | **Tokio 1.42.0 multi-threaded runtime with 2 worker threads** (`TOKIO_WORKER_THREADS=2`, matching the 2 vCPU quota). Requests are async tasks scheduled over those 2 OS threads, **not one thread per request**; no `spawn_blocking` on the hot path. |
| Database access | **SQLx 0.8.3** (async, Tokio) with a **20-connection** pool (min = max, all opened at startup), statement cache on, `test_before_acquire(false)` (see [section 13](#13-bugs-found-while-building-this-and-fixed)) |
| JSON | `serde_json` on fixed structs; request bodies validated by hand |
| Build profile | `opt-level = 3`, **fat LTO**, `codegen-units = 1`, `panic = "abort"`, symbols stripped. No `-C target-cpu=native`, so the binary is portable. |
| Image | `gcr.io/distroless/cc-debian12:nonroot` (dynamic glibc), peak memory about 8 MiB |

Both are blocking-vs-async by design: the JVM variant is thread-per-request over blocking JDBC, the Rust variant is a small fixed set of threads multiplexing many async tasks, which is a large part of why Rust uses 100x less memory at similar throughput on the database-bound workloads.

Each `apps/<stack>/README.md` has the stack-specific details.

---

## 6. Docker setup and resource limits

| Container | CPU | Memory | Other |
| --- | --- | --- | --- |
| each app (one runs at a time) | **2.0 vCPU** | **4 GiB** (swap = same, i.e. none) | `pids_limit` 1024, `nofile` 65536, `init: true`, SIGTERM + 15 s grace |
| PostgreSQL | 2.0 vCPU | 2 GiB (no swap) | `shm_size` 256m |
| k6 | `K6_CPUS` (default 4.0) | `K6_MEM` (default 2g) | – |

Notes:

- CPU limits are CFS quotas (throttling), not pinned cores. Runtimes are also told their CPU count (`GOMAXPROCS`, `ActiveProcessorCount`, 2 workers, 2 Tokio threads).
- Compose profiles `go`, `spring`, `nest`, `fastapi`, `rust` select the app; profile `tools` enables k6 and `dbtools` (psql/pg_dump). A `runner` profile also exists but the current scripts don't use it.
- Apps reach PostgreSQL by service name; k6 reaches the app via the network alias `app` (`http://app:8080`), the same for every stack. `compose.dev.yaml` publishes `127.0.0.1:8080` for curl/health polling; the benchmark scripts include it.
- Pin images for real comparisons: set `POSTGRES_IMAGE` / `K6_IMAGE` in `.env` to exact digests. They default to `postgres:17` and `grafana/k6:latest`.
- Credentials (`bench` / `bench_local_only`) are for local use only; the database is never exposed beyond the Docker network.

---

## 7. Benchmark: how a run works

`scripts/run-benchmark.sh` (stack order **nest → spring → go → rust → fastapi**). For each stack:

1. Stop any other app; **restore the 1M-row baseline** from the template.
2. Build and start the app, wait for `/health`, record startup time and the DB session count (should be exactly 20).
3. Run the **contract smoke test** (38 byte-exact checks, section 10).
4. For each workload, in this fixed order: `health`, `pk`, `range`, `stats`, `insert`, `batch`, `mixed`:
   reset DB (trim to 1M rows, vacuum, checkpoint, pre-warm, zero stats) → **10 s warm-up** → reset again → sample CPU/memory with `docker stats` → **30 s measured run at 100 VUs** → collect `pg_stat_statements`, cache hit ratio, row counts.
5. A run is **valid only if k6's own test clock matches the requested duration** (97–110 %). Otherwise (host or VM stalled) it is retried up to 3 times and flagged in the report if it never passes.
6. Record OOM-kill state and restart count, stop the app.
7. Generate the HTML report.

Workloads (`k6/bench.js`):

| Workload | Request |
| --- | --- |
| `health` | `GET /health` |
| `pk` | `GET /readings/{id}`, ids spread over all 1,000,000 rows |
| `range` | `GET /readings?deviceId=…&limit=50` (50 rows returned) |
| `stats` | `GET /readings/stats?deviceId=…` (aggregates 1,000 rows) |
| `insert` | `POST /readings` |
| `batch` | `POST /readings/batch` with 10 readings |
| `mixed` | exactly 50 % pk, 30 % range, 10 % stats, 9 % insert, 1 % batch |

Every 100th iteration also verifies the response body (ids match, 50 items in descending order, stats `count == 1000`, …), so "fast but wrong" cannot pass. Requests are tagged `name=<workload>`; without that tag k6 creates one metric series per unique URL and runs out of memory.

Defaults are short so a full run finishes in about 25 minutes; raise `DURATION`, `WARMUP` and `REPS` for tighter numbers (JVM and V8 benefit from longer warm-up).

---

## 8. Ramp test: finding the breaking point

`scripts/run-ramp.sh` uses k6 `constant-arrival-rate` (an **open model**) in consecutive steps. Each step holds a fixed offered request rate for 15 s, after a 15 s warm-up. Default steps (req/s): 250, 500, 1000, 2000, 3000, 4000, 6000, 8000, 12000, 16000, 24000, 32000, 48000, on `pk` (set `WORKLOADS` to `health range stats insert` as needed).

Per step the report records served rate, p50/p90/p95/p99/max, errors, dropped iterations, and app, database and k6 CPU.

- A step is **healthy** if errors ≤ 1 %, served ≥ 95 % of the offered rate and dropped iterations ≤ 0.5 %. The first unhealthy step is where the stack **breaks**.
- **p95 threshold**: the highest healthy step whose p95 is within the limit (`P95_TARGET_MS`, default **0.5 ms**). The report also gives a ladder for 1, 2, 5, 10, 25, 50 and 100 ms and from which rate each stack first meets the limit (very low rates are often slower than moderate ones: idle CPUs, cold paths).
- **Limiting factor** per stack: app CPU (≥ 1.7 of 2 cores), database CPU, load-generator CPU, or the VU cap/network.
- If the report says the load generator was the limit, raise `K6_CPUS`, `K6_MEM` and `MAX_VUS`.

---

## 9. Reports

All reports are single self-contained HTML files (no network, light and dark themes, tables behind every chart), built by one script, `scripts/report.py`, from one shared module set (`scripts/reporting/`).

- **`results/report.html`: the combined report.** One page with a per-stack scorecard (mixed throughput, PK p95, efficiency, ramp limits, auth result, JWT cost), then the full benchmark, every ramp run, the auth contract and JWT overhead, and a list of all runs. It picks the broadest no-auth benchmark and all ramps automatically; override with `python3 scripts/report.py all --bench <dir> --ramp <dir> --base <dir> --jwt <dir>`. Rebuilt after every run.
- **`results/index.html`**: catalogue of every run with links.

- **`results/benchmarks/<run>/report.html`**: summary and findings, relative throughput index, throughput / latency (p50, p95, p99) / CPU / memory / requests-per-core charts for every workload, a full latency table, limiting-factor analysis (app CPU, database CPU, or load generator), reliability table (build and startup time, DB sessions, smoke result, OOM/restarts), PostgreSQL statement costs and cache hit ratios, method and limitations, and every raw run.
- **`results/ramps/<run>/ramp-report.html`**: the p95 ≤ 0.5 ms answer per stack, where each breaks and why, the threshold ladder, curves of p95 / served rate / errors / app CPU versus offered load, and every step.

Raw artifacts next to each report: k6 summaries (`*.json`), k6 logs, `docker stats` samples, `pg_stat_statements` dumps, smoke output, build logs, app logs, `env.txt` (host, Docker VM and settings). Regenerate any time with `python3 scripts/report.py bench results/benchmarks/<run>` or `python3 scripts/report.py ramp results/ramps/<run>`; both also refresh `results/index.html` and the combined `results/report.html`. Name a run with `LABEL=jwt scripts/run-benchmark.sh` (folder `2026-10-10_1530_jwt`).

---

## 10. Contract smoke test

`scripts/smoke.sh` (run automatically before load) sends 38 requests and compares against **ground truth read straight from PostgreSQL**:

- byte-exact body for `GET /readings/1` and for device 17's stats, `Content-Length` present on a 50-item list
- pagination (50 items, pages differ, empty envelope), empty-range stats with `null` min/max
- all 4xx cases: bad limit/offset/range/device/timestamp, negative or non-numeric id, unknown route, malformed JSON, missing field, float and string where integer expected, out-of-range temperature/humidity, 4-digit fractional seconds, unknown device
- create round-trip, timezone normalization (a `Z` input → `+05:30`), batch of 10 / 100 inserted, 0 and 101 rejected, **atomicity** (a bad or foreign-key-violating item inserts nothing)

Run it manually against any running app: `BASE=http://localhost:8080 PSQL="docker compose -f infra/compose.yaml exec -T -e PGUSER=bench -e PGDATABASE=sensorpulse postgres psql -tA" scripts/smoke.sh` (it mutates data; reset with `scripts/pg/reset.sql`).

---

## 11. Fairness controls

- Same host, Docker network path, PostgreSQL instance, schema, index, data, SQL text, pool size (20), response bytes and error semantics. Only one app runs at a time.
- Identical CPU/memory limits; runtime CPU counts set explicitly; swap disabled.
- Database reset to the exact 1M-row baseline before every warm-up and measured run, tables and indexes pre-warmed into shared buffers, statistics zeroed; writes do not accumulate across runs.
- Prepared statements everywhere (pgx, asyncpg, SQLx cache them; JDBC `prepareThreshold=1`; `pg` named queries). `EXPLAIN`-level parity is visible in `pg_stat_statements` (same statements, same call counts).
- All pool connections opened at startup; pool size verified from `pg_stat_activity`.
- Keep-alive on everywhere, 60 s idle timeouts; Tomcat's per-connection request cap removed; `TCP_NODELAY` on.
- Warm-up before every measurement; invalid (clock-skewed) runs are retried; thresholds on error rate and checks.
- Body-level verification in k6; byte-exact contract check per stack.
- Reports flag whether the app, the database or the load generator was the bottleneck, so a result that mostly measures PostgreSQL is labelled as such.

---

## 12. Results snapshot

One local run on an Apple Silicon Mac (Docker Desktop VM: 15 vCPU, 8 GiB; app 2 vCPU / 4 GiB; PostgreSQL 2 vCPU / 2 GiB; 100 VUs; 10 s warm-up, 30 s measured per workload; 1 repetition), run `2026-10-11_1244`, all eight stacks in one go with the Asia/Kolkata (`+05:30`) contract. 56 of 56 measured runs completed with zero failed requests; every stack passed 38/38 API checks and 29/29 auth checks. **Indicative only** (see [limitations](#14-limitations)).

Overall score (best stack per workload = 100, geometric mean over the 7 workloads): **Go 89.8**, Spring Boot 76.7, NestJS 75.7, Rust 74.6, Spring Boot Native 71.9, FastAPI 65.1, Laravel Octane 24.4, Laravel 7.8.

Throughput, successful requests per second:

| Workload | NestJS | Spring Boot | Go | Rust | FastAPI | Laravel | Laravel Octane | Spring Boot Native |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Health (no DB) | 55,593 | 42,808 | 61,494 | 54,047 | 67,009 | 1,464 | 6,009 | 43,532 |
| PK lookup | 29,202 | 27,380 | **40,362** | 27,922 | 15,477 | 1,293 | 4,793 | 23,723 |
| Range (50 rows) | 12,493 | 20,860 | **22,138** | 12,363 | 7,893 | 1,216 | 4,173 | 14,060 |
| Aggregate (stats) | 1,892 | 1,825 | 1,932 | 1,939 | 2,079 | 1,546 | **3,061** | 1,920 |
| Single insert | 16,288 | 14,236 | **18,161** | 13,457 | 13,379 | 1,317 | 4,610 | 11,846 |
| Batch insert (10) | 8,630 | 8,534 | 8,723 | 9,325 | 8,632 | 1,318 | 3,481 | **9,679** |
| Mixed | 11,928 | 13,058 | 12,646 | 12,831 | 11,410 | 1,249 | 3,896 | **14,026** |

Latency, ms (p50 / p95 / p99):

| Workload | NestJS | Spring Boot | Go | Rust | FastAPI | Laravel | Laravel Octane | Spring Boot Native |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PK lookup | 2.9 / 6.5 / 10.6 | 1.6 / 8.9 / 46.6 | 2.0 / 5.2 / 9.5 | 3.1 / 7.6 / 13.2 | 2.8 / 20.0 / 35.3 | 93.0 / 107.5 / 114.8 | 13.0 / 53.2 / 59.8 | 1.4 / 8.7 / 62.7 |
| Range list | 7.7 / 9.9 / 12.4 | 1.7 / 12.8 / 57.6 | 4.0 / 7.2 / 10.1 | 7.7 / 10.7 / 13.3 | 4.8 / 40.4 / 66.0 | 95.3 / 106.3 / 115.6 | 15.6 / 55.0 / 60.2 | 2.0 / 60.7 / 72.2 |
| Single insert | 4.6 / 21.9 / 29.1 | 3.8 / 39.3 / 48.9 | 4.1 / 15.1 / 27.7 | 4.7 / 32.6 / 40.9 | 7.0 / 16.4 / 23.8 | 92.8 / 101.9 / 105.9 | 17.0 / 42.2 / 46.4 | 3.6 / 53.4 / 65.3 |
| Mixed | 5.3 / 40.3 / 44.8 | 2.3 / 62.5 / 69.7 | 3.0 / 56.9 / 62.4 | 3.7 / 53.5 / 57.8 | 4.5 / 29.6 / 50.6 | 94.7 / 104.9 / 109.8 | 19.0 / 49.4 / 54.7 | 2.6 / 37.2 / 50.5 |

Cost per request (mixed workload):

| | NestJS | Spring Boot | Go | Rust | FastAPI | Laravel | Laravel Octane | Spring Boot Native |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| App CPU (cores of 2) | 1.34 | 1.43 | 0.84 | 0.94 | 2.01 | 2.01 | 2.03 | 2.04 |
| Requests per core | 8,884 | 9,108 | 15,020 | 13,714 | 5,670 | 623 | 1,921 | 6,877 |
| Peak memory (MiB) | 165 | 840 | 27 | 8 | 102 | 75 | 187 | 168 |
| Limiting resource | database CPU | database CPU | database CPU | database CPU | app CPU | app CPU | app CPU | app CPU |

Ramp (open model, `pk`, 4-CPU k6, 15 s steps from 250 to 48,000 req/s; "healthy" = last step with no errors or drops, "breaks" = first step that has them):

| Stack | Max load with p95 ≤ 0.5 ms | Max load with p95 ≤ 5 ms | Healthy up to | Breaks at | Peak served |
| --- | ---: | ---: | ---: | ---: | ---: |
| Go | 12,000 | 24,000 | 32,000 | 48,000 | 46,690 |
| Rust | 12,000 | 16,000 | 32,000 | 48,000 | 42,769 |
| NestJS | 8,000 | 24,000 | 32,000 | 48,000 | 39,773 |
| Spring Boot | 8,000 | 16,000 | 16,000 | 24,000 | 32,621 |
| Spring Boot Native | 6,000 | 16,000 | 16,000 | 24,000 | 24,357 |
| FastAPI | not reached (p95 1.98 ms at 250 req/s) | 8,000 | 16,000 | 24,000 | 16,750 |
| Laravel Octane | not reached | 4,000 | 4,000 | 6,000 | 4,999 |
| Laravel | not reached | 1,000 | 1,000 | 2,000 | 1,510 |

What the numbers mean:

- **Go leads where the framework matters** (PK lookup, range list, single insert) and has the best score, with the lowest p99 on reads and, with Rust, the smallest footprint (27 and 8 MiB). The lead is 1.06x to 1.4x over the next stack, not an order of magnitude.
- **Aggregate, batch insert and mixed are bound by PostgreSQL** (2 vCPU saturated) for the first five stacks, so they look alike or rank by how much DB work they cause. Differences of a few percent there are noise (one repetition).
- **Laravel Octane wins the aggregate test (3,061 req/s, 1.5x the next).** That is a database effect, not a framework one: it uses 4 DB connections against 20 for the others, and a saturated 2-vCPU PostgreSQL does less context switching with fewer sessions. Treat it as a hint to test the connection count, not as a PHP result.
- **Spring Boot on the JVM vs native**: native uses about 5x less memory (168 vs 840 MiB) and has the best p50 on reads, but it is 13% to 33% slower on read-heavy routes, has a worse tail (p99 63 to 72 ms) and breaks the p95 target earlier. Native wins the mixed workload by 7%, where the database is the limit. Details in [`docs/spring-jvm-vs-graalvm.md`](docs/spring-jvm-vs-graalvm.md).
- **Laravel (PHP-FPM) is CPU-bound by the framework itself**: about 1.3k req/s on every workload, even `/health`, at the 2-CPU quota with PostgreSQL almost idle (0.4 cores). **Octane** is 2.0x to 3.7x faster on database routes (4.1x on health) but still CPU-bound at the quota: the full Laravel kernel, router and middleware pipeline still run for every request. Details in [`docs/laravel-vs-octane.md`](docs/laravel-vs-octane.md).
- **Tail latency vs throughput**: Spring Boot has the best p50 on reads (1.6 ms) and one of the worst p99 (46.6 to 57.6 ms). FastAPI has the best mixed p95 (29.6 ms) while being fifth on throughput.
- On the cheap health route Go, Rust and NestJS did not reach their CPU quota (the load generator was the limit); FastAPI, Spring Boot, Laravel, Octane and Spring Native did, so FastAPI's 67k req/s there is the single highest number but says little about database work.

**Tuning notes.** [`docs/optimisation.md`](docs/optimisation.md) records what was tried to make each stack faster within the lab's rules. Kept: NestJS timestamp handling (range list +46%) and a prepared-statement-per-worker PDO path for Laravel Octane (+15% to +26%). Rejected after measuring: a FastAPI query-string shortcut, a hand-written Go JSON encoder, PHP JIT, and other GCs for Spring (G1 beats Parallel and Serial; Serial alone costs 23% to 49% on reads, which explains most of the native image's read-path gap). It also explains why changes must be compared with alternating runs: a sequential comparison on a laptop mislabelled three no-op changes as 3% to 12% regressions.

---

## 13. Bugs found while building this (and fixed)

Worth reading before writing your own benchmark: each of these distorted results until found.

| Problem | Symptom | Fix |
| --- | --- | --- |
| **k6 metric cardinality**: every unique URL (`/readings/123456`) becomes its own time series | k6 killed by OOM (exit 137) mid-run | tag requests `name=<workload>` |
| **pgxpool** `MaxConnLifetime = 0` and `MaxConnIdleTime = 0` mean "expire immediately", not "never" | Go: ~360 req/s, 11 % errors, PostgreSQL forking a backend per request (DB CPU 190 %) | set both to 24 h |
| **SQLx** `test_before_acquire` defaults to true: a ping round trip on every pool checkout | Rust ~40 % slower, database CPU higher | `test_before_acquire(false)` |
| **Go `net/http`** switches to chunked encoding for larger bodies | violates the "Content-Length always" rule | set the header explicitly |
| **Tomcat** closes a keep-alive connection after 100 requests | Spring pays reconnect cost | `max-keep-alive-requests=-1` |
| **Hikari** creates its pool lazily | warm-up code hit a null pool | open one connection first |
| **NestJS + Fastify** registers its own JSON parser | `FST_ERR_CTP_ALREADY_PRESENT` crash | `bodyParser: false` + own parser |
| **PostgreSQL healthcheck** via unix socket goes green while the init script is still seeding | apps started against a half-loaded database | `pg_isready -h 127.0.0.1` (TCP opens only after init) |
| **Hardware stalls**: macOS swapping with the Docker VM, or sleep | one 30 s test took 33 min of wall time | scripts run `caffeinate`, verify k6's clock, retry invalid runs |
| **Mixed workload**: operation chosen from the same counter as the device id | list requests only ever hit 30 % of devices | independent selection |
| **Spring AOT + `@ConditionalOnProperty`** is evaluated when the native image is built, not at startup | GraalVM image ignored `AUTH_MODE=jwt`: 10 of 29 auth checks failed | register the interceptor always, test the mode at runtime |
| **GraalVM community build** has no `MaxRAMPercentage` and ignores `JAVA_TOOL_OPTIONS` | container exited at start: `Could not find option 'MaxRAMPercentage'` | pass `-Xmx2600m` through `NATIVE_OPTS` |
| **nginx → PHP-FPM keep-alive** (`fastcgi_keep_conn`) binds each FPM worker to an idle nginx connection | Laravel: 0.5 % of requests hung until the 10 s timeout once kept connections outnumbered the 20 workers | no upstream keepalive |
| **Laravel sends no Content-Length** for small JSON bodies | nginx answered with chunked encoding | set the header explicitly |
| Dependency drift: `go mod tidy` wanted a newer toolchain; old Rust image rejected newer crates | image builds failed | commit `go.sum`, `Cargo.lock`; Rust image 1.98 |

Also noted: SQLx sends **two TCP packets per query** where pgx sends one (measured on the PostgreSQL container's NIC). This is a library behavior, not configurable, and costs a little CPU on both sides.

---

## 14. Limitations

- **Local-grade environment.** The load generator, database and application share one machine inside the Docker Desktop VM, with scheduling noise. Publication-grade numbers need a dedicated Linux host with CPU pinning (`cpuset`), `performance` CPU governor, k6 on separate hardware, and pinned image digests.
- **One repetition, 30 s runs.** No dispersion estimate; JIT-based runtimes would benefit from longer warm-up. Use `REPS`, `DURATION` and `WARMUP`.
- **Fixed stack order**, not randomized; each app also stays up across its seven workloads (a fixed order, identical for every stack).
- **Closed-loop 100-VU tests** hide behavior at fixed arrival rate; the ramp test complements them.
- **Resource sampling** uses `docker stats` (≈ 1–2 s granularity).
- The database has only **2 vCPU**: for several workloads it, not the application, is the bottleneck. A second tier with more database CPU would separate the frameworks further.
- Baseline tuning only: each stack uses sensible production defaults, not exhaustive per-framework tuning (virtual threads, Express, sync FastAPI, fasthttp, etc. are untested variants).

---

## 15. Configuration reference

`scripts/run-benchmark.sh` environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `STACKS` | `nest spring go rust fastapi laravel octane graalvm` | order of stacks |
| `WORKLOADS` | `health pk range stats insert batch mixed` | workloads per stack |
| `VUS` | `100` | virtual users |
| `WARMUP` | `10s` | warm-up per workload |
| `DURATION` | `30s` | measured duration |
| `REPS` | `1` | repetitions per cell |
| `RUN_ID` | `YYYY-MM-DD_HHMM[_LABEL]` | results folder name; reuse an existing one to add stacks |
| `LABEL` | – | suffix for the default run folder name |
| `AUTH_MODE` | `none` | `jwt` benchmarks the apps with HS256 bearer-token verification |

`scripts/run-ramp.sh`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `STACKS` | all eight | stacks to ramp |
| `WORKLOADS` | `pk` | `health pk range stats insert` |
| `RATES` | `250,500,…,48000` | offered req/s per step |
| `STEP_DUR` / `WARM_DUR` | `15` / `15` | seconds per step / warm-up |
| `MAX_VUS` | `1000` | k6 VU cap (iterations beyond it are dropped) |
| `P95_TARGET_MS` | `0.5` | latency threshold highlighted in the report |
| `K6_CPUS` / `K6_MEM` | `4.0` / `2g` | k6 container limits |

`.env`: `PLATFORM` (`linux/arm64` or `linux/amd64`; mismatching it forces slow emulation), `POSTGRES_IMAGE`, `K6_IMAGE`.

App environment (set by Compose): `PORT=8080`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_POOL_TOTAL=20`; Nest/FastAPI also `APP_WORKERS=2`, `DB_POOL_PER_WORKER=10`.

---

## 16. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `expected 1000000 rows` | Volume has stale data; `docker compose -f infra/compose.yaml down -v` and rerun (the scripts trim extra rows automatically). |
| Stack "never became healthy" | See `results/<run>/app-<stack>.log` and `build-<stack>.log`. |
| k6 exits with 137 | Out of memory in the k6 container: use tagged requests (already done) or raise `K6_MEM`. |
| Runs reported INVALID / very slow | Host or Docker VM is stalling (memory pressure, sleep). Close heavy apps, give Docker more RAM, keep the machine awake. |
| Exit code 99 from k6 | A threshold (errors > 1 % or checks < 99 %) was crossed; the report lists the cell. |
| Odd performance on Apple Silicon | `PLATFORM` in `.env` must be `linux/arm64`. |
| Smoke test fails for one stack | Details in `results/<run>/smoke-<stack>.txt`; the report marks that stack as not strictly comparable. |

---

## 17. Extending: add another stack

1. Create `apps/<name>/` with a multi-stage `Dockerfile` that serves the API on port 8080 and reads the standard `DB_*` variables; keep the pool at 20 connections total (min = max).
2. Add a service `app-<name>` with `profiles: [<name>]` and the shared limits (`<<: *app`) in `infra/compose.yaml`, plus a ports entry in `infra/compose.dev.yaml`.
3. Add the name to `STACKS` in the scripts, and to `STACKS` in `scripts/reporting/common.py` (name, description, colour slot, pool layout). That one table drives every report.
4. Run `RUN_ID=<existing> STACKS=<name> scripts/run-benchmark.sh`. The smoke test must pass 38/38 before the numbers mean anything.

Further reading: [`docs/implementation-plan.md`](docs/implementation-plan.md) (design rationale and fairness rules), [`docs/blueprint.md`](docs/blueprint.md) (original blueprint), [`api/openapi.yaml`](api/openapi.yaml).

---

## 18. Authentication (JWT)

All apps can verify an **HS256 bearer token** on every request. It is **off by default** (`AUTH_MODE=none`) so the standard benchmarks stay comparable; set `AUTH_MODE=jwt` to turn it on (`JWT_SECRET` defaults to `bench-jwt-secret-local-only`).

- **Scope:** `/readings*` requires `Authorization: Bearer <token>`; `/health` stays public; unknown routes stay 404.
- **Rules (identical in every stack):** `Bearer ` prefix; three non-empty segments; header `alg` must be `HS256` (so `alg: none` and RS256-header confusion are rejected); valid HMAC-SHA256 signature (constant-time compare); `exp` must be an integer in the future; `sub` must be a non-empty string. Verified on every request, never cached.
- **Failure:** `401 {"error":"unauthorized"}` plus `WWW-Authenticate: Bearer`. Auth is checked **before** body parsing, validation and the database, so a bad token never reaches PostgreSQL.
- **Implementation:** each stack uses its standard library crypto (Go `crypto/hmac`, Rust `hmac`+`sha2`, Node `crypto`, Java `javax.crypto.Mac`, Python `hmac`, PHP `hash_hmac`) and is only wired in when enabled (Gin route group, Axum `route_layer`, Nest guard, Spring `HandlerInterceptor`, FastAPI router dependency, Laravel and Laravel Octane route middleware), so the default mode has zero auth overhead.
- **No login endpoint:** tokens are minted by `scripts/jwt.py` (`valid`, `expired`, `badsig`, `wrongsecret`, `none`, `rs256`, `malformed`, `nosub`, `floatexp`).

**Tests**

```bash
scripts/run-auth-test.sh             # every stack: 29 auth checks + the 38-check API contract with a token + AUTH_MODE=none needs no token
AUTH_MODE=jwt LABEL=jwt scripts/run-benchmark.sh      # benchmark with auth on
python3 scripts/report.py auth results/benchmarks/<no-auth-run> results/benchmarks/<jwt-run>   # cost of auth
```

`scripts/smoke-auth.sh` covers: no header, empty bearer, wrong scheme, lowercase `bearer`, malformed token, bad signature, wrong secret, `alg: none`, RS256 header confusion, expired, missing `sub`, float `exp`; valid token on every route; **auth before validation** (bad query without token is 401, with token 422); **auth before body parsing**; unknown route 404 without a token; and that rejected writes insert nothing.

**Result:** all eight stacks pass 29/29 auth checks and 38/38 API checks with a token; with `AUTH_MODE=none` no token is needed. Cost on cheap routes is small: a back-to-back A/B of PK lookups (2 runs per mode) put JWT at 0–9 % for Rust and Go. Mixed workloads, bound by PostgreSQL, barely notice it. Single-run comparisons on this laptop swing by 20–40 %, so use the A/B approach (several alternating runs) before quoting an overhead figure.

Known gap: `JSON.parse` in NestJS cannot tell `exp: 1700000000.0` from an integer, so only non-integer values such as `1700000000.5` are rejected there.
