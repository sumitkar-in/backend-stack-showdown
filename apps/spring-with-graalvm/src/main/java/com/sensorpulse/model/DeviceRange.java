package com.sensorpulse.model;

import java.time.OffsetDateTime;

public record DeviceRange(int device, OffsetDateTime from, OffsetDateTime to) {}
