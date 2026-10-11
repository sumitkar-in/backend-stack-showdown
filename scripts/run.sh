#!/usr/bin/env bash
# One command for the whole lab: auth tests, the 100-VU benchmark, the ramp test, then the combined report.
#
#   scripts/run.sh                          # auth + bench + ramp + report, every stack
#   scripts/run.sh bench ramp               # only some stages (auth | bench | ramp | authcost | report)
#   STACKS="go rust" scripts/run.sh         # subset of stacks
#   QUICK=1 scripts/run.sh                  # smoke-sized run (~10x shorter: 8 s measured, 4 ramp steps) to check the setup
#   FULL=1 scripts/run.sh                   # also run `authcost` (same workloads with and without JWT, for the overhead table)
#   LABEL=night scripts/run.sh              # names the run folders <date>_<time>_night; all stages share one run id
#
# Stages run in order and one failing does not stop the next; the exit code is non-zero if any failed.
# Any variable the stage scripts understand (DURATION, WARMUP, REPS, WORKLOADS, RATES, STEP_DUR, VUS, ...) is passed through.
set -uo pipefail
cd "$(dirname "$0")/.."

ALL_STAGES="auth bench ramp"; [ -n "${FULL:-}" ] && ALL_STAGES="$ALL_STAGES authcost"
STAGES=${*:-$ALL_STAGES}
for s in $STAGES; do
  case $s in auth|bench|ramp|authcost|report) ;; *) echo "unknown stage: $s (auth | bench | ramp | authcost | report)" >&2; exit 2;; esac
done

export STACKS=${STACKS:-"nest spring go rust fastapi laravel octane graalvm"}
export RUN_ID=${RUN_ID:-$(date +%Y-%m-%d_%H%M)${LABEL:+_$LABEL}}
if [ -n "${QUICK:-}" ]; then
  export WARMUP=${WARMUP:-3s} DURATION=${DURATION:-8s} STEP_DUR=${STEP_DUR:-5} WARM_DUR=${WARM_DUR:-3}
  export RATES=${RATES:-"500,2000,8000,24000"} WORKLOADS_BENCH=${WORKLOADS_BENCH:-"pk mixed"}
fi

declare -a RESULTS=()
run_stage() { # name command...
  local name=$1; shift
  echo; echo "################ $name  (run $RUN_ID) ################"
  local t=$SECONDS
  if "$@"; then RESULTS+=("ok     $name ($((SECONDS - t))s)"); else RESULTS+=("FAILED $name (exit $?, $((SECONDS - t))s)"); FAILED=1; fi
}
FAILED=0

for stage in $STAGES; do
  case $stage in
    auth)  run_stage auth  scripts/run-auth-test.sh ;;
    bench) run_stage bench env ${WORKLOADS_BENCH:+WORKLOADS="$WORKLOADS_BENCH"} scripts/run-benchmark.sh ;;
    ramp)  run_stage ramp  scripts/run-ramp.sh ;;
    authcost)
      # same workloads twice, differing only in AUTH_MODE; the report pairs them automatically
      run_stage authcost-noauth env RUN_ID="${RUN_ID}_noauth" AUTH_MODE=none WORKLOADS="${AUTHCOST_WORKLOADS:-pk range mixed}" scripts/run-benchmark.sh
      run_stage authcost-jwt    env RUN_ID="${RUN_ID}_jwt"    AUTH_MODE=jwt  WORKLOADS="${AUTHCOST_WORKLOADS:-pk range mixed}" scripts/run-benchmark.sh ;;
    report) ;;
  esac
done

echo; echo "################ report ################"
python3 scripts/report.py refresh
echo; printf '%s\n' "${RESULTS[@]}"
echo "combined report: $PWD/results/report.html"
exit $FAILED
