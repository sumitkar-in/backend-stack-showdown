-- Exactly 1,000 devices and 1,000,000 readings. Deterministic data generation.
INSERT INTO devices (name, location)
SELECT 'sensor-' || LPAD(g::text, 4, '0'),
       'site-' || LPAD(((g - 1) % 20 + 1)::text, 2, '0')
FROM generate_series(1, 1000) AS g ORDER BY g;

INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at)
SELECT ((g - 1) % 1000 + 1)::integer,
       (1800 + ((g * 37) % 1701))::smallint,
       (3000 + ((g * 11) % 6001))::smallint,
       '2026-01-01T00:00:00+05:30'::timestamptz + ((g - 1) * INTERVAL '1 second')
FROM generate_series(1, 1000000) AS g
ORDER BY g;
