BY_ID = (
    "SELECT id, device_id, temperature_centi, humidity_bp, observed_at "
    "FROM readings WHERE id = $1"
)
LIST = (
    "SELECT id, device_id, temperature_centi, humidity_bp, observed_at "
    "FROM readings "
    "WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3 "
    "ORDER BY observed_at DESC, id DESC LIMIT $4 OFFSET $5"
)
STATS = (
    "SELECT COUNT(*)::bigint AS count, "
    "COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, "
    "COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, "
    "MIN(temperature_centi) AS temperature_min_centi, "
    "MAX(temperature_centi) AS temperature_max_centi "
    "FROM readings WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3"
)
INSERT = (
    "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) "
    "VALUES ($1, $2, $3, $4) "
    "RETURNING id, device_id, temperature_centi, humidity_bp, observed_at"
)

_BATCH_HEAD = "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES "
_batch_cache: dict[int, str] = {}


def batch_insert(n: int) -> str:
    """Single multi-row INSERT with n parameter groups (atomic), cached per size."""
    sql = _batch_cache.get(n)
    if sql is None:
        groups = ",".join(
            f"(${i * 4 + 1},${i * 4 + 2},${i * 4 + 3},${i * 4 + 4})" for i in range(n)
        )
        sql = _batch_cache[n] = _BATCH_HEAD + groups
    return sql
