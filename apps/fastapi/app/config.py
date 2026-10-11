import os

DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "sensorpulse")
DB_USER = os.environ.get("DB_USER", "bench")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

DB_POOL_TOTAL = int(os.environ.get("DB_POOL_TOTAL", "20"))
DB_POOL_PER_WORKER = int(os.environ.get("DB_POOL_PER_WORKER", "10"))
APP_WORKERS = int(os.environ.get("APP_WORKERS", "2"))

if DB_POOL_PER_WORKER * APP_WORKERS != DB_POOL_TOTAL:
    raise RuntimeError(
        f"pool mismatch: {DB_POOL_PER_WORKER} x {APP_WORKERS} workers != DB_POOL_TOTAL={DB_POOL_TOTAL}"
    )

AUTH_MODE = os.environ.get("AUTH_MODE", "none")
JWT_SECRET = os.environ.get("JWT_SECRET", "bench-jwt-secret-local-only").encode()
