from fastapi import FastAPI

from . import errors
from .db import lifespan
from .routes import health, readings

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
errors.register(app)
app.include_router(health.router)
app.include_router(readings.router)
