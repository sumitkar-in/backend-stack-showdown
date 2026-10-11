# NestJS backend

NestJS 10 + Fastify adapter (logger off) + `pg`. Node `cluster`: 2 workers, each with its own pool of 10 (20 total, min = max, opened at startup).

- Raw parameterized SQL via named (prepared) queries; no ORM, no class-validator.
- Fastify's JSON parser is replaced by a raw-buffer parser; the service parses and validates itself (malformed -> 400, invalid -> 422).
- One global exception filter normalizes all errors to `{"error": ...}`; unknown routes/methods -> 404.
- A worker crash exits the primary with code 1 (run invalid) instead of respawning.
- Known limitation: `JSON.parse` cannot distinguish `2375.0` from `2375`; only non-integer numbers (2375.5) are rejected.
- `package-lock.json` is created by the first build; commit it to pin transitive deps.

Run: `docker compose -f infra/compose.yaml --profile nest up -d --build app-nest`
