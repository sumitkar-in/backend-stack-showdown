<?php

namespace App\Support;

/** Same statements as every other stack (Laravel/PDO use ? placeholders). */
final class Sql
{
    public const BY_ID = 'SELECT id, device_id, temperature_centi, humidity_bp, observed_at FROM readings WHERE id = ?';

    public const LIST = 'SELECT id, device_id, temperature_centi, humidity_bp, observed_at FROM readings '
        .'WHERE device_id = ? AND observed_at >= ? AND observed_at < ? '
        .'ORDER BY observed_at DESC, id DESC LIMIT ? OFFSET ?';

    public const STATS = 'SELECT COUNT(*)::bigint AS count, '
        .'COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, '
        .'COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, '
        .'MIN(temperature_centi) AS temperature_min_centi, '
        .'MAX(temperature_centi) AS temperature_max_centi '
        .'FROM readings WHERE device_id = ? AND observed_at >= ? AND observed_at < ?';

    public const INSERT = 'INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) '
        .'VALUES (?, ?, ?, ?) '
        .'RETURNING id, device_id, temperature_centi, humidity_bp, observed_at';

    private const BATCH_HEAD = 'INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES ';

    /** @var array<int,string> */
    private static array $batch = [];

    /** One multi-row INSERT with $n groups (atomic), cached per size within the worker. */
    public static function batchInsert(int $n): string
    {
        return self::$batch[$n] ??= self::BATCH_HEAD.implode(',', array_fill(0, $n, '(?,?,?,?)'));
    }
}
