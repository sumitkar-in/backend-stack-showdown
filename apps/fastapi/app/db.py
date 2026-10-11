from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from . import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """One fixed-size pool per worker process (min == max, no growth under load)."""
    app.state.pool = await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        min_size=config.DB_POOL_PER_WORKER,
        max_size=config.DB_POOL_PER_WORKER,
        command_timeout=10,
        max_inactive_connection_lifetime=0,
    )
    try:
        yield
    finally:
        await app.state.pool.close()
