<?php

namespace App\Http\Controllers;

use Illuminate\Http\Response;

class HealthController
{
    public function __invoke(): Response
    {
        $body = '{"status":"ok"}';   // no DB access

        return new Response($body, 200, ['Content-Type' => 'application/json', 'Content-Length' => strlen($body)]);
    }
}
