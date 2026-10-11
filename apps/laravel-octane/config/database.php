<?php

return [
    'default' => 'pgsql',
    'connections' => [
        'pgsql' => [
            'driver' => 'pgsql',
            'host' => env('DB_HOST', 'postgres'),
            'port' => env('DB_PORT', '5432'),
            'database' => env('DB_NAME', 'sensorpulse'),
            'username' => env('DB_USER', 'bench'),
            'password' => env('DB_PASSWORD', ''),
            'charset' => 'utf8',
            'prefix' => '',
            'sslmode' => 'disable',
            // Deliberately no 'search_path' / 'timezone' / 'synchronous_commit' keys: each one makes Laravel
            // send an extra SET statement on every request. The server already runs in Asia/Kolkata with the public schema.
            // No PDO::ATTR_PERSISTENT: an Octane worker is a long-lived process, so its connection already
            // lives across requests (one PostgreSQL session per worker).
        ],
    ],
    'migrations' => ['table' => 'migrations'],
];
