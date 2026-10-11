package com.sensorpulse.model;

/** Component order fixes JSON key order. */
public record Reading(long id, int deviceId, short temperatureCenti, short humidityBp, String observedAt) {}
