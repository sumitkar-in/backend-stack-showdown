<?php

namespace App\Support;

/** Strict hand-written validation. Every failure throws ApiException::invalid() (422). */
final class Input
{
    /** RFC 3339 with timezone and at most 3 fractional digits -> DateTimeImmutable (+05:30), or null. */
    public static function timestamp(mixed $v): ?\DateTimeImmutable
    {
        if (! is_string($v)
            || ! preg_match('/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,3})?(?:Z|[+-][0-9]{2}:[0-9]{2})$/', $v, $m)) {
            return null;
        }
        if (! checkdate((int) $m[2], (int) $m[3], (int) $m[1]) || (int) $m[4] > 23 || (int) $m[5] > 59 || (int) $m[6] > 59) {
            return null;
        }
        try {
            return (new \DateTimeImmutable($v))->setTimezone(new \DateTimeZone('+05:30'));
        } catch (\Exception) {
            return null;
        }
    }

    /** Asia/Kolkata string PostgreSQL parses unambiguously. */
    public static function pgTs(\DateTimeImmutable $t): string
    {
        return $t->format('Y-m-d\TH:i:s.vP');
    }

    /** "2026-01-01 00:00:00.5+05:30" (the server runs in Asia/Kolkata) -> "2026-01-01T00:00:00.500+05:30" */
    public static function formatPg(string $s): string
    {
        $frac = '000';
        if (($s[19] ?? '') === '.') {
            $end = strcspn($s, '+-', 20);
            $frac = str_pad(substr($s, 20, min(3, $end)), 3, '0');
        }

        return substr($s, 0, 10).'T'.substr($s, 11, 8).'.'.$frac.'+05:30';
    }

    /**
     * Query parameters from the raw query string; a repeated name makes the request invalid
     * (PHP's own parser would silently keep the last one).
     *
     * @return array<string,string>
     */
    public static function query(string $qs): array
    {
        $out = [];
        if ($qs === '') {
            return $out;
        }
        foreach (explode('&', $qs) as $pair) {
            if ($pair === '') {
                continue;
            }
            $kv = explode('=', $pair, 2);
            $k = urldecode($kv[0]);
            if (isset($out[$k])) {
                throw ApiException::invalid();
            }
            $out[$k] = urldecode($kv[1] ?? '');
        }

        return $out;
    }

    public static function id(string $raw): int
    {
        if (! preg_match('/^[1-9][0-9]{0,17}$/', $raw)) {
            throw ApiException::invalid();
        }

        return (int) $raw;
    }

    /** @return array{0:int,1:string,2:string} device, from, to */
    public static function deviceRange(array $q): array
    {
        $dev = $q['deviceId'] ?? null;
        $from = self::timestamp($q['from'] ?? null);
        $to = self::timestamp($q['to'] ?? null);
        if ($dev === null || ! preg_match('/^[1-9][0-9]{0,8}$/', $dev) || $from === null || $to === null || $from >= $to) {
            throw ApiException::invalid();
        }

        return [(int) $dev, self::pgTs($from), self::pgTs($to)];
    }

    /** @return array{0:int,1:int} limit (1-100, default 50), offset (0-1000, default 0) */
    public static function paging(array $q): array
    {
        $lim = $q['limit'] ?? '50';
        $off = $q['offset'] ?? '0';
        if (! preg_match('/^[0-9]{1,4}$/', $lim) || ! preg_match('/^[0-9]{1,4}$/', $off)) {
            throw ApiException::invalid();
        }
        $lim = (int) $lim;
        $off = (int) $off;
        if ($lim < 1 || $lim > 100 || $off > 1000) {
            throw ApiException::invalid();
        }

        return [$lim, $off];
    }

    /** Stage 1: malformed or empty JSON -> 400. Objects stay stdClass so {} and [] remain distinguishable. */
    public static function json(string $raw): mixed
    {
        try {
            return json_decode($raw, false, 64, JSON_THROW_ON_ERROR);
        } catch (\JsonException) {
            throw ApiException::badRequest();
        }
    }

    private static function int(\stdClass $o, string $key, int $lo, int $hi): int
    {
        // is_int is false for 2375.0 / 1e3 / "2375" / true / null, so only real integers pass
        if (! property_exists($o, $key) || ! is_int($o->$key) || $o->$key < $lo || $o->$key > $hi) {
            throw ApiException::invalid();
        }

        return $o->$key;
    }

    /** Stage 2: one reading object -> [device, temperature, humidity, observedAt]. */
    public static function reading(mixed $o): array
    {
        if (! $o instanceof \stdClass) {
            throw ApiException::invalid();
        }
        $device = self::int($o, 'deviceId', 1, 2147483647);
        $temp = self::int($o, 'temperatureCenti', -5000, 10000);
        $hum = self::int($o, 'humidityBp', 0, 10000);
        $at = self::timestamp($o->observedAt ?? null);
        if ($at === null) {
            throw ApiException::invalid();
        }

        return [$device, $temp, $hum, self::pgTs($at)];
    }

    /** 1-100 valid readings -> flat bindings. */
    public static function batch(mixed $root): array
    {
        $items = $root->readings ?? null;
        if (! is_array($items) || count($items) < 1 || count($items) > 100) {
            throw ApiException::invalid();
        }
        $flat = [];
        foreach ($items as $item) {
            array_push($flat, ...self::reading($item));
        }

        return $flat;
    }
}
