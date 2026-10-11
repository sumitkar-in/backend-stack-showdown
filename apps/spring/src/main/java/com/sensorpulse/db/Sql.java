package com.sensorpulse.db;

import java.util.Arrays;

public final class Sql {
    private Sql() {}

    public static final String BY_ID =
            "SELECT id, device_id, temperature_centi, humidity_bp, observed_at "
                    + "FROM readings WHERE id = ?";

    public static final String LIST =
            "SELECT id, device_id, temperature_centi, humidity_bp, observed_at "
                    + "FROM readings "
                    + "WHERE device_id = ? AND observed_at >= ? AND observed_at < ? "
                    + "ORDER BY observed_at DESC, id DESC LIMIT ? OFFSET ?";

    public static final String STATS =
            "SELECT COUNT(*)::bigint AS count, "
                    + "COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, "
                    + "COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, "
                    + "MIN(temperature_centi) AS temperature_min_centi, "
                    + "MAX(temperature_centi) AS temperature_max_centi "
                    + "FROM readings WHERE device_id = ? AND observed_at >= ? AND observed_at < ?";

    public static final String INSERT =
            "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) "
                    + "VALUES (?, ?, ?, ?) "
                    + "RETURNING id, device_id, temperature_centi, humidity_bp, observed_at";

    private static final String BATCH_HEAD =
            "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES ";

    /** BATCH[n] = one multi-row INSERT with n groups (atomic); built once. */
    private static final String[] BATCH = new String[101];

    static {
        for (int n = 1; n <= 100; n++) {
            String[] groups = new String[n];
            Arrays.fill(groups, "(?,?,?,?)");
            BATCH[n] = BATCH_HEAD + String.join(",", groups);
        }
    }

    public static String batchInsert(int n) {
        return BATCH[n];
    }
}
