# Spring Boot on the JVM vs Spring Boot as a GraalVM native image

The same Spring Boot 3.4 application (Tomcat MVC with 200 threads, `JdbcTemplate`, HikariCP with 20 connections, PostgreSQL JDBC with `prepareThreshold=1`, identical SQL, validation, error contract and JWT interceptor) built two ways:

- **JVM** (`apps/spring`): Java 21 on `eclipse-temurin:21-jre`, G1 GC, JIT-compiled at run time.
- **Native** (`apps/spring-with-graalvm`): the same sources compiled ahead of time by GraalVM `native-image` into one executable on `debian:bookworm-slim`.

Source: run `2026-10-11_1244` (local Docker on an Apple Silicon Mac, 100 constant VUs, 10 s warm-up, 30 s measured, 1 repetition, app 2 vCPU / 4 GiB, PostgreSQL 2 vCPU / 2 GiB; all eight stacks in one run). **Indicative only**: one local run, no dispersion estimate, a 10 s warm-up that is short for a JIT.

## 1. What differs

| | JVM | Native image |
| --- | --- | --- |
| Compilation | bytecode, JIT (C1/C2) after warm-up | ahead of time, `-O2`, no JIT, no PGO |
| GC | G1 | Serial (the only full GC in the community build) |
| Memory flags | `-XX:MaxRAMPercentage=65`, `-XX:ActiveProcessorCount=2` via `JAVA_TOOL_OPTIONS` | `-Xmx2600m` via `NATIVE_OPTS` (`JAVA_TOOL_OPTIONS` is ignored; `MaxRAMPercentage` does not exist) |
| Reflection | resolved at run time | fixed at build time; the model records are registered with `@RegisterReflectionForBinding` because `Json.respond()` serializes them with a plain `ObjectMapper` |
| Conditional beans | `@ConditionalOnProperty` evaluated at startup | evaluated when the image is built, so the JWT interceptor is always registered and enabled at run time (`app.auth.mode`) |
| Build | `mvn package`, about 1 min | `mvn -Pnative native:compile`, several minutes and about 6 GiB of RAM |
| Image size | 530 MB | 253 MB |
| Startup | about 2 s to healthy | about 1 s to healthy |

Identical: routes, SQL, Hikari pool (20, awaited at startup), Tomcat keep-alive settings, 38 API checks, 29 auth checks.

## 2. Throughput (successful req/s, higher is better)

| Workload | JVM | Native | Native vs JVM | JVM limit | Native limit |
| --- | ---: | ---: | ---: | --- | --- |
| Health (no DB) | 42,808 | 43,532 | +2% | app CPU | app CPU |
| PK lookup | 27,380 | 23,723 | -13% | app CPU | app CPU |
| Range list (50 rows) | 20,860 | 14,060 | -33% | app CPU | app CPU |
| Aggregate | 1,825 | 1,920 | +5% | database CPU | database CPU |
| Single insert | 14,236 | 11,846 | -17% | app CPU | app CPU |
| Batch insert (10) | 8,534 | 9,679 | +13% | database CPU | app CPU |
| Mixed | 13,058 | 14,026 | +7% | database CPU | app CPU |

Native is ahead only where PostgreSQL is the limit or the app does almost nothing (health, aggregate, batch, mixed). On read routes that spend their time in Spring MVC, Jackson and JDBC (PK lookup -13%, range list -33%) and on single inserts (-17%) the JIT-compiled JVM is faster: with a warmed JIT it inlines the hot path more aggressively than a static `-O2` compile, and without profile-guided optimisation the native image cannot close that gap.

## 3. Latency (ms, p50 / p95 / p99, lower is better)

| Workload | JVM | Native |
| --- | --- | --- |
| Health (no DB) | 1.7 / 6.2 / 11.5 | 1.3 / 4.7 / 31.6 |
| PK lookup | 1.6 / 8.9 / 46.6 | 1.4 / 8.7 / 62.7 |
| Range list (50 rows) | 1.7 / 12.8 / 57.6 | 2.0 / 60.7 / 72.2 |
| Aggregate | 84.6 / 105.0 / 190.9 | 28.0 / 106.4 / 189.8 |
| Single insert | 3.8 / 39.3 / 48.9 | 3.6 / 53.4 / 65.3 |
| Batch insert (10) | 5.4 / 55.7 / 65.2 | 5.3 / 42.8 / 56.1 |
| Mixed | 2.3 / 62.5 / 69.7 | 2.6 / 37.2 / 50.5 |

Native has the best median on reads (1.4 ms on PK lookups) but a worse tail: p99 of 62.7 ms on PK and 72.2 ms on range lists, against 46.6 and 57.6 ms for the JVM. The Serial GC is the likely cause, and an experiment supports it: running the JVM build itself with `-XX:+UseSerialGC` (3 runs each, same machine) cost 23% on PK lookups and 49% on range lists against G1, with a similar p99, while using about 40% less memory (see [`optimisation.md`](optimisation.md)). A collection stops every thread, while G1 works in parallel on the 2 vCPUs. The JVM's own tail is already high (it has the worst p99 of the mature stacks), so neither is a good choice for strict tail-latency targets at this load.

## 4. CPU and memory

| Workload | JVM CPU | Native CPU | JVM req/core | Native req/core | JVM MiB | Native MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Health (no DB) | 2.04 | 2.03 | 20,957 | 21,396 | 518 | 150 |
| PK lookup | 2.06 | 2.03 | 13,278 | 11,678 | 522 | 173 |
| Range list (50 rows) | 2.03 | 2.02 | 10,251 | 6,950 | 835 | 295 |
| Aggregate | 0.32 | 0.46 | 5,769 | 4,187 | 835 | 127 |
| Single insert | 2.12 | 2.09 | 6,707 | 5,663 | 839 | 175 |
| Batch insert (10) | 1.44 | 1.99 | 5,936 | 4,873 | 839 | 198 |
| Mixed | 1.43 | 2.04 | 9,108 | 6,877 | 840 | 168 |

The memory gap is the headline: about 130 to 300 MiB for native against 520 to 840 MiB for the JVM, roughly 3x to 5x less, in a container limited to 4 GiB. The JVM sizes its heap to 65% of the limit and keeps it; the native image stays near its live set. Per CPU core the JVM is more efficient on reads (13,278 vs 11,678 req/core on PK lookups) and on the mixed workload when the database does not saturate (9,108 vs 6,877).

## 5. Open-model ramp (PK lookup)

| | JVM | Native |
| --- | ---: | ---: |
| Max load with p95 ≤ 0.5 ms | 8,000 req/s | 6,000 req/s |
| Max load with p95 ≤ 5 ms | 16,000 req/s | 16,000 req/s |
| Healthy up to | 16,000 req/s | 16,000 req/s |
| First step with errors or drops | 24,000 req/s | 24,000 req/s |
| Peak served | 32,621 req/s | 24,357 req/s |

Both break at the same step, but the JVM keeps serving more requests beyond it (about 34% more at its peak), consistent with the throughput table.

## 6. When to pick which

- **Native** when memory, container density or cold start matter: serverless, many small replicas, short-lived jobs, or a database-bound service where the framework is not the bottleneck (aggregate, batch and mixed here).
- **JVM** when sustained throughput and tail latency on CPU-bound routes matter and the process is long-lived enough for the JIT to warm up.
- Neither beats Go or Rust on cost per request at this size: Go serves about 15,000 req/s per core on the mixed workload, against 9,100 (JVM) and 6,900 (native).

## 7. Things that went wrong while adding native support

| Problem | Symptom | Fix |
| --- | --- | --- |
| `@ConditionalOnProperty(app.auth.mode=jwt)` is resolved during AOT processing, when `AUTH_MODE` is not set | the native image never registered the JWT interceptor: 10 of 29 auth checks failed | always register `AuthConfig`, enable the interceptor from `app.auth.mode` at run time |
| `-XX:MaxRAMPercentage` and `JAVA_TOOL_OPTIONS` do not exist in the community native image | container exited at start with `Could not find option 'MaxRAMPercentage'` | pass `-Xmx2600m` through `NATIVE_OPTS` |
| Records serialized by a plain `ObjectMapper` are invisible to Spring AOT | risk of empty or failing JSON at run time | `@RegisterReflectionForBinding` on the five model records |

## 8. Limitations and what was not tried

One local machine with the load generator, database and app sharing it; 1 repetition; 30 s runs and a 10 s warm-up, which favours native (no warm-up needed) over the JVM; closed-loop load for the main table. Not tried: Oracle GraalVM (G1 and PGO, which would likely close much of the throughput gap and improve the tail), `-march=native` or `-O3` builds, tuning `-Xmn`, ParallelGC or ZGC on the JVM, a longer warm-up for the JVM, virtual threads.

## 9. Reproduce

```bash
# both Spring variants, benchmark only
STACKS="spring graalvm" scripts/run-benchmark.sh

# add native to an existing run
RUN_ID=2026-10-11_1244 STACKS=graalvm scripts/run-benchmark.sh

# build and run the native image by hand
docker compose -f infra/compose.yaml -f infra/compose.dev.yaml --profile graalvm up -d --build app-graalvm
curl -s localhost:8080/readings/1
```
