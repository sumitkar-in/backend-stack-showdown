#!/usr/bin/env bash
# End-to-end benchmark: for each stack (default order nest, spring, go, rust, fastapi, laravel, octane) build + start the app container
# (2 vCPU / 4 GiB), run a contract smoke test, then run every workload with k6 at 100 VUs, sample container
# CPU/memory, and finally generate an HTML report.
#
#   scripts/run-benchmark.sh                      # defaults
#   RUN_ID=<existing run> STACKS=fastapi scripts/run-benchmark.sh   # add a stack to an earlier run
#   STACKS="go rust" WORKLOADS="pk mixed" DURATION=60s REPS=3 scripts/run-benchmark.sh
set -uo pipefail
cd "$(dirname "$0")/.."

STACKS=${STACKS:-"nest spring go rust fastapi laravel octane graalvm"}
WORKLOADS=${WORKLOADS:-"health pk range stats insert batch mixed"}
VUS=${VUS:-100}
WARMUP=${WARMUP:-10s}
DURATION=${DURATION:-30s}
REPS=${REPS:-1}
RUN_ID=${RUN_ID:-$(date +%Y-%m-%d_%H%M)${LABEL:+_$LABEL}}   # e.g. 2026-10-10_1530_jwt
OUT=results/benchmarks/$RUN_ID
mkdir -p "$OUT"/{k6,stats,postgres,contract,logs}
K6_OUT="/results/benchmarks/$RUN_ID/k6"   # path of $OUT/k6 inside the k6 container
source scripts/lib.sh

# AUTH_MODE=jwt benchmarks the apps with HS256 bearer-token verification on every /readings request.
export AUTH_MODE=${AUTH_MODE:-none}
AUTH_TOKEN=""; [ "$AUTH_MODE" = jwt ] && AUTH_TOKEN=$(mint_token valid)
export AUTH_TOKEN

secs() { echo "${1%s}"; }

# ---------- environment ----------
# Resuming into an existing RUN_ID (e.g. RUN_ID=<old> STACKS=fastapi) keeps earlier results and adds the new stacks.
if [ -f "$OUT/env.txt" ]; then
  known=$(grep '^stacks=' "$OUT/env.txt" | cut -d= -f2)
  for s in $STACKS; do case " $known " in *" $s "*) ;; *) known="$known $s";; esac; done
  sed -i.bak "s|^stacks=.*|stacks=$known|" "$OUT/env.txt"; rm -f "$OUT/env.txt.bak"
  echo "resumed=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/env.txt"
else
{
  echo "run_id=$RUN_ID"
  echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  host_env
  echo "auth_mode=$AUTH_MODE"
  echo "stacks=$STACKS"; echo "workloads=$WORKLOADS"
  echo "vus=$VUS"; echo "warmup=$WARMUP"; echo "duration=$DURATION"; echo "reps=$REPS"
  echo "app_cpus=2"; echo "app_mem=4g"; echo "db_cpus=2"; echo "db_mem=2g"; echo "db_pool=20"
} > "$OUT/env.txt"
fi
[ -f "$OUT/cells.tsv" ] || : > "$OUT/cells.tsv"; [ -f "$OUT/stacks.tsv" ] || : > "$OUT/stacks.tsv"

# ---------- database ----------
pg_prepare || exit 1
docker image inspect "${POSTGRES_IMAGE:-postgres:17}" --format '{{.Id}}' > "$OUT/postgres/postgres.image" 2>/dev/null
$PSQL -c "select version()" > "$OUT/postgres/postgres.version"
PG_CID=$($DC ps -q postgres)

# ---------- stacks ----------
for stack in $STACKS; do
  svc="app-$stack"
  log "=================== $stack ==================="
  stop_apps
  restore_baseline || { log "baseline restore failed"; continue; }

  t0=$(date +%s)
  if ! $DC --profile "$stack" up -d --build "$svc" >"$OUT/logs/build-$stack.log" 2>&1; then
    log "$stack: build/start FAILED (see $OUT/logs/build-$stack.log)"
    echo "$stack	build_failed	0	0	0" >> "$OUT/stacks.tsv"; continue
  fi
  t1=$(date +%s)
  if ! wait_health; then
    log "$stack: never became healthy"; $DC logs --tail 60 "$svc" > "$OUT/logs/app-$stack.log" 2>&1
    echo "$stack	unhealthy	$((t1-t0))	0	0" >> "$OUT/stacks.tsv"; $DC stop "$svc" >/dev/null 2>&1; continue
  fi
  t2=$(date +%s)
  APP_CID=$($DC ps -q "$svc")
  log "$stack: healthy (build+create $((t1-t0))s, startup $((t2-t1))s)"
  $PSQL -tA -c "select count(*) from pg_stat_activity where usename='bench' and datname='sensorpulse' and pid <> pg_backend_pid()" > "$OUT/postgres/pgconns-$stack.txt"
  log "$stack: db sessions after start: $(cat "$OUT/postgres/pgconns-$stack.txt")"

  if [ "$AUTH_MODE" = jwt ]; then
    log "$stack: auth contract test"
    bash scripts/smoke-auth.sh > "$OUT/contract/auth-$stack.txt" 2>&1 || log "$stack: AUTH CONTRACT FAILED (see $OUT/contract/auth-$stack.txt)"
    restore_baseline   # smoke.sh needs the pristine baseline
    $DC --profile "$stack" restart "$svc" >/dev/null 2>&1; wait_health || log "$stack: unhealthy after restart"
  fi
  log "$stack: contract smoke test"
  if bash scripts/smoke.sh > "$OUT/contract/smoke-$stack.txt" 2>&1; then smoke=pass; else smoke=fail; fi
  log "$stack: smoke $smoke ($(tail -1 "$OUT/contract/smoke-$stack.txt"))"
  echo "$stack	$smoke	$((t1-t0))	$((t2-t1))	$APP_CID" >> "$OUT/stacks.tsv"

  for w in $WORKLOADS; do
    rep=1
    while [ "$rep" -le "$REPS" ]; do
      cell="$stack-$w-r$rep"
      k6() { k6_run -e WORKLOAD="$w" -e VUS="$VUS" -e RESULT_DIR="$K6_OUT" "$@" bench.js; }

      reset_rows
      log "$cell: warm-up $WARMUP"
      k6 -e DURATION="$WARMUP" -e RUN_ID="warm-$cell" >"$OUT/k6/warm-$cell.log" 2>&1

      attempt=1
      while :; do
        reset_rows
        rows_before=$(db_rows)
        sample_stats "$OUT/stats/stats-$cell.raw" "$APP_CID" "$PG_CID"
        log "$cell: measuring $DURATION at $VUS VUs (attempt $attempt)"
        k6 -e DURATION="$DURATION" -e RUN_ID="$cell" >"$OUT/k6/k6-$cell.log" 2>&1
        k6_exit=$?
        stop_samplers
        # A run is only valid if k6's own test clock matches the requested duration (host/VM stalls break this).
        if python3 - "$OUT/k6/$cell.json" "$(secs "$DURATION")" <<'PY'
import json, sys
try:
    ms = json.load(open(sys.argv[1]))["state"]["testRunDurationMs"]
except Exception:
    sys.exit(1)
want = float(sys.argv[2]) * 1000
sys.exit(0 if want * 0.97 <= ms <= want * 1.10 else 1)
PY
        then break; fi
        log "$cell: INVALID run (test clock off, host stalled?) attempt $attempt"
        if [ "$attempt" -ge 3 ]; then echo "$cell" >> "$OUT/invalid.txt"; break; fi
        attempt=$((attempt+1)); sleep 10
      done
      rows_after=$(db_rows)
      $PSQL -c "select calls, round(mean_exec_time::numeric,3), round(total_exec_time::numeric,0), left(regexp_replace(query,'\s+',' ','g'),90) from pg_stat_statements where query ilike '%readings%' and query not ilike '%pg_stat%' order by total_exec_time desc limit 6" \
        -F '|' > "$OUT/postgres/pgstmt-$cell.txt" 2>&1
      $PSQL -F '|' -c "select blks_hit, blks_read, xact_commit, xact_rollback, tup_inserted, temp_files from pg_stat_database where datname='sensorpulse'" > "$OUT/postgres/pgdb-$cell.txt" 2>&1
      echo "$stack	$w	$rep	$rows_before	$rows_after	$k6_exit" >> "$OUT/cells.tsv"
      log "$cell: done k6_exit=$k6_exit rows $rows_before -> $rows_after ($(grep -h '^run=' "$OUT/k6/k6-$cell.log" | tail -1))"
      rep=$((rep+1))
    done
  done

  docker inspect --format '{{.State.OOMKilled}} {{.RestartCount}} {{.Image}}' "$APP_CID" > "$OUT/logs/inspect-$stack.txt" 2>&1
  $DC logs --tail 40 "$svc" > "$OUT/logs/app-$stack.log" 2>&1
  log "$stack: oom/restarts/image: $(cat "$OUT/logs/inspect-$stack.txt")"
  $DC stop "$svc" >/dev/null 2>&1
  sleep 5
done

echo "finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/env.txt"
stop_apps
log "generating report"
python3 scripts/report.py bench "$OUT" && log "report: $OUT/report.html"
