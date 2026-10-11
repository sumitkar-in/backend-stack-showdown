import asyncpg
import orjson
from fastapi import APIRouter, Depends, Request

from .. import config, serializers, sql, validation
from ..auth import require_jwt
from ..responses import bad_request, invalid, not_found, reply

# The dependency exists only when AUTH_MODE=jwt, so the default mode has zero auth overhead.
router = APIRouter(dependencies=[Depends(require_jwt)] if config.AUTH_MODE == "jwt" else [])

_CONSTRAINT_ERRORS = (asyncpg.ForeignKeyViolationError, asyncpg.CheckViolationError)


async def _json_body(request: Request):
    """Parsed body, or None for malformed JSON (-> 400)."""
    try:
        return orjson.loads(await request.body())
    except orjson.JSONDecodeError:
        return None


# /readings/stats must be registered before /readings/{rid}
@router.get("/readings/stats")
async def stats(request: Request):
    parsed = validation.device_range(request.query_params)
    if parsed is None:
        return invalid()
    device, ts_from, ts_to = parsed
    row = await request.app.state.pool.fetchrow(sql.STATS, device, ts_from, ts_to)
    return reply(orjson.dumps(serializers.stats(device, row)))


@router.get("/readings/{rid}")
async def get_reading(rid: str, request: Request):
    reading_id = validation.reading_id(rid)
    if reading_id is None:
        return invalid()
    row = await request.app.state.pool.fetchrow(sql.BY_ID, reading_id)
    if row is None:
        return not_found()
    return reply(orjson.dumps(serializers.reading(row)))


@router.get("/readings")
async def list_readings(request: Request):
    parsed = validation.device_range(request.query_params)
    page = validation.paging(request.query_params)
    if parsed is None or page is None:
        return invalid()
    rows = await request.app.state.pool.fetch(sql.LIST, *parsed, *page)
    return reply(
        orjson.dumps(
            {
                "items": [serializers.reading(r) for r in rows],
                "limit": page[0],
                "offset": page[1],
            }
        )
    )


@router.post("/readings")
async def create_reading(request: Request):
    body = await _json_body(request)
    if body is None:
        return bad_request()
    vals = validation.reading_payload(body)
    if vals is None:
        return invalid()
    try:
        row = await request.app.state.pool.fetchrow(sql.INSERT, *vals)
    except _CONSTRAINT_ERRORS:
        return invalid()
    return reply(orjson.dumps(serializers.reading(row)), 201)


@router.post("/readings/batch")
async def create_batch(request: Request):
    body = await _json_body(request)
    if not isinstance(body, dict):
        return bad_request()
    args = validation.batch_payload(body)
    if args is None:
        return invalid()
    count = len(args) // 4
    try:
        await request.app.state.pool.execute(sql.batch_insert(count), *args)
    except _CONSTRAINT_ERRORS:
        return invalid()
    return reply(orjson.dumps({"inserted": count}), 201)
