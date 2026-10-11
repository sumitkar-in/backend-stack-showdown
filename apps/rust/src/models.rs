use serde::Serialize;
use sqlx::postgres::PgRow;
use sqlx::Row;
use time::OffsetDateTime;

// Field order fixes JSON key order.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Reading {
    pub id: i64,
    pub device_id: i32,
    pub temperature_centi: i16,
    pub humidity_bp: i16,
    pub observed_at: String,
}

#[derive(Serialize)]
pub struct ListResponse {
    pub items: Vec<Reading>,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StatsResponse {
    pub device_id: i32,
    pub count: i64,
    pub temperature_sum_centi: i64,
    pub humidity_sum_bp: i64,
    pub temperature_min_centi: Option<i16>,
    pub temperature_max_centi: Option<i16>,
}

#[derive(Serialize)]
pub struct Inserted {
    pub inserted: usize,
}

/// Asia/Kolkata (fixed +05:30, India has no DST), exactly 3 fractional digits.
pub fn format_ts(t: OffsetDateTime) -> String {
    let t = t.to_offset(time::UtcOffset::from_hms(5, 30, 0).expect("valid offset"));
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}+05:30",
        t.year(),
        u8::from(t.month()),
        t.day(),
        t.hour(),
        t.minute(),
        t.second(),
        t.millisecond()
    )
}

impl Reading {
    pub fn from_row(row: &PgRow) -> Result<Self, sqlx::Error> {
        Ok(Self {
            id: row.try_get("id")?,
            device_id: row.try_get("device_id")?,
            temperature_centi: row.try_get("temperature_centi")?,
            humidity_bp: row.try_get("humidity_bp")?,
            observed_at: format_ts(row.try_get("observed_at")?),
        })
    }
}

impl StatsResponse {
    pub fn from_row(device_id: i32, row: &PgRow) -> Result<Self, sqlx::Error> {
        Ok(Self {
            device_id,
            count: row.try_get("count")?,
            temperature_sum_centi: row.try_get("temperature_sum_centi")?,
            humidity_sum_bp: row.try_get("humidity_sum_bp")?,
            temperature_min_centi: row.try_get("temperature_min_centi")?,
            temperature_max_centi: row.try_get("temperature_max_centi")?,
        })
    }
}
