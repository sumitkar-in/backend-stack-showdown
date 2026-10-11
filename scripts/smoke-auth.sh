#!/usr/bin/env bash
# Auth contract test for an app started with AUTH_MODE=jwt. Needs BASE (default http://localhost:8080)
# and optionally PSQL (psql -tA on the sensorpulse DB) for the "nothing inserted" check.
cd "$(dirname "$0")/.."
BASE=${BASE:-http://localhost:8080}
fails=0; total=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
pass() { total=$((total+1)); echo "PASS $1"; }
fail() { total=$((total+1)); fails=$((fails+1)); echo "FAIL $1 :: $2"; }
# mint every token kind once (T_valid, T_expired, ...) instead of spawning python per check
while IFS='=' read -r _k _v; do printf -v "T_$_k" '%s' "$_v"; done < <(python3 scripts/jwt.py all)
UNAUTH='{"error":"unauthorized"}'
GOOD='{"deviceId":17,"temperatureCenti":2375,"humidityBp":5375,"observedAt":"2026-01-12T00:00:00.000+05:30"}'

# check NAME EXPECT_STATUS METHOD PATH [AUTH_HEADER_VALUE|-] [BODY]
check() {
  local name=$1 want=$2 method=$3 path=$4 auth=${5:--} body=${6-}
  local args=(-s -o "$TMP/b" -D "$TMP/h" -w '%{http_code}' -X "$method")
  [ "$auth" != "-" ] && args+=(-H "Authorization: $auth")
  [ -n "$body" ] && args+=(-H 'Content-Type: application/json' --data-binary "$body")
  local code; code=$(curl "${args[@]}" "$BASE$path")
  BODY=$(cat "$TMP/b")
  if [ "$code" != "$want" ]; then fail "$name" "status $code, want $want, body ${BODY:0:100}"; return 1; fi
  if [ "$want" = 401 ]; then
    [ "$BODY" = "$UNAUTH" ] || { fail "$name" "body $BODY"; return 1; }
    grep -qi '^www-authenticate: *bearer' "$TMP/h" || { fail "$name" "no WWW-Authenticate: Bearer header"; return 1; }
  fi
  pass "$name"
}

VALID="Bearer $T_valid"
check public_health_no_token            200 GET /health
check no_header_401                     401 GET /readings/1
check empty_bearer_401                  401 GET /readings/1 "Bearer "
check basic_scheme_401                  401 GET /readings/1 "Basic dXNlcjpwYXNz"
check lowercase_scheme_401              401 GET /readings/1 "bearer $T_valid"
check malformed_token_401               401 GET /readings/1 "Bearer $T_malformed"
check bad_signature_401                 401 GET /readings/1 "Bearer $T_badsig"
check wrong_secret_401                  401 GET /readings/1 "Bearer $T_wrongsecret"
check alg_none_401                      401 GET /readings/1 "Bearer $T_none"
check alg_confusion_rs256_401           401 GET /readings/1 "Bearer $T_rs256"
check expired_401                       401 GET /readings/1 "Bearer $T_expired"
check missing_sub_401                   401 GET /readings/1 "Bearer $T_nosub"
check float_exp_401                     401 GET /readings/1 "Bearer $T_floatexp"
check valid_token_200                   200 GET /readings/1 "$VALID"
[ "$(echo "$BODY" | head -c 6)" = '{"id":' ] && pass valid_token_body_is_reading || fail valid_token_body_is_reading "$BODY"
check list_requires_token               401 GET "/readings?deviceId=17&from=2026-01-01T00:00:00.000%2B05:30&to=2026-01-13T00:00:00.000%2B05:30"
check list_with_token                   200 GET "/readings?deviceId=17&from=2026-01-01T00:00:00.000%2B05:30&to=2026-01-13T00:00:00.000%2B05:30" "$VALID"
check stats_requires_token              401 GET "/readings/stats?deviceId=17&from=2026-01-01T00:00:00.000%2B05:30&to=2026-01-13T00:00:00.000%2B05:30"
check stats_with_token                  200 GET "/readings/stats?deviceId=17&from=2026-01-01T00:00:00.000%2B05:30&to=2026-01-13T00:00:00.000%2B05:30" "$VALID"
check auth_before_validation_401        401 GET "/readings?deviceId=abc"
check bad_query_with_token_422          422 GET "/readings?deviceId=abc" "$VALID"
check post_requires_token               401 POST /readings - "$GOOD"
check auth_before_body_parse_401        401 POST /readings - '{"deviceId":'
check malformed_body_with_token_400     400 POST /readings "$VALID" '{"deviceId":'
check batch_requires_token              401 POST /readings/batch - "{\"readings\":[$GOOD]}"
check post_with_token_201               201 POST /readings "$VALID" "$GOOD"
check batch_with_token_201              201 POST /readings/batch "$VALID" "{\"readings\":[$GOOD]}"
check unknown_route_404_without_token   404 GET /nope

# rejected writes must not reach the database
if [ -n "${PSQL:-}" ]; then
  before=$($PSQL -c "select count(*) from readings")
  curl -s -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary "$GOOD" "$BASE/readings"
  curl -s -o /dev/null -X POST -H 'Content-Type: application/json' -H "Authorization: Bearer $T_expired" --data-binary "$GOOD" "$BASE/readings"
  after=$($PSQL -c "select count(*) from readings")
  [ "$before" = "$after" ] && pass rejected_writes_insert_nothing || fail rejected_writes_insert_nothing "rows $before -> $after"
fi

echo "SUMMARY total=$total failed=$fails"
[ "$fails" = 0 ]
