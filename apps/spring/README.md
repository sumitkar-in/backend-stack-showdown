# Spring Boot backend

Spring Boot 3.4 MVC (Tomcat, 200 threads) + `JdbcTemplate` + HikariCP (20 connections, min = max, awaited at startup) + PostgreSQL JDBC (`prepareThreshold=1`). Java 21, G1, no virtual threads.

- Raw parameterized SQL, no JPA/Hibernate. Records are serialized with Jackson to `byte[]`, so `Content-Length` is always set.
- Bodies arrive as raw bytes: malformed JSON -> 400, then strict validation (`isIntegralNumber`, so `2375.0` is rejected) -> 422.
- `@RestControllerAdvice` normalizes all errors; unknown routes/methods -> 404.
- `server.tomcat.max-keep-alive-requests=-1` (Tomcat's default of 100 would recycle connections and penalize this stack).
- Compose sets `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=65 -XX:ActiveProcessorCount=2`.
- JIT needs a longer warm-up than the others; use the uniform 60 s warm-up from the plan.

Layout: `config/` (pool warm-up), `db/` (SQL, repository), `model/` (records), `support/` (timestamps), `web/` (controllers, validation, errors).

Run: `docker compose -f infra/compose.yaml --profile spring up -d --build app-spring`
