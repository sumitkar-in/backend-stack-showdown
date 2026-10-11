# Spring Boot (GraalVM native image) backend

The same Spring Boot 3.4 app as `apps/spring` (Tomcat MVC, `JdbcTemplate`, HikariCP 20 connections, PostgreSQL JDBC with `prepareThreshold=1`, same SQL, validation and error contract), compiled ahead of time with GraalVM `native-image` into a single executable. No JVM, no JIT, no warm-up compilation.

- **Build.** Multi-stage Dockerfile: `ghcr.io/graalvm/native-image-community:21` runs `mvn -Pnative native:compile` (the `native` profile comes from `spring-boot-starter-parent`; Maven is copied from the Maven image). The native step needs roughly 6+ GiB of RAM and several minutes; first build is slow.
- **Runtime.** `debian:bookworm-slim` (+ `zlib1g`), non-root, executable started through `sh -c 'exec /app/sensorpulse $NATIVE_OPTS'`. Native images ignore `JAVA_TOOL_OPTIONS`, so compose passes `NATIVE_OPTS=-Xmx2600m` (about 65% of the 4 GiB limit; the community build has no `MaxRAMPercentage`)`.
- **GC.** Community native images ship the Serial GC (`--gc=serial`), not G1. Pauses are stop-the-world on one thread, which matters for tail latency under load. CPU count is read from the container quota (2 vCPU).
- **Optimisation.** `-O2`, no PGO, so peak throughput can be below the JIT build once it is fully warmed; startup and memory are far better.
- **Reflection.** `Json.respond()` serializes the model records with a plain `ObjectMapper`, which Spring AOT cannot see, so `SensorPulseApplication` registers them with `@RegisterReflectionForBinding`.
- **Everything else** (Tomcat 200 threads, unlimited keep-alive, pool warm-up before readiness, JWT interceptor) is unchanged from `apps/spring`.

Run: `docker compose -f infra/compose.yaml --profile graalvm up -d --build app-graalvm`
Benchmark: included in the default `STACKS` as `graalvm` (`STACKS=graalvm scripts/run-benchmark.sh` to run it alone).
