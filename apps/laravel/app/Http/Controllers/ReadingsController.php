<?php

namespace App\Http\Controllers;

use App\Support\ApiException;
use App\Support\Input;
use App\Support\Sql;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;

class ReadingsController
{
    private static function send(array $data, int $status = 200): Response
    {
        $body = json_encode($data);

        // explicit Content-Length: without it nginx answers with chunked transfer encoding
        return new Response($body, $status, ['Content-Type' => 'application/json', 'Content-Length' => strlen($body)]);
    }

    private static function reading(object $r): array
    {
        return [
            'id' => $r->id,
            'deviceId' => $r->device_id,
            'temperatureCenti' => $r->temperature_centi,
            'humidityBp' => $r->humidity_bp,
            'observedAt' => Input::formatPg($r->observed_at),
        ];
    }

    public function show(string $id): Response
    {
        $rows = DB::select(Sql::BY_ID, [Input::id($id)]);
        if (! $rows) {
            throw ApiException::notFound();
        }

        return self::send(self::reading($rows[0]));
    }

    public function index(Request $request): Response
    {
        $q = Input::query((string) $request->server->get('QUERY_STRING', ''));
        [$device, $from, $to] = Input::deviceRange($q);
        [$limit, $offset] = Input::paging($q);
        $rows = DB::select(Sql::LIST, [$device, $from, $to, $limit, $offset]);

        return self::send(['items' => array_map(self::reading(...), $rows), 'limit' => $limit, 'offset' => $offset]);
    }

    public function stats(Request $request): Response
    {
        $q = Input::query((string) $request->server->get('QUERY_STRING', ''));
        [$device, $from, $to] = Input::deviceRange($q);
        $r = DB::select(Sql::STATS, [$device, $from, $to])[0];

        return self::send([
            'deviceId' => $device,
            'count' => $r->count,
            'temperatureSumCenti' => $r->temperature_sum_centi,
            'humiditySumBp' => $r->humidity_sum_bp,
            'temperatureMinCenti' => $r->temperature_min_centi,
            'temperatureMaxCenti' => $r->temperature_max_centi,
        ]);
    }

    public function store(Request $request): Response
    {
        $args = Input::reading(Input::json($request->getContent()));
        $rows = DB::select(Sql::INSERT, $args);   // INSERT ... RETURNING

        return self::send(self::reading($rows[0]), 201);
    }

    public function storeBatch(Request $request): Response
    {
        $root = Input::json($request->getContent());
        if (! $root instanceof \stdClass) {
            throw ApiException::badRequest();
        }
        $flat = Input::batch($root);
        $n = intdiv(count($flat), 4);
        DB::insert(Sql::batchInsert($n), $flat);

        return self::send(['inserted' => $n], 201);
    }
}
