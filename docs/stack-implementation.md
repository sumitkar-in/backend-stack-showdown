# Stack-by-stack Implementation Responsibilities

Implement **the same 6 routes** defined in README and run identical SQL templates. Every app must listen on 0.0.0.0:8080, derive configuration from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME, expose production logging, use parameterized SQL and shut down pool gracefully on SIGTERM.

| App folder | Implementation notes | Connection pool |
| --- | --- | --- |
| `apps/go` | `gin-gonic/gin`, `jackc/pgx/v5/pgxpool`; `GOMAXPROCS=2`; map PG row types and Asia/Kolkata (+05:30) milliseconds explicitly; single release binary | 20 globally |
| `apps/spring` | Spring Boot MVC, Spring JDBC `JdbcTemplate`/`NamedParameterJdbcTemplate`, HikariCP; avoid JPA or Hibernate; identical validated DTOs; JVM processor count 2, Tomcat request threads capped at 200 | 20 globally |
| `apps/nest` | `@nestjs/platform-fastify`, `pg`, common controller/service, schema validators and explicit error normalization; Node cluster with two worker processes; each creates own PG pool | 10 per worker × 2 |
| `apps/fastapi` | async `FastAPI`, `asyncpg.create_pool` on lifespan startup; `await` per query; Uvicorn `--workers 2`; explicit Pydantic response normalization; avoid synchronous pool inside async routes | 10 per worker × 2 |
| `apps/rust` | Axum 0.8-style router (pin implementation version), Tokio 2-worker runtime, SQLx Postgres pool and `serde` JSON; release optimizations and no SQL ORM helpers | 20 globally |

## Exact SQL behavior

- A single create executes one parameterized INSERT RETURNING and serializes the result.
- Ten-item batch is one SQL INSERT with 10 parameterized groups, all-or-nothing; general endpoint supports 1–100 records.
- Primary-key GET is one SQL SELECT by id.
- Device/time GET is one SELECT with WHERE device/time, ORDER BY observed_at DESC,id DESC, LIMIT/OFFSET; **do not query COUNT(*) for pagination**.
- Stats is one aggregate SELECT with COUNT, SUM, MIN, MAX; not application-side iteration through records.
- Health must not acquire a DB connection.

## Production build requirements

- Multi-stage Dockerfile, only production runtime artifacts in the final image.
- Lockfiles / dependencies pinned to exact versions; record SHA256/image digest in each run's manifest.
- `PORT=8080`, `DB_POOL_TOTAL=20` (Nest/Python split into per-worker limits).
- Disable access logging, auto-reload and debug for benchmark runs. Use JSON serialization with Asia/Kolkata (+05:30) millisecond format, without gzip.
- HTTP keep-alive on, connection timeouts recorded, max body allows 100 readings.
- For process comparisons, give all stacks their normal optimized production setting; do not switch one framework to an artificially crippled configuration in the name of symmetry. Always disclose configuration differences.
