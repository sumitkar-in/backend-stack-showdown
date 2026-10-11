export interface ReadingRow {
  id: number;
  device_id: number;
  temperature_centi: number;
  humidity_bp: number;
  observed_at: string;
}

export interface StatsRow {
  count: number;
  temperature_sum_centi: number;
  humidity_sum_bp: number;
  temperature_min_centi: number | null;
  temperature_max_centi: number | null;
}

// "2026-01-01 00:00:00.5+05:30" (PostgreSQL text, session in Asia/Kolkata) -> "2026-01-01T00:00:00.500+05:30".
// India has no DST, so the offset is always +05:30.
export const formatTs = (t: string): string => {
  let frac = '000';
  if (t.charCodeAt(19) === 46) {
    const end = t.indexOf('+', 20);
    frac = t.slice(20, end).padEnd(3, '0');
  }
  return `${t.slice(0, 10)}T${t.slice(11, 19)}.${frac}+05:30`;
};

// Key order is fixed by literal order.
export const reading = (r: ReadingRow) => ({
  id: r.id,
  deviceId: r.device_id,
  temperatureCenti: r.temperature_centi,
  humidityBp: r.humidity_bp,
  observedAt: formatTs(r.observed_at),
});

export const stats = (deviceId: number, r: StatsRow) => ({
  deviceId,
  count: r.count,
  temperatureSumCenti: r.temperature_sum_centi,
  humiditySumBp: r.humidity_sum_bp,
  temperatureMinCenti: r.temperature_min_centi,
  temperatureMaxCenti: r.temperature_max_centi,
});
