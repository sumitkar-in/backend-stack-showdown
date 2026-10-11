-- run against database "sensorpulse": back to the exact 1M-row baseline, hot cache, zeroed stats
DELETE FROM readings WHERE id > 1000000;
ALTER TABLE readings ALTER COLUMN id RESTART WITH 1000001;
VACUUM (ANALYZE) readings;
CHECKPOINT;
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
SELECT pg_prewarm('readings'), pg_prewarm('readings_pkey'), pg_prewarm('idx_readings_device_time_id');
SELECT pg_stat_statements_reset();
SELECT pg_stat_reset();
