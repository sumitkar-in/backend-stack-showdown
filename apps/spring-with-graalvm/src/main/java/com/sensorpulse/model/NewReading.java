package com.sensorpulse.model;

import java.time.OffsetDateTime;

public record NewReading(int deviceId, short temperatureCenti, short humidityBp, OffsetDateTime observedAt) {}
