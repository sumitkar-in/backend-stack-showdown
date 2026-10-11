#!/usr/bin/env bash
# Ramp test: offered load climbs in steps (open model) to find where each stack breaks and the highest rate
# that keeps p95 under a latency threshold (default 0.5 ms; the report also tabulates 1/2/5/10/25/50/100 ms).
#
#   scripts/run-ramp.sh
#   STACKS="go rust" WORKLOADS="pk health" RATES="500,1000,2000,4000,8000" STEP_DUR=20 scripts/run-ramp.sh
set -uo pipefail
cd "$(dirname "$0")/.."

STACKS=${STACKS:-"nest spring go rust fastapi laravel octane graalvm"}
WORKLOADS=${WORKLOADS:-"pk"}
RATES=${RATES:-"250,500,1000,2000,3000,4000,6000,8000,12000,16000,24000,32000,48000"}
STEP_DUR=${STEP_DUR:-15}
WARM_DUR=${WARM_DUR:-15}
MAX_VUS=${MAX_VUS:-1000}
export K6_CPUS=${K6_CPUS:-4.0} K6_MEM=${K6_MEM:-2g}
P95_TARGET_MS=${P95_TARGET_MS:-0.5}
RUN_ID=${RUN_ID:-$(date +%Y-%m-%d_%H%M)${LABEL:+_$LABEL}}
OUT=results/ramps/$RUN_ID
mkdir -p "$OUT"/{k6,stats,logs}
K6_OUT="/results/ramps/$RUN_ID/k6"
source scripts/lib.sh

export AUTH_MODE=${AUTH_MODE:-none}
AUTH_TOKEN=""; [ "$AUTH_MODE" = jwt ] && AUTH_TOKEN=$(mint_token valid)
export AUTH_TOKEN

{
  echo "run_id=$RUN_ID"; echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  host_env
  echo "stacks=$STACKS"; echo "workloads=$WORKLOADS"; echo "rates=$RATES"; echo "step_dur=$STEP_DUR"; echo "warm_dur=$WARM_DUR"
  echo "max_vus=$MAX_VUS"; echo "k6_cpus=$K6_CPUS"; echo "auth_mode=$AUTH_MODE"; echo "p95_target_ms=$P95_TARGET_MS"; echo "app_cpus=2"; echo "app_mem=4g"
} > "$OUT/env.txt"
: > "$OUT/cells.tsv"

pg_prepare || exit 1
PG_CID=$($DC ps -q postgres)

for stack in $STACKS; do
  svc="app-$stack"; log "=============== $stack ==============="
  stop_apps
  restore_baseline || { log "restore failed"; continue; }
  if ! $DC --profile "$stack" up -d --build "$svc" >"$OUT/logs/build-$stack.log" 2>&1; then log "$stack: build FAILED"; continue; fi
  wait_health || { log "$stack: never healthy"; $DC logs --tail 60 "$svc" > "$OUT/logs/app-$stack.log" 2>&1; $DC stop "$svc" >/dev/null 2>&1; continue; }
  APP_CID=$($DC ps -q "$svc"); log "$stack: healthy"

  for w in $WORKLOADS; do
    cell="$stack-$w"
    reset_rows
    steps=$(echo "$RATES" | tr ',' '\n' | wc -l | tr -d ' ')
    total=$((WARM_DUR + steps * STEP_DUR))
    log "$cell: ramp $RATES req/s, ${STEP_DUR}s per step (~${total}s)"
    # timestamped docker stats so CPU can be attributed to each step
    sample_stats "$OUT/stats/stats-$cell.raw" ts "$APP_CID" "$PG_CID"
    t0=$(python3 -c "import time;print(time.time())")
    k6_run -e WORKLOAD="$w" -e RATES="$RATES" -e STEP_DUR="$STEP_DUR" -e WARM_DUR="$WARM_DUR" -e MAX_VUS="$MAX_VUS" \
      -e RESULT_DIR="$K6_OUT" -e RUN_ID="$cell" ramp.js >"$OUT/k6/k6-$cell.log" 2>&1 &
    K6PID=$!
    # sample the load generator too, so a client-side limit is visible
    K6_CID=""; for i in $(seq 20); do K6_CID=$(docker ps -q --filter "name=k6-run" | head -1); [ -n "$K6_CID" ] && break; sleep 0.5; done
    [ -n "$K6_CID" ] && sample_stats "$OUT/stats/stats-k6-$cell.raw" ts "$K6_CID"
    wait $K6PID
    k6_exit=$?
    stop_samplers
    echo "$stack	$w	$t0	$k6_exit" >> "$OUT/cells.tsv"
    log "$cell: done (k6 exit $k6_exit)  $(grep -h '^ramp ' "$OUT/k6/k6-$cell.log" | tail -1 | cut -c1-200)"
  done
  $DC stop "$svc" >/dev/null 2>&1; sleep 5
done

echo "finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/env.txt"
stop_apps
python3 scripts/report.py ramp "$OUT" && log "report: $OUT/ramp-report.html"
