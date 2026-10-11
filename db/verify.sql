SELECT 'devices' AS item, count(*) AS actual, 1000 AS expected FROM devices
UNION ALL
SELECT 'readings', count(*), 1000000 FROM readings;
SELECT min(id), max(id), min(observed_at), max(observed_at) FROM readings;
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'readings';
