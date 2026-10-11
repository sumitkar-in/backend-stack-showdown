<?php

use Monolog\Handler\StreamHandler;

return [
    'default' => 'stderr',
    'deprecations' => ['channel' => 'null', 'trace' => false],
    'channels' => [
        'stderr' => [
            'driver' => 'monolog',
            'level' => 'error',
            'handler' => StreamHandler::class,
            'with' => ['stream' => 'php://stderr'],
        ],
        'null' => ['driver' => 'monolog', 'handler' => Monolog\Handler\NullHandler::class],
    ],
];
