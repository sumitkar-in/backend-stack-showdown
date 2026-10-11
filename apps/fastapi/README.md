# FastAPI backend

FastAPI + Uvicorn (2 workers, uvloop/httptools) + asyncpg (pool 10 per worker = 20 total) + orjson.

- Raw parameterized SQL, asyncpg's automatic prepared-statement cache, no ORM, no `response_model`.
- Request handling is two-stage: malformed JSON -> 400, then manual strict validation -> 422 (see `docs/implementation-plan.md` 3.3).
- Docs endpoints, access log and reload are disabled.
- Pool size is asserted at startup: `DB_POOL_PER_WORKER * APP_WORKERS == DB_POOL_TOTAL`.
- Dependencies are pinned in `requirements.txt` (no hash pinning yet).

Run: `docker compose -f infra/compose.yaml --profile fastapi up -d --build app-fastapi`
