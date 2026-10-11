<?php

namespace App\Http\Middleware;

use App\Support\ApiException;
use Closure;
use Illuminate\Http\Request;

/**
 * Verifies an HS256 bearer token on every request (no caching of verified tokens).
 * Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
 * valid HMAC-SHA256 signature, integer exp in the future, non-empty sub.
 */
class JwtAuth
{
    public function handle(Request $request, Closure $next)
    {
        if (! self::verify($request->headers->get('Authorization'), (string) config('app.jwt_secret'))) {
            throw ApiException::unauthorized();
        }

        return $next($request);
    }

    private static function b64(string $s): ?string
    {
        if (! preg_match('/^[A-Za-z0-9_-]+$/', $s)) {
            return null;
        }
        $d = base64_decode(strtr($s, '-_', '+/').str_repeat('=', (4 - strlen($s) % 4) % 4), true);

        return $d === false ? null : $d;
    }

    private static function verify(?string $header, string $secret): bool
    {
        if ($header === null || ! str_starts_with($header, 'Bearer ')) {
            return false;
        }
        $parts = explode('.', substr($header, 7));
        if (count($parts) !== 3 || in_array('', $parts, true)) {
            return false;
        }
        [$h, $p, $s] = $parts;
        $sig = self::b64($s);
        if ($sig === null || ! hash_equals(hash_hmac('sha256', "$h.$p", $secret, true), $sig)) {
            return false;
        }
        $hb = self::b64($h);
        $pb = self::b64($p);
        if ($hb === null || $pb === null) {
            return false;
        }
        $hdr = json_decode($hb);
        $claims = json_decode($pb);

        return $hdr instanceof \stdClass && ($hdr->alg ?? null) === 'HS256'
            && $claims instanceof \stdClass
            && is_string($claims->sub ?? null) && $claims->sub !== ''
            && is_int($claims->exp ?? null) && $claims->exp > time();
    }
}
