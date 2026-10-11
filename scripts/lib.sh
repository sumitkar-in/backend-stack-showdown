#!/usr/bin/env bash
# Shared helpers for run-benchmark.sh, run-ramp.sh and run-auth-test.sh. Source it from the repo root, after setting OUT:
#   cd "$(dirname "$0")/.."; OUT=results/<kind>/$RUN_ID; source scripts/lib.sh
# Provides: DC PSQL PSQL_ADMIN BASE, log, stop_apps, wait_health, pg_prepare, restore_baseline, reset_rows, host_env,
#           sample_stats, k6_run, new_run_id, mint_token, and an EXIT/INT/TERM trap that stops samplers and app containers.

for _c in docker curl python3; do
  command -v "$_c" >/dev/null || { echo "missing required tool: $_c" >&2; exit 1; }
done
[ -f .env ] || { echo "missing .env (cp .env.example .env, then set PLATFORM)" >&2; exit 1; }

DC="docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml"
_PSQL_BASE="$DC exec -T -e PGUSER=bench -e PGPASSWORD=bench_local_only"
PSQL="$_PSQL_BASE -e PGDATABASE=sensorpulse postgres psql -v ON_ERROR_STOP=1 -tAq"
PSQL_ADMIN="$_PSQL_BASE -e PGDATABASE=postgres postgres psql -v ON_ERROR_STOP=1 -q"
export PSQL BASE=${BASE:-http://localhost:8080} JWT_SECRET=${JWT_SECRET:-bench-jwt-secret-local-only}

new_run_id() { echo "$(date +%Y-%m-%d_%H%M)${LABEL:+_$LABEL}"; }   # e.g. 2026-10-10_1530_jwt
mint_token() { python3 scripts/jwt.py "$1"; }
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/run.log"; }

# Keep the Mac awake while the script runs (a sleeping host invalidates timings).
command -v caffeinate >/dev/null && { caffeinate -dims -w $$ >/dev/null 2>&1 & }

# ---------- cleanup: Ctrl-C or an error must not leave samplers or app containers running ----------
SAMPLER_PIDS=()
stop_samplers() {
  [ "${#SAMPLER_PIDS[@]}" -gt 0 ] || return 0
  kill "${SAMPLER_PIDS[@]}" 2>/dev/null; wait "${SAMPLER_PIDS[@]}" 2>/dev/null
  SAMPLER_PIDS=()
}
stop_apps() {
  local ids; ids=$(docker ps -q --filter "name=sensorpulse-bench-app-")
  [ -z "$ids" ] || docker stop -t 15 $ids >/dev/null 2>&1
  return 0
}
_cleanup() { stop_samplers; stop_apps; }
trap _cleanup EXIT
trap 'echo; echo "interrupted"; exit 130' INT TERM

wait_health() { # [seconds=120]
  local i
  for i in $(seq "${1:-120}"); do curl -fsS -m 2 "$BASE/health" >/dev/null 2>&1 && return 0; sleep 1; done
  return 1
}

# ---------- database ----------
db_rows() { # row count; retried because a one-off psql/docker hiccup used to leave an empty value in cells.tsv
  local i n
  for i in 1 2 3 4 5; do
    n=$($PSQL -c "select count(*) from readings" 2>/dev/null)
    [ -n "$n" ] && { echo "$n"; return 0; }
    sleep 2
  done
  return 1
}
reset_rows() { $PSQL < scripts/pg/reset.sql >/dev/null 2>&1; }           # trim to the 1,000,000 baseline rows, vacuum, prewarm
restore_baseline() { $PSQL_ADMIN < scripts/pg/restore.sql >>"$OUT/run.log" 2>&1; }   # recreate the DB from the template

# Start PostgreSQL, make sure exactly 1,000,000 rows exist, and create the baseline template database if missing.
pg_prepare() {
  log "starting postgres (first start seeds 1,000,000 readings)"
  $DC up -d --wait postgres >>"$OUT/run.log" 2>&1 || { log "postgres failed to start"; return 1; }
  local rows; rows=$(db_rows)
  if [ "${rows:-0}" -gt 1000000 ] 2>/dev/null; then reset_rows; rows=$(db_rows); fi   # leftovers from an earlier run
  log "readings in database: $rows"
  [ "$rows" = "1000000" ] || { log "expected 1000000 rows (fresh volume needed: docker compose down -v)"; return 1; }
  if [ "$($PSQL_ADMIN -tA -c "select 1 from pg_database where datname='sensorpulse_tpl'")" != "1" ]; then
    log "creating baseline template database"
    $PSQL -c "VACUUM (FREEZE, ANALYZE) readings" >/dev/null
    $PSQL_ADMIN < scripts/pg/make-template.sql >>"$OUT/run.log" 2>&1 || { log "template creation failed"; return 1; }
  fi
}

# ---------- environment record ----------
host_env() { # prints key=value lines describing the machine
  echo "host=$(uname -srm)"
  echo "host_cpu=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || grep -m1 'model name' /proc/cpuinfo 2>/dev/null)"
  echo "host_cores=$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
  echo "host_mem_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))"
  local info; info=$(docker info --format '{{.ServerVersion}}|{{.OperatingSystem}}|{{.NCPU}}|{{.MemTotal}}|{{.Architecture}}')
  IFS='|' read -r ver os ncpu mem arch <<<"$info"
  echo "docker=$ver / $os"
  echo "docker_vm_cpus=$ncpu"
  echo "docker_vm_mem_gb=$(awk -v m="$mem" 'BEGIN{printf "%.1f", m/1073741824}')"
  echo "docker_arch=$arch"
}

# ---------- load + sampling ----------
# sample_stats FILE [ts] CONTAINER...   background `docker stats` sampler; with "ts" every line is prefixed by an epoch time
sample_stats() {
  local file=$1 ts=""; shift
  [ "${1:-}" = ts ] && { ts=1; shift; }
  if [ -n "$ts" ]; then
    docker stats --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' "$@" 2>/dev/null \
      | python3 -u -c "import sys,time
for l in sys.stdin: print(time.time(), l, end='', flush=True)" > "$file" &
  else
    docker stats --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' "$@" > "$file" 2>/dev/null &
  fi
  SAMPLER_PIDS+=($!)
}

# k6_run [-e KEY=VAL ...] SCRIPT   run k6 in the tools profile against the app (alias `app` on the bench network)
k6_run() {
  local script=${!#} args=("${@:1:$#-1}")
  $DC --profile tools run --rm -T -e BASE_URL=http://app:8080 -e AUTH_TOKEN="${AUTH_TOKEN:-}" "${args[@]}" k6 run "/scripts/$script"
}
