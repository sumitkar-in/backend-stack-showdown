export const BY_ID =
  'SELECT id, device_id, temperature_centi, humidity_bp, observed_at FROM readings WHERE id = $1';
export const LIST =
  'SELECT id, device_id, temperature_centi, humidity_bp, observed_at FROM readings ' +
  'WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3 ' +
  'ORDER BY observed_at DESC, id DESC LIMIT $4 OFFSET $5';
export const STATS =
  'SELECT COUNT(*)::bigint AS count, ' +
  'COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, ' +
  'COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, ' +
  'MIN(temperature_centi) AS temperature_min_centi, ' +
  'MAX(temperature_centi) AS temperature_max_centi ' +
  'FROM readings WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3';
export const INSERT =
  'INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) ' +
  'VALUES ($1, $2, $3, $4) ' +
  'RETURNING id, device_id, temperature_centi, humidity_bp, observed_at';

const BATCH_HEAD =
  'INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES ';
const batchCache = new Map<number, string>();

/** One multi-row INSERT with n parameter groups (atomic), cached per size. */
export function batchInsert(n: number): string {
  let sql = batchCache.get(n);
  if (!sql) {
    const groups: string[] = [];
    for (let i = 0; i < n; i++) {
      const b = i * 4;
      groups.push(`($${b + 1},$${b + 2},$${b + 3},$${b + 4})`);
    }
    sql = BATCH_HEAD + groups.join(',');
    batchCache.set(n, sql);
  }
  return sql;
}
