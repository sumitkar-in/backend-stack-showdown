# How to operate the benchmark

From the bundle root:

```bash
# 1. First boot and seed (only on a FRESH named pgdata volume)
docker compose -f infra/compose.yaml up -d postgres

# 2. Verify database is ready and exact seeded row counts
docker compose -f infra/compose.yaml exec -T postgres \
  psql -U bench -d sensorpulse -f /docker-entrypoint-initdb.d/verify.sql

# 3. Once apps/go has a Dockerfile and implementation:
docker compose -f infra/compose.yaml --profile go up -d --build app-go
curl -fsS http://localhost:8080/health

# 4. k6 warm-up, read-only
mkdir -p results
docker compose -f infra/compose.yaml --profile tools run --rm \
  -e BASE_URL=http://app-go:8080 -e WORKLOAD=pk \
  -e VUS=100 -e DURATION=30s -e RUN_ID=go-pk-warmup \
  k6 run /scripts/bench.js

# 5. k6 measured read-only run
docker compose -f infra/compose.yaml --profile tools run --rm \
  -e BASE_URL=http://app-go:8080 -e WORKLOAD=pk \
  -e VUS=100 -e DURATION=2m -e RUN_ID=go-pk-rep1 \
  k6 run /scripts/bench.js

# 6. Stop Go before starting any other stack (same host port)
docker compose -f infra/compose.yaml stop app-go
```

## Write/mixed reset procedure

To retain an exactly identical baseline for every measured write or mixed run:

1. With only DB running, save a snapshot **after** 1M seed and index setup. Example (host stores compressed dump):

   `docker compose -f infra/compose.yaml exec -T postgres pg_dump -U bench -d sensorpulse -Fc > results/baseline.dump`

2. Stop the benchmark application and ensure no app DB sessions before restoring. For a disposable benchmark DB, a suitable method is to drop/recreate the database through a *separate administrative connection*, then restore the snapshot. Example commands (run only on this disposable benchmark instance; **destructive**):

   ```bash
   docker compose -f infra/compose.yaml exec -T postgres \
     psql -U bench -d postgres -c 'DROP DATABASE IF EXISTS sensorpulse WITH (FORCE);'
   docker compose -f infra/compose.yaml exec -T postgres \
     psql -U bench -d postgres -c 'CREATE DATABASE sensorpulse OWNER bench;'
   docker compose -f infra/compose.yaml exec -T postgres \
     pg_restore -U bench -d sensorpulse --no-owner --no-privileges \
     < results/baseline.dump
   ```

   This example pipes the host-side custom-format dump into `pg_restore`'s standard input. It is destructive to the benchmark database and must **never** be pointed at a production database. Re-run `db/verify.sql` after restore.

3. Start the app, validate and warm it. For write workloads, restore again after warm-up. After a consistent DB cache-primer step and metrics reset, start the measured 120-second run.
4. Record DB row count before and after the run and save k6 + Docker + Postgres metrics. Restore baseline before the next run.
5. Use a dedicated script/orchestrator to repeat 5 times and shuffle stack order. Do not allow multiple app services to run simultaneously.

## Suggested experiment matrix

Rows: Go, Java, NestJS, FastAPI, Rust.
Columns: `health`, `pk`, `range`, `stats`, `insert`, `batch`, `mixed`.
5 repetitions of each row-column combination, with 100 VUs and 120s measured duration (175 runs). To keep initial iteration small, first complete a three-workload smoke matrix: `health`, `pk`, `insert` x 1 repetition.

Track workload and whether DB was reset, response count/error rate, PG query-call totals, app vCPU-throttling and mean/max RSS. A read-only throughput result from a fresh DB must not be compared against the same workload after millions of inserts.
