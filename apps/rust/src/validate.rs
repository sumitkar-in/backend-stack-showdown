use std::sync::LazyLock;

use regex::Regex;
use serde_json::Value;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

use crate::respond::ApiError;

static RE_ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[1-9][0-9]{0,17}$").unwrap());
static RE_DEVICE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[1-9][0-9]{0,8}$").unwrap());
static RE_UINT: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[0-9]{1,4}$").unwrap());
static RE_TS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,3})?(Z|[+-][0-9]{2}:[0-9]{2})$")
        .unwrap()
});

pub type QueryPairs = [(String, String)];

/// RFC3339 with timezone and at most 3 fractional digits.
pub fn parse_ts(s: &str) -> Option<OffsetDateTime> {
    if !RE_TS.is_match(s) {
        return None;
    }
    OffsetDateTime::parse(s, &Rfc3339).ok()
}

/// Query value only when the parameter appears exactly once.
fn single<'a>(q: &'a QueryPairs, name: &str) -> Option<&'a str> {
    let mut it = q.iter().filter(|(k, _)| k == name);
    match (it.next(), it.next()) {
        (Some((_, v)), None) => Some(v.as_str()),
        _ => None,
    }
}

pub fn parse_id(raw: &str) -> Result<i64, ApiError> {
    if !RE_ID.is_match(raw) {
        return Err(ApiError::Invalid);
    }
    raw.parse().map_err(|_| ApiError::Invalid)
}

pub struct DeviceRange {
    pub device: i32,
    pub from: OffsetDateTime,
    pub to: OffsetDateTime,
}

pub fn parse_device_range(q: &QueryPairs) -> Result<DeviceRange, ApiError> {
    let dev = single(q, "deviceId").filter(|d| RE_DEVICE.is_match(d)).ok_or(ApiError::Invalid)?;
    let from = single(q, "from").and_then(parse_ts).ok_or(ApiError::Invalid)?;
    let to = single(q, "to").and_then(parse_ts).ok_or(ApiError::Invalid)?;
    if from >= to {
        return Err(ApiError::Invalid);
    }
    Ok(DeviceRange { device: dev.parse().map_err(|_| ApiError::Invalid)?, from, to })
}

/// limit 1-100 (default 50), offset 0-1000 (default 0).
pub fn parse_paging(q: &QueryPairs) -> Result<(i64, i64), ApiError> {
    let get = |name: &str, default: &'static str| -> Result<i64, ApiError> {
        let raw = if q.iter().any(|(k, _)| k == name) { single(q, name).ok_or(ApiError::Invalid)? } else { default };
        if !RE_UINT.is_match(raw) {
            return Err(ApiError::Invalid);
        }
        raw.parse().map_err(|_| ApiError::Invalid)
    };
    let (limit, offset) = (get("limit", "50")?, get("offset", "0")?);
    if !(1..=100).contains(&limit) || offset > 1000 {
        return Err(ApiError::Invalid);
    }
    Ok((limit, offset))
}

/// Stage 1: malformed JSON -> 400.
pub fn parse_json(body: &[u8]) -> Result<Value, ApiError> {
    serde_json::from_slice(body).map_err(|_| ApiError::BadRequest)
}

pub struct NewReading {
    pub device_id: i32,
    pub temperature_centi: i16,
    pub humidity_bp: i16,
    pub observed_at: OffsetDateTime,
}

fn int_field(o: &serde_json::Map<String, Value>, key: &str, lo: i64, hi: i64) -> Option<i64> {
    // as_i64 is None for 2375.0 / 1e3 / strings / bools / null => strict integers only.
    o.get(key)?.as_i64().filter(|v| (lo..=hi).contains(v))
}

/// Stage 2: one reading object, or None when invalid (-> 422).
pub fn new_reading(v: &Value) -> Option<NewReading> {
    let o = v.as_object()?;
    Some(NewReading {
        device_id: int_field(o, "deviceId", 1, 2_147_483_647)? as i32,
        temperature_centi: int_field(o, "temperatureCenti", -5000, 10000)? as i16,
        humidity_bp: int_field(o, "humidityBp", 0, 10000)? as i16,
        observed_at: parse_ts(o.get("observedAt")?.as_str()?)?,
    })
}

/// 1-100 valid readings, or None.
pub fn batch(v: &Value) -> Option<Vec<NewReading>> {
    let items = v.as_object()?.get("readings")?.as_array()?;
    if !(1..=100).contains(&items.len()) {
        return None;
    }
    items.iter().map(new_reading).collect()
}
