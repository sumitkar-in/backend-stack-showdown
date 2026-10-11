<?php

namespace App\Support;

use Illuminate\Http\Response;

/** An error with a canonical status and body; rendered by the exception handler in bootstrap/app.php. */
class ApiException extends \Exception
{
    private function __construct(public readonly int $status, public readonly string $body)
    {
        parent::__construct($body);
    }

    public static function badRequest(): self   { return new self(400, '{"error":"bad_request"}'); }
    public static function invalid(): self      { return new self(422, '{"error":"validation_error"}'); }
    public static function notFound(): self     { return new self(404, '{"error":"not_found"}'); }
    public static function unauthorized(): self { return new self(401, '{"error":"unauthorized"}'); }
    public static function internal(): self     { return new self(500, '{"error":"internal"}'); }

    public function toResponse(): Response
    {
        $headers = ['Content-Type' => 'application/json', 'Content-Length' => strlen($this->body)];
        if ($this->status === 401) {
            $headers['WWW-Authenticate'] = 'Bearer';
        }

        return new Response($this->body, $this->status, $headers);
    }
}
