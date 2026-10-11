<?php

use App\Http\Middleware\JwtAuth;
use App\Support\ApiException;
use Illuminate\Database\QueryException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpKernel\Exception\MethodNotAllowedHttpException;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        // Plain routes at the root: no /api prefix and none of the web group (session, cookies, CSRF).
        then: function () {
            Route::group([], base_path('routes/api.php'));
        },
    )
    ->withMiddleware(function (Middleware $middleware) {
        // Drop the default global stack (maintenance check, TrimStrings, ConvertEmptyStringsToNull, CORS, ...):
        // it would mutate request input, and none of it is part of the API contract.
        $middleware->use([]);
        $middleware->alias(['jwt' => JwtAuth::class]);
    })
    ->withExceptions(function (Exceptions $exceptions) {
        $exceptions->dontReport([ApiException::class, NotFoundHttpException::class, MethodNotAllowedHttpException::class, QueryException::class]);
        // Every error leaves as {"error": "..."} with the contract's status code.
        $exceptions->render(function (Throwable $e) {
            if ($e instanceof ApiException) {
                return $e->toResponse();
            }
            if ($e instanceof NotFoundHttpException || $e instanceof MethodNotAllowedHttpException) {
                return ApiException::notFound()->toResponse();
            }
            if ($e instanceof QueryException && in_array((string) $e->getCode(), ['23503', '23514'], true)) {
                return ApiException::invalid()->toResponse(); // FK / CHECK violation
            }
            error_log('unhandled: '.$e::class.': '.$e->getMessage());

            return ApiException::internal()->toResponse();
        });
    })
    ->create();
