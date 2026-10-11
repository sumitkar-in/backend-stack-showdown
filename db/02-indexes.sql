-- Build after bulk loading so startup seed is efficient.
CREATE INDEX idx_readings_device_time_id
    ON readings (device_id, observed_at DESC, id DESC);
ANALYZE devices;
ANALYZE readings;
