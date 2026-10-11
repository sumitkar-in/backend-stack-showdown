package com.sensorpulse.support;

import java.time.DateTimeException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.regex.Pattern;

public final class Timestamps {
    private Timestamps() {}

    private static final Pattern RFC3339 = Pattern.compile(
            "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,3})?(Z|[+-][0-9]{2}:[0-9]{2})$");

    private static final DateTimeFormatter OUT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSxxx");

    /** Asia/Kolkata as a fixed +05:30 offset (India has no DST). */
    private static final ZoneOffset IST = ZoneOffset.ofHoursMinutes(5, 30);

    /** RFC3339 with timezone and at most 3 fractional digits, else null. */
    public static OffsetDateTime parse(String s) {
        if (s == null || !RFC3339.matcher(s).matches()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(s);
        } catch (DateTimeException e) {
            return null;
        }
    }

    /** Asia/Kolkata (+05:30), exactly 3 fractional digits. */
    public static String format(OffsetDateTime t) {
        return OUT.format(t.withOffsetSameInstant(IST));
    }
}
