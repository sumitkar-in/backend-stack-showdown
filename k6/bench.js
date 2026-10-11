import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const BASE = __ENV.BASE_URL || 'http://app:8080';
const WORKLOAD = __ENV.WORKLOAD || 'mixed';
const DURATION = __ENV.DURATION || '2m';
const VUS = Number(__ENV.VUS || '100');
const RESULT_DIR = __ENV.RESULT_DIR || '/results';
const AUTH = __ENV.AUTH_TOKEN ? { Authorization: `Bearer ${__ENV.AUTH_TOKEN}` } : {};
const HEADERS = { headers: { 'Content-Type': 'application/json', ...AUTH }, timeout: '10s' };
// Asia/Kolkata (+05:30, no DST): shift the instant by 5h30m, render with toISOString, swap Z for the offset.
const ist = (ms) => new Date(ms + 19800000).toISOString().replace('Z', '+05:30');
const FROM = '2026-01-01T00:00:00.000+05:30';
const TO = '2026-01-13T00:00:00.000+05:30';
const Q = `from=${encodeURIComponent(FROM)}&to=${encodeURIComponent(TO)}`;

export const options = {
  scenarios: {
    benchmark: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
      gracefulStop: '15s',
      exec: 'benchmark',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: { http_req_failed: ['rate<0.01'], checks: ['rate>0.99'] },
};

// Key selection is independent of the operation mix (mixed mode used to correlate them).
function key() {
  return exec.vu.idInTest * 7919 + exec.vu.iterationInScenario * 104729;
}
function device(k) { return (k % 1000) + 1; }
function readingId(k) { return (Math.imul(k, 2654435761) >>> 0) % 1000000 + 1; }
function tagged(kind) { return { ...HEADERS, tags: { operation: kind, name: kind } }; } // name groups URLs: unique URLs would explode metric cardinality (OOM)
function status(r, code) { check(r, { [`status_${code}`]: (x) => x.status === code }); }
function reading(k) {
  return {
    deviceId: device(k),
    temperatureCenti: 1800 + ((k * 37) % 1701),
    humidityBp: 3000 + ((k * 11) % 6001),
    // spread over 30 days after the seed so inserts hit varied index positions
    observedAt: ist(Date.parse('2026-02-01T00:00:00.000+05:30') + (k % 2592000) * 1000),
  };
}

// Every 100th iteration also verifies the body, so "fast but wrong" responses cannot pass.
function deepCheck(kind, r, k) {
  const body = r.json();
  if (kind === 'pk') {
    check(body, { pk_shape: (b) => b.id === readingId(k) && typeof b.observedAt === 'string' });
  } else if (kind === 'range') {
    check(body, {
      range_shape: (b) => b.items.length === 50 && b.items.every((x) => x.deviceId === device(k)) &&
        b.items[0].observedAt >= b.items[49].observedAt,
    });
  } else if (kind === 'stats') {
    check(body, { stats_shape: (b) => b.deviceId === device(k) && b.count === 1000 });
  } else if (kind === 'insert') {
    check(body, { insert_shape: (b) => b.deviceId === device(k) && b.id > 1000000 });
  } else if (kind === 'batch') {
    check(body, { batch_shape: (b) => b.inserted === 10 });
  }
}

function one(kind, k, deep) {
  let r;
  let code = 200;
  switch (kind) {
    case 'health':
      r = http.get(`${BASE}/health`, tagged(kind)); break;
    case 'pk':
      r = http.get(`${BASE}/readings/${readingId(k)}`, tagged(kind)); break;
    case 'range':
      r = http.get(`${BASE}/readings?deviceId=${device(k)}&${Q}&limit=50&offset=0`, tagged(kind)); break;
    case 'stats':
      r = http.get(`${BASE}/readings/stats?deviceId=${device(k)}&${Q}`, tagged(kind)); break;
    case 'insert':
      r = http.post(`${BASE}/readings`, JSON.stringify(reading(k)), tagged(kind)); code = 201; break;
    case 'batch':
      r = http.post(`${BASE}/readings/batch`,
        JSON.stringify({ readings: Array.from({ length: 10 }, (_, i) => reading(k * 10 + i)) }), tagged(kind));
      code = 201; break;
    default:
      throw new Error(`Unknown workload: ${kind}`);
  }
  status(r, code);
  if (deep && r.status === code && kind !== 'health') deepCheck(kind, r, k);
}

export function benchmark() {
  const k = key();
  const iter = exec.scenario.iterationInTest;
  const deep = iter % 100 === 0;
  if (WORKLOAD !== 'mixed') { one(WORKLOAD, k, deep); return; }
  // exact 50% pk, 30% range, 10% stats, 9% insert, 1% batch (37 is coprime to 100)
  const slot = (iter * 37 + 11) % 100;
  const kind = slot < 50 ? 'pk' : slot < 80 ? 'range' : slot < 90 ? 'stats' : slot < 99 ? 'insert' : 'batch';
  one(kind, k, deep);
}

export function handleSummary(data) {
  const runId = (__ENV.RUN_ID || 'manual').replace(/[^A-Za-z0-9_.-]/g, '_');
  const m = data.metrics;
  const rps = m.http_reqs?.values?.rate ?? 0;
  return {
    [`${RESULT_DIR}/${runId}.json`]: JSON.stringify(data, null, 2),
    stdout: `\nrun=${runId} workload=${WORKLOAD} rps=${rps.toFixed(1)} p95_ms=${m.http_req_duration?.values?.['p(95)']}\n`,
  };
}
