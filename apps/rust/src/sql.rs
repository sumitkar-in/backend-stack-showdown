use std::sync::OnceLock;

pub const BY_ID: &str = "SELECT id, device_id, temperature_centi, humidity_bp, observed_at \
FROM readings WHERE id = $1";

pub const LIST: &str = "SELECT id, device_id, temperature_centi, humidity_bp, observed_at \
FROM readings \
WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3 \
ORDER BY observed_at DESC, id DESC LIMIT $4 OFFSET $5";

pub const STATS: &str = "SELECT COUNT(*)::bigint AS count, \
COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, \
COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, \
MIN(temperature_centi) AS temperature_min_centi, \
MAX(temperature_centi) AS temperature_max_centi \
FROM readings WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3";

pub const INSERT: &str = "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) \
VALUES ($1, $2, $3, $4) \
RETURNING id, device_id, temperature_centi, humidity_bp, observed_at";

const BATCH_HEAD: &str =
    "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES ";

static BATCH: OnceLock<Vec<String>> = OnceLock::new();

/// One multi-row INSERT with `n` (1..=100) parameter groups (atomic); built once, reused.
pub fn batch_insert(n: usize) -> &'static str {
    let all = BATCH.get_or_init(|| {
        (0..=100)
            .map(|n| {
                let groups: Vec<String> = (0..n)
                    .map(|i| {
                        let b = i * 4;
                        format!("(${},${},${},${})", b + 1, b + 2, b + 3, b + 4)
                    })
                    .collect();
                format!("{BATCH_HEAD}{}", groups.join(","))
            })
            .collect()
    });
    &all[n]
}
