<?php

return [
    'name' => 'SensorPulse',
    'env' => env('APP_ENV', 'production'),
    'debug' => false,
    'url' => 'http://localhost',
    'timezone' => 'Asia/Kolkata',
    'locale' => 'en',
    'fallback_locale' => 'en',
    'cipher' => 'AES-256-CBC',
    'key' => env('APP_KEY'),   // never used (no cookies/sessions/encryption), present so the framework boots cleanly
    'auth_mode' => env('AUTH_MODE', 'none'),
    // Only the framework providers this API uses. The default list also boots Auth, Cookie, Session, View, ... on
    // every request (or every worker start) for features that are not part of the contract.
    'providers' => [
        Illuminate\Cache\CacheServiceProvider::class,
        Illuminate\Database\DatabaseServiceProvider::class,
        Illuminate\Filesystem\FilesystemServiceProvider::class,
        Illuminate\Foundation\Providers\ConsoleSupportServiceProvider::class,
        Illuminate\Foundation\Providers\FoundationServiceProvider::class,
        Illuminate\Pipeline\PipelineServiceProvider::class,
        Illuminate\Translation\TranslationServiceProvider::class,
        Illuminate\View\ViewServiceProvider::class,   // Octane's reset listeners touch the translator and view engines
    ],
    'jwt_secret' => env('JWT_SECRET', 'bench-jwt-secret-local-only'),
];
