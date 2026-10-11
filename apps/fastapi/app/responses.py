from fastapi.responses import Response

JSON = "application/json"

HEALTH = b'{"status":"ok"}'
ERR_400 = b'{"error":"bad_request"}'
ERR_404 = b'{"error":"not_found"}'
ERR_401 = b'{"error":"unauthorized"}'
ERR_422 = b'{"error":"validation_error"}'
ERR_500 = b'{"error":"internal"}'


def reply(body: bytes, status: int = 200) -> Response:
    return Response(content=body, status_code=status, media_type=JSON)


def bad_request() -> Response:
    return reply(ERR_400, 400)


def not_found() -> Response:
    return reply(ERR_404, 404)


def invalid() -> Response:
    return reply(ERR_422, 422)
