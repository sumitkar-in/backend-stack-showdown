"""Strict, hand-written validation. Every function returns None when input is invalid."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

IST = timezone(timedelta(hours=5, minutes=30))

_RE_ID = re.compile(r"[1-9][0-9]{0,17}")
_RE_DEVICE = re.compile(r"[1-9][0-9]{0,8}")
_RE_UINT = re.compile(r"[0-9]{1,4}")
_RE_TS = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,3})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)


def parse_ts(value) -> datetime | None:
    """RFC3339 with timezone and at most 3 fractional digits -> aware Asia/Kolkata datetime."""
    if not isinstance(value, str) or not _RE_TS.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(IST)
    except ValueError:
        return None


def _single(params, name: str) -> str | None:
    values = params.getlist(name)
    return values[0] if len(values) == 1 else None


def reading_id(raw: str) -> int | None:
    return int(raw) if _RE_ID.fullmatch(raw) else None


def device_range(params):
    """deviceId + from/to query -> (device, from, to) or None."""
    dev = _single(params, "deviceId")
    ts_from = parse_ts(_single(params, "from"))
    ts_to = parse_ts(_single(params, "to"))
    if dev is None or not _RE_DEVICE.fullmatch(dev):
        return None
    if ts_from is None or ts_to is None or ts_from >= ts_to:
        return None
    return int(dev), ts_from, ts_to


def paging(params):
    """limit (1-100, default 50) and offset (0-1000, default 0) -> (limit, offset) or None."""
    lim = _single(params, "limit") if "limit" in params else "50"
    off = _single(params, "offset") if "offset" in params else "0"
    if lim is None or off is None:
        return None
    if not _RE_UINT.fullmatch(lim) or not _RE_UINT.fullmatch(off):
        return None
    limit, offset = int(lim), int(off)
    if not 1 <= limit <= 100 or offset > 1000:
        return None
    return limit, offset


def _is_int(v) -> bool:
    return type(v) is int  # rejects bool and float


def reading_payload(obj):
    """Body of a single reading -> (device, temp, humidity, observed_at) or None."""
    if not isinstance(obj, dict):
        return None
    d, t, h = obj.get("deviceId"), obj.get("temperatureCenti"), obj.get("humidityBp")
    if not (_is_int(d) and _is_int(t) and _is_int(h)):
        return None
    if not 1 <= d <= 2147483647 or not -5000 <= t <= 10000 or not 0 <= h <= 10000:
        return None
    ts = parse_ts(obj.get("observedAt"))
    return None if ts is None else (d, t, h, ts)


def batch_payload(obj) -> list | None:
    """Flat asyncpg args for 1-100 readings, or None if any is invalid."""
    items = obj.get("readings") if isinstance(obj, dict) else None
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        return None
    args: list = []
    for item in items:
        vals = reading_payload(item)
        if vals is None:
            return None
        args.extend(vals)
    return args
