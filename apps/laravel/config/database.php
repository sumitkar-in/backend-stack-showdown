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
            'options' => [
                PDO::ATTR_PERSISTENT => true,   // one PostgreSQL session per PHP-FPM worker, reused across requests
            ],
        ],
    ],
    'migrations' => ['table' => 'migrations'],
];
