# Laravel backend

Laravel 12 on PHP 8.3, served by **nginx + PHP-FPM** (the standard production setup), with PDO PostgreSQL through Laravel's `DB` facade (raw SQL, no Eloquent).

- **Connection model.** PHP has no shared pool: `pm = static` with **20 workers**, each holding one persistent PDO connection, so the database sees at most 20 sessions (the same budget as the other stacks). Connections open on a worker's first DB request; the warm-up phase brings all 20 up. Prepared statements are native (server-side) but PDO cannot reuse them across requests, so every request pays a parse step (a PHP characteristic).
- **Framework stack.** Real Laravel: kernel, router, container, middleware pipeline, exception handler. Routes live at the root without the web group (no session/cookies/CSRF), and the default global middleware (TrimStrings, ConvertEmptyStringsToNull, ...) is removed so request input is untouched. `config:cache` and `route:cache` run at container start; opcache is on with `validate_timestamps=0`, JIT off.
- **Avoided per-request overhead.** The DB config omits `search_path`, `timezone` and `synchronous_commit`, because each makes Laravel send an extra `SET` on every request.
- **Contract.** Same two-stage handling as the others: malformed JSON -> 400 (`JSON_THROW_ON_ERROR`), then strict validation -> 422 (`is_int`, so `2375.0` is rejected). Errors are normalized in `bootstrap/app.php`; FK/CHECK violations (SQLSTATE 23503/23514) map to 422. Duplicate query parameters are rejected (PHP's own parser would silently keep the last).
- **Auth.** `AUTH_MODE=jwt` adds the `jwt` route middleware (`app/Http/Middleware/JwtAuth.php`), same rules as the other stacks.
- **Container.** nginx (2 workers, keep-alive unlimited, no access log) and PHP-FPM run in one container, started by `docker/entrypoint.sh`; non-root (`www-data`).
- `composer.lock` is committed.

Layout: `bootstrap/app.php` (wiring + error rendering), `routes/api.php`, `app/Http/Controllers`, `app/Http/Middleware/JwtAuth.php`, `app/Support` (`Sql`, `Input`, `ApiException`), `config/`, `docker/`.

Run: `docker compose -f infra/compose.yaml --profile laravel up -d --build app-laravel`
