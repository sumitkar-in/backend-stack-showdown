"""HS256 bearer-token verification.

Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
valid HMAC-SHA256 signature, integer exp in the future, non-empty sub. Verified on every request (no cache).
"""
import base64
import hashlib
import hmac
import re
import time

import orjson
from fastapi import Request

from . import config

_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class Unauthorized(Exception):
    pass


def _b64d(s: str) -> bytes:
    if not _B64URL.match(s):
        raise ValueError
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(header: str | None) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    parts = header[7:].split(".")
    if len(parts) != 3 or not all(parts):
        return False
    h, p, s = parts
    try:
        sig = _b64d(s)
        expected = hmac.new(config.JWT_SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return False
        hdr = orjson.loads(_b64d(h))
        if not isinstance(hdr, dict) or hdr.get("alg") != "HS256":
            return False
        claims = orjson.loads(_b64d(p))
    except (ValueError, orjson.JSONDecodeError):
        return False
    if not isinstance(claims, dict):
        return False
    sub, exp = claims.get("sub"), claims.get("exp")
    return isinstance(sub, str) and sub != "" and type(exp) is int and exp > time.time()


async def require_jwt(request: Request) -> None:
    if not verify(request.headers.get("authorization")):
        raise Unauthorized
