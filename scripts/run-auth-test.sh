#!/usr/bin/env bash
# Auth test for every app: starts each stack with AUTH_MODE=jwt and runs
#   1. scripts/smoke-auth.sh   (401 cases, alg=none/RS256 confusion, expiry, auth-before-validation, ...)
#   2. scripts/smoke.sh        (the normal 38-check API contract, now sending a valid token)
# then restarts it with AUTH_MODE=none and confirms no token is needed. Writes results/auth/<run>/summary.md.
#
#   scripts/run-auth-test.sh               # all stacks
#   STACKS="go rust" scripts/run-auth-test.sh
set -uo pipefail
cd "$(dirname "$0")/.."

STACKS=${STACKS:-"nest spring go rust fastapi laravel octane graalvm"}
RUN_ID=${RUN_ID:-$(date +%Y-%m-%d_%H%M)${LABEL:+_$LABEL}}
OUT=results/auth/$RUN_ID; mkdir -p "$OUT"/{contract,logs}
source scripts/lib.sh

start_app() { # stack mode [--build]
  AUTH_MODE=$2 $DC --profile "$1" up -d ${3:-} --force-recreate "app-$1" >"$OUT/logs/build-$1-$2.log" 2>&1 && wait_health
}

pg_prepare || exit 1

{ echo "# Auth test (JWT HS256)"; echo; echo "| Stack | Auth contract | API contract with token | Auth off needs no token |"; echo "| --- | --- | --- | --- |"; } > "$OUT/summary.md"
overall=0
for stack in $STACKS; do
  log "=========== $stack ==========="
  stop_apps
  restore_baseline
  if ! start_app "$stack" jwt --build; then
    log "$stack: failed to start with AUTH_MODE=jwt"; echo "| $stack | start failed | – | – |" >> "$OUT/summary.md"; overall=1; continue
  fi
  # Order matters: smoke.sh needs the pristine baseline, so it runs first; the auth checks do not.
  AUTH_TOKEN=$(mint_token valid) bash scripts/smoke.sh > "$OUT/contract/api-$stack.txt" 2>&1; b=$?
  log "$stack: API contract with token: $(tail -1 "$OUT/contract/api-$stack.txt")"
  bash scripts/smoke-auth.sh > "$OUT/contract/auth-$stack.txt" 2>&1; a=$?
  log "$stack: auth contract: $(tail -1 "$OUT/contract/auth-$stack.txt")"

  start_app "$stack" none
  c1=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/readings/1"); c2=$(curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer garbage' "$BASE/readings/1")
  if [ "$c1" = 200 ] && [ "$c2" = 200 ]; then c=0; else c=1; fi
  log "$stack: AUTH_MODE=none -> no token: $c1, garbage token: $c2"

  fa=$(grep -c '^FAIL' "$OUT/contract/auth-$stack.txt"); fb=$(grep -c '^FAIL' "$OUT/contract/api-$stack.txt")
  pa=$(grep -c '^PASS' "$OUT/contract/auth-$stack.txt"); pb=$(grep -c '^PASS' "$OUT/contract/api-$stack.txt")
  st() { [ "$1" = 0 ] && echo "PASS" || echo "**FAIL**"; }
  echo "| $stack | $(st $a) ($pa/$((pa+fa))) | $(st $b) ($pb/$((pb+fb))) | $(st $c) (no token $c1, garbage token $c2) |" >> "$OUT/summary.md"
  [ "$a$b$c" = "000" ] || overall=1
  $DC stop "app-$stack" >/dev/null 2>&1
done
stop_apps
reset_rows
echo; cat "$OUT/summary.md"
python3 scripts/report.py refresh >/dev/null 2>&1; log "details: $OUT/"
exit $overall
