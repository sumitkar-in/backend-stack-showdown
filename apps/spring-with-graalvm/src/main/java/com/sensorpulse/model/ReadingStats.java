package com.sensorpulse.model;

public record ReadingStats(
        int deviceId,
        long count,
        long temperatureSumCenti,
        long humiditySumBp,
        Short temperatureMinCenti,
        Short temperatureMaxCenti) {}
