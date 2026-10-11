# Rust backend

Axum 0.8 (HTTP/1 only) + Tokio multi-thread runtime (2 worker threads) + SQLx 0.8 (runtime queries, no macros/ORM). Pool: 20 connections, min = max, all opened at startup.

- Raw parameterized SQL; SQLx's per-connection statement cache prepares the fixed queries.
- Bodies are taken as raw bytes: malformed JSON -> 400, then strict validation (`as_i64`, so `2375.0` is rejected) -> 422.
- `TCP_NODELAY` is enabled to match the other stacks' defaults.
- Release profile: `opt-level=3`, fat LTO, `codegen-units=1`, `panic=abort`, stripped. No `target-cpu=native`.
- SIGTERM drains in-flight requests (max 10 s) and closes the pool. `Cargo.lock` is pinned; builds use `--locked`.

Layout: `main.rs`, `config.rs`, `db.rs`, `sql.rs`, `validate.rs`, `models.rs`, `respond.rs`, `handlers.rs`.

Run: `docker compose -f infra/compose.yaml --profile rust up -d --build app-rust`
