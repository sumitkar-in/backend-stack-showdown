package com.sensorpulse.model;

import java.util.List;

public record ReadingPage(List<Reading> items, int limit, int offset) {}
