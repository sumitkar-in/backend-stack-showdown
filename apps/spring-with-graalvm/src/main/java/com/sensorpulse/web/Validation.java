package com.sensorpulse.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.sensorpulse.model.DeviceRange;
import com.sensorpulse.model.NewReading;
import com.sensorpulse.support.Timestamps;
import jakarta.servlet.http.HttpServletRequest;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/** Strict hand-written validation; every failure throws ApiException.invalid() (422). */
public final class Validation {
    private Validation() {}

    private static final Pattern ID = Pattern.compile("^[1-9][0-9]{0,17}$");
    private static final Pattern DEVICE = Pattern.compile("^[1-9][0-9]{0,8}$");
    private static final Pattern UINT = Pattern.compile("^[0-9]{1,4}$");

    public record Paging(int limit, int offset) {}

    public static long id(String raw) {
        if (!ID.matcher(raw).matches()) {
            throw ApiException.invalid();
        }
        return Long.parseLong(raw);
    }

    /** Query value only when the parameter appears exactly once. */
    private static String single(HttpServletRequest req, String name) {
        String[] v = req.getParameterValues(name);
        return v != null && v.length == 1 ? v[0] : null;
    }

    public static DeviceRange deviceRange(HttpServletRequest req) {
        String dev = single(req, "deviceId");
        OffsetDateTime from = Timestamps.parse(single(req, "from"));
        OffsetDateTime to = Timestamps.parse(single(req, "to"));
        if (dev == null || !DEVICE.matcher(dev).matches() || from == null || to == null || !from.isBefore(to)) {
            throw ApiException.invalid();
        }
        return new DeviceRange(Integer.parseInt(dev), from, to);
    }

    /** limit 1-100 (default 50), offset 0-1000 (default 0). */
    public static Paging paging(HttpServletRequest req) {
        String lim = req.getParameterMap().containsKey("limit") ? single(req, "limit") : "50";
        String off = req.getParameterMap().containsKey("offset") ? single(req, "offset") : "0";
        if (lim == null || off == null || !UINT.matcher(lim).matches() || !UINT.matcher(off).matches()) {
            throw ApiException.invalid();
        }
        int limit = Integer.parseInt(lim);
        int offset = Integer.parseInt(off);
        if (limit < 1 || limit > 100 || offset > 1000) {
            throw ApiException.invalid();
        }
        return new Paging(limit, offset);
    }

    /** Integral JSON numbers only: 2375.0, 1e3, strings, bools, null are rejected. */
    private static long intField(JsonNode o, String key, long lo, long hi) {
        JsonNode n = o.get(key);
        if (n == null || !n.isIntegralNumber() || !n.canConvertToLong()) {
            throw ApiException.invalid();
        }
        long v = n.longValue();
        if (v < lo || v > hi) {
            throw ApiException.invalid();
        }
        return v;
    }

    public static NewReading reading(JsonNode o) {
        if (o == null || !o.isObject()) {
            throw ApiException.invalid();
        }
        JsonNode at = o.get("observedAt");
        OffsetDateTime ts = at != null && at.isTextual() ? Timestamps.parse(at.textValue()) : null;
        if (ts == null) {
            throw ApiException.invalid();
        }
        return new NewReading(
                (int) intField(o, "deviceId", 1, 2_147_483_647L),
                (short) intField(o, "temperatureCenti", -5000, 10000),
                (short) intField(o, "humidityBp", 0, 10000),
                ts);
    }

    /** 1-100 valid readings. */
    public static List<NewReading> batch(JsonNode root) {
        JsonNode items = root.get("readings");
        if (items == null || !items.isArray() || items.size() < 1 || items.size() > 100) {
            throw ApiException.invalid();
        }
        List<NewReading> out = new ArrayList<>(items.size());
        for (JsonNode item : items) {
            out.add(reading(item));
        }
        return out;
    }
}
