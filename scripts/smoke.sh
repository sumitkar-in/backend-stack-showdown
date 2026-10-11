#!/usr/bin/env bash
# Contract smoke test against one running app. Needs: BASE (url), PSQL (psql -tA command on sensorpulse DB).
# Prints "PASS name" / "FAIL name :: detail"; exit 1 if anything failed. Runs on a fresh baseline; mutates (inserts).
BASE=${BASE:-http://localhost:8080}
fails=0; total=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
AH=(); [ -n "${AUTH_TOKEN:-}" ] && AH=(-H "Authorization: Bearer $AUTH_TOKEN")   # AUTH_MODE=jwt runs

pass() { total=$((total+1)); echo "PASS $1"; }
fail() { total=$((total+1)); fails=$((fails+1)); echo "FAIL $1 :: $2"; }

# req NAME METHOD PATH EXPECT_STATUS [BODY]  -> sets $BODY_OUT
req() {
  local name=$1 method=$2 path=$3 want=$4 data=${5-}
  local code
  if [ -n "$data" ]; then
    code=$(curl -s -o "$TMP/b" -D "$TMP/h" -w '%{http_code}' -X "$method" "${AH[@]}" -H 'Content-Type: application/json' --data-binary "$data" "$BASE$path")
  else
    code=$(curl -s -o "$TMP/b" -D "$TMP/h" -w '%{http_code}' -X "$method" "${AH[@]}" "$BASE$path")
  fi
  BODY_OUT=$(cat "$TMP/b")
  if [ "$code" != "$want" ]; then fail "$name" "status $code, want $want, body: ${BODY_OUT:0:120}"; return 1; fi
  return 0
}
expect_body() { # NAME EXPECTED
  if [ "$BODY_OUT" = "$2" ]; then pass "$1"; else fail "$1" "body ${BODY_OUT:0:160} != ${2:0:160}"; fi
}
contains() { case "$BODY_OUT" in *"$2"*) pass "$1";; *) fail "$1" "missing $2 in ${BODY_OUT:0:120}";; esac; }

FROM='2026-01-01T00:00:00.000%2B05:30'; TO='2026-01-13T00:00:00.000%2B05:30'   # %2B = the + of the offset in a query string
Q="from=$FROM&to=$TO"
GOOD='{"deviceId":17,"temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}'

# ground truth straight from the database (byte-exact comparison)
EXP1=$($PSQL -c "select format('{\"id\":%s,\"deviceId\":%s,\"temperatureCenti\":%s,\"humidityBp\":%s,\"observedAt\":\"%s\"}', id, device_id, temperature_centi, humidity_bp, to_char(observed_at at time zone 'Asia/Kolkata','YYYY-MM-DD\"T\"HH24:MI:SS.MS\"+05:30\"')) from readings where id=1")
EXPS=$($PSQL -c "select format('{\"deviceId\":17,\"count\":%s,\"temperatureSumCenti\":%s,\"humiditySumBp\":%s,\"temperatureMinCenti\":%s,\"temperatureMaxCenti\":%s}', count(*), sum(temperature_centi), sum(humidity_bp), min(temperature_centi), max(temperature_centi)) from readings where device_id=17")

req health GET /health 200 && expect_body health '{"status":"ok"}'
req pk_first GET /readings/1 200 && expect_body pk_first_bytes "$EXP1"
req pk_last GET /readings/1000000 200 && contains pk_last '"id":1000000'
req pk_missing GET /readings/1000001 404 && expect_body pk_missing_body '{"error":"not_found"}'
req list_page1 GET "/readings?deviceId=17&$Q&limit=50&offset=0" 200 && {
  n=$(echo "$BODY_OUT" | grep -o '"id":' | wc -l | tr -d ' ')
  [ "$n" = "50" ] && pass list_50_items || fail list_50_items "got $n items"
  cl=$(grep -i '^content-length:' "$TMP/h" | tr -d '\r')
  [ -n "$cl" ] && pass list_content_length || fail list_content_length "no Content-Length (chunked?)"
  P1=$BODY_OUT
}
req list_page2 GET "/readings?deviceId=17&$Q&limit=50&offset=50" 200 && {
  first1=$(echo "$P1" | grep -o '"id":[0-9]*' | head -1); first2=$(echo "$BODY_OUT" | grep -o '"id":[0-9]*' | head -1)
  [ "$first1" != "$first2" ] && pass list_pages_differ || fail list_pages_differ "same first id"
}
req list_empty GET "/readings?deviceId=1001&$Q" 200 && expect_body list_empty_envelope '{"items":[],"limit":50,"offset":0}'
req stats_full GET "/readings/stats?deviceId=17&$Q" 200 && expect_body stats_bytes "$EXPS"
req stats_empty GET "/readings/stats?deviceId=17&from=2030-01-01T00:00:00.000%2B05:30&to=2030-01-02T00:00:00.000%2B05:30" 200 \
  && expect_body stats_empty_nulls '{"deviceId":17,"count":0,"temperatureSumCenti":0,"humiditySumBp":0,"temperatureMinCenti":null,"temperatureMaxCenti":null}'

# validation (reads)
req bad_limit GET "/readings?deviceId=17&$Q&limit=101" 422 && pass bad_limit_422
req bad_offset GET "/readings?deviceId=17&$Q&offset=-1" 422 && pass bad_offset_422
req bad_range GET "/readings?deviceId=17&from=$TO&to=$FROM" 422 && pass from_after_to_422
req bad_device GET "/readings?deviceId=abc&$Q" 422 && pass bad_device_422
req bad_ts GET "/readings?deviceId=17&from=yesterday&to=$TO" 422 && pass bad_timestamp_422
req neg_id GET /readings/-5 422 && pass negative_id_422
req str_id GET /readings/abc 422 && pass nonnumeric_id_422
req no_route GET /nope 404 && expect_body unknown_route_body '{"error":"not_found"}'

# writes
before=$($PSQL -c "select count(*) from readings")
req create POST /readings 201 "$GOOD" && {
  contains create_observedAt '"observedAt":"2026-01-12T00:00:00.000+05:30"'
  newid=$(echo "$BODY_OUT" | sed -E 's/.*"id":([0-9]+).*/\1/')
  [ "$newid" = "1000001" ] && pass create_id_1000001 || fail create_id_1000001 "id $newid"
  created=$BODY_OUT
  req readback GET "/readings/$newid" 200 && expect_body create_roundtrip "$created"
}
# any RFC 3339 offset is accepted (a trailing Z too) and always answered in Asia/Kolkata
req create_offset POST /readings 201 '{"deviceId":17,"temperatureCenti":1,"humidityBp":1,"observedAt":"2026-01-11T18:30:00.000Z"}' \
  && contains offset_normalized_ist '"observedAt":"2026-01-12T00:00:00.000+05:30"'
req malformed POST /readings 400 '{"deviceId":' && expect_body malformed_body '{"error":"bad_request"}'
req missing_field POST /readings 422 '{"deviceId":17,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && pass missing_field_422
req float_field POST /readings 422 '{"deviceId":17,"temperatureCenti":2375.5,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && pass float_field_422
req string_field POST /readings 422 '{"deviceId":"17","temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && pass string_field_422
req temp_range POST /readings 422 '{"deviceId":17,"temperatureCenti":10001,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && pass temp_out_of_range_422
req hum_range POST /readings 422 '{"deviceId":17,"temperatureCenti":1,"humidityBp":-1,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && pass humidity_out_of_range_422
req ts_4digits POST /readings 422 '{"deviceId":17,"temperatureCenti":1,"humidityBp":1,"observedAt":"2026-01-12T00:00:00.1234+05:30"}' && pass ts_4_fraction_digits_422
req unknown_dev POST /readings 422 '{"deviceId":99999,"temperatureCenti":1,"humidityBp":1,"observedAt":"2026-01-12T00:00:00.000+05:30"}' && expect_body unknown_device_body '{"error":"validation_error"}'

R='{"deviceId":18,"temperatureCenti":2400,"humidityBp":5500,"observedAt":"2026-01-12T00:00:01.000+05:30"}'
mk() { local n=$1 s="" i; for i in $(seq "$n"); do s="$s${s:+,}$R"; done; echo "{\"readings\":[$s]}"; }
c0=$($PSQL -c "select count(*) from readings")
req batch10 POST /readings/batch 201 "$(mk 10)" && expect_body batch10_body '{"inserted":10}'
c1=$($PSQL -c "select count(*) from readings")
[ $((c1-c0)) = 10 ] && pass batch10_rows_added || fail batch10_rows_added "delta $((c1-c0))"
req batch_bad POST /readings/batch 422 "{\"readings\":[$R,{\"deviceId\":18}]}" && {
  c2=$($PSQL -c "select count(*) from readings")
  [ "$c2" = "$c1" ] && pass batch_atomic_no_partial_insert || fail batch_atomic_no_partial_insert "rows changed $c1 -> $c2"
}
req batch_fk POST /readings/batch 422 "{\"readings\":[$R,{\"deviceId\":99999,\"temperatureCenti\":1,\"humidityBp\":1,\"observedAt\":\"2026-01-12T00:00:00.000+05:30\"}]}" && {
  c3=$($PSQL -c "select count(*) from readings")
  [ "$c3" = "$c1" ] && pass batch_fk_atomic || fail batch_fk_atomic "rows changed $c1 -> $c3"
}
req batch_empty POST /readings/batch 422 '{"readings":[]}' && pass batch_empty_422
req batch100 POST /readings/batch 201 "$(mk 100)" && expect_body batch100_body '{"inserted":100}'
req batch101 POST /readings/batch 422 "$(mk 101)" && pass batch101_422
req batch_malformed POST /readings/batch 400 '{"readings":[' && pass batch_malformed_400

echo "SUMMARY total=$total failed=$fails"
[ "$fails" = 0 ]
