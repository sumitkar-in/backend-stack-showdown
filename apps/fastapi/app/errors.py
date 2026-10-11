from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException

from .auth import Unauthorized
from .responses import ERR_401, ERR_404, ERR_500, reply


def register(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        return reply(ERR_404, 404)  # unknown route / wrong method -> not_found

    @app.exception_handler(Unauthorized)
    async def _unauthorized(request: Request, exc: Unauthorized):
        resp = reply(ERR_401, 401)
        resp.headers["WWW-Authenticate"] = "Bearer"
        return resp

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):
        return reply(ERR_500, 500)
