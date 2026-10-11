// Stepped open-model ramp: offered request rate climbs step by step; per-step latency is recorded
// in its own Trend so the report can show where p95 crosses a threshold and where the stack breaks.
import http from 'k6/http';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://app:8080';
const WORKLOAD = __ENV.WORKLOAD || 'pk';
const RATES = (__ENV.RATES || '250,500,1000,2000,3000,4000,6000,8000,12000,16000,24000,32000,48000').split(',').map(Number);
const STEP = Number(__ENV.STEP_DUR || '15');      // seconds per step
const WARM_RATE = Number(__ENV.WARM_RATE || '1000');
const WARM = Number(__ENV.WARM_DUR || '15');
const AUTH = __ENV.AUTH_TOKEN ? { Authorization: `Bearer ${__ENV.AUTH_TOKEN}` } : {};
const RESULT_DIR = __ENV.RESULT_DIR || '/results';
const MAX_VUS = Number(__ENV.MAX_VUS || '1000');   // cap: beyond this the iterations are dropped (= saturated)
const FROM = '2026-01-01T00:00:00.000+05:30';
const TO = '2026-01-13T00:00:00.000+05:30';
const Q = `from=${encodeURIComponent(FROM)}&to=${encodeURIComponent(TO)}`;

const lat = RATES.map((_, i) => new Trend(`lat_${i}`, true));
const reqs = RATES.map((_, i) => new Counter(`reqs_${i}`));
const errs = RATES.map((_, i) => new Counter(`errs_${i}`));

const vusFor = (rate) => Math.min(Math.max(20, Math.ceil(rate / 20)), MAX_VUS);

const scenarios = {
  warm: {
    executor: 'constant-arrival-rate', rate: WARM_RATE, timeUnit: '1s', duration: `${WARM}s`,
    preAllocatedVUs: vusFor(WARM_RATE), maxVUs: MAX_VUS, exec: 'warm', gracefulStop: '5s',
  },
};
const thresholds = {};
RATES.forEach((rate, i) => {
  scenarios[`step_${i}`] = {
    executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration: `${STEP}s`,
    startTime: `${WARM + i * STEP}s`, preAllocatedVUs: vusFor(rate), maxVUs: MAX_VUS,
    exec: 'step', env: { STEP_IDX: String(i) }, gracefulStop: '5s',
  };
  thresholds[`dropped_iterations{scenario:step_${i}}`] = ['count>=0']; // exposes the per-step count in the summary
});

export const options = {
  scenarios,
  thresholds,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'],
  discardResponseBodies: false,
};

function call() {
  const dev = Math.floor(Math.random() * 1000) + 1;
  switch (WORKLOAD) {
    case 'health': return [http.get(`${BASE}/health`, { headers: AUTH, tags: { name: 'health' } }), 200];
    case 'pk': return [http.get(`${BASE}/readings/${Math.floor(Math.random() * 1000000) + 1}`, { headers: AUTH, tags: { name: 'pk' } }), 200];
    case 'range': return [http.get(`${BASE}/readings?deviceId=${dev}&${Q}&limit=50&offset=0`, { headers: AUTH, tags: { name: 'range' } }), 200];
    case 'stats': return [http.get(`${BASE}/readings/stats?deviceId=${dev}&${Q}`, { headers: AUTH, tags: { name: 'stats' } }), 200];
    case 'insert': {
      const body = JSON.stringify({ deviceId: dev, temperatureCenti: 2000, humidityBp: 5000, observedAt: '2026-02-01T00:00:00.000+05:30' });
      return [http.post(`${BASE}/readings`, body, { headers: { 'Content-Type': 'application/json', ...AUTH }, tags: { name: 'insert' } }), 201];
    }
    default: throw new Error(`Unknown workload ${WORKLOAD}`);
  }
}

export function warm() { call(); }

export function step() {
  const i = Number(__ENV.STEP_IDX);
  const [r, want] = call();
  lat[i].add(r.timings.duration);
  reqs[i].add(1);
  if (r.status !== want) errs[i].add(1);
}

const val = (m, k, d = 0) => (m && m.values && m.values[k] !== undefined ? m.values[k] : d);

export function handleSummary(data) {
  const runId = (__ENV.RUN_ID || 'ramp').replace(/[^A-Za-z0-9_.-]/g, '_');
  const m = data.metrics;
  const steps = RATES.map((rate, i) => ({
    step: i, offered: rate, seconds: STEP,
    count: val(m[`reqs_${i}`], 'count'), errors: val(m[`errs_${i}`], 'count'),
    dropped: val(m[`dropped_iterations{scenario:step_${i}}`], 'count'),
    avg: val(m[`lat_${i}`], 'avg', null), p50: val(m[`lat_${i}`], 'med', null), p90: val(m[`lat_${i}`], 'p(90)', null),
    p95: val(m[`lat_${i}`], 'p(95)', null), p99: val(m[`lat_${i}`], 'p(99)', null), max: val(m[`lat_${i}`], 'max', null),
  }));
  const out = { workload: WORKLOAD, stepSeconds: STEP, warmSeconds: WARM, maxVus: MAX_VUS, steps };
  return {
    [`${RESULT_DIR}/${runId}.json`]: JSON.stringify(out, null, 2),
    stdout: `\nramp ${runId}: ${steps.map((s) => `${s.offered}->p95=${s.p95 === null ? 'n/a' : s.p95.toFixed(2)}ms`).join('  ')}\n`,
  };
}
