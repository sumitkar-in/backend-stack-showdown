<?php

namespace App\Support;

use Illuminate\Support\Facades\DB;
use PDO;
use PDOStatement;

/**
 * Thin PDO access for the hot path: skips the query builder, query events and binding preparation of the DB facade
 * and keeps one prepared (server-side) statement per SQL text for as long as the connection lives. Under PHP-FPM that
 * is one request, so nothing changes; in a long-lived worker (Octane) every statement is parsed once.
 */
final class Pg
{
    private static ?PDO $pdo = null;

    /** @var array<string,PDOStatement> */
    private static array $statements = [];

    private static function statement(string $sql): PDOStatement
    {
        $pdo = DB::connection()->getPdo();
        if ($pdo !== self::$pdo) {   // new connection: cached statements belong to the old one
            self::$pdo = $pdo;
            self::$statements = [];
        }

        return self::$statements[$sql] ??= $pdo->prepare($sql);
    }

    /** @return list<object> */
    public static function select(string $sql, array $params): array
    {
        $st = self::statement($sql);
        $st->execute($params);

        return $st->fetchAll(PDO::FETCH_OBJ);
    }

    public static function insert(string $sql, array $params): void
    {
        self::statement($sql)->execute($params);
    }
}
