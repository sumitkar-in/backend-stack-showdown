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
    'jwt_secret' => env('JWT_SECRET', 'bench-jwt-secret-local-only'),
];
