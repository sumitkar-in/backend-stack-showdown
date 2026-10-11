# Go backend

Gin (release mode, no access log) + pgx v5 `pgxpool` (20 connections, min = max, opened at startup) + `encoding/json`.

- Raw parameterized SQL; pgx's default statement cache prepares the fixed queries. No ORM.
- Two-stage body handling: malformed JSON -> 400, then strict validation -> 422. Integers are checked via `json.Number`, so `2375.0` and `1e3` are rejected.
- `Content-Length` is always set (no chunked responses).
- `GOMAXPROCS=2` in the image; SIGTERM drains in-flight requests (10 s) and closes the pool.
- `go.sum` is committed and pins all dependencies.

Layout: `main.go` (server), `config.go`, `db.go` (pool), `sql.go`, `validate.go`, `models.go`, `respond.go`, `handlers.go`.

Run: `docker compose -f infra/compose.yaml --profile go up -d --build app-go`
