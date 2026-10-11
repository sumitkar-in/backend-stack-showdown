from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))  # India has no DST: a fixed offset is exact


def fmt_ts(dt: datetime) -> str:
    """Asia/Kolkata (+05:30), exactly 3 fractional digits."""
    dt = dt.astimezone(IST)
    return f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}+05:30"


def reading(row) -> dict:
    return {
        "id": row["id"],
        "deviceId": row["device_id"],
        "temperatureCenti": row["temperature_centi"],
        "humidityBp": row["humidity_bp"],
        "observedAt": fmt_ts(row["observed_at"]),
    }


def stats(device_id: int, row) -> dict:
    return {
        "deviceId": device_id,
        "count": row["count"],
        "temperatureSumCenti": row["temperature_sum_centi"],
        "humiditySumBp": row["humidity_sum_bp"],
        "temperatureMinCenti": row["temperature_min_centi"],
        "temperatureMaxCenti": row["temperature_max_centi"],
    }
