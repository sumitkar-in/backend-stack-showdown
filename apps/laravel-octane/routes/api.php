<?php

use App\Http\Controllers\HealthController;
use App\Http\Controllers\ReadingsController;
use Illuminate\Support\Facades\Route;

Route::get('/health', HealthController::class);   // public, no DB

// JWT middleware exists only when AUTH_MODE=jwt (evaluated when the route cache is built at container start).
Route::middleware(config('app.auth_mode') === 'jwt' ? ['jwt'] : [])->group(function () {
    Route::get('/readings/stats', [ReadingsController::class, 'stats']);   // before /readings/{id}
    Route::get('/readings/{id}', [ReadingsController::class, 'show']);
    Route::get('/readings', [ReadingsController::class, 'index']);
    Route::post('/readings', [ReadingsController::class, 'store']);
    Route::post('/readings/batch', [ReadingsController::class, 'storeBatch']);
});
