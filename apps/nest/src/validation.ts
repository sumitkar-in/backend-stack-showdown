import { badRequest, invalid } from './errors';

const RE_ID = /^[1-9][0-9]{0,17}$/;
const RE_DEVICE = /^[1-9][0-9]{0,8}$/;
const RE_UINT = /^[0-9]{1,4}$/;
const RE_TS =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,3})?(?:Z|[+-][0-9]{2}:[0-9]{2})$/;

export type Query = Record<string, string | string[] | undefined>;
export type ReadingArgs = [number, number, number, Date];

const daysInMonth = (y: number, m: number): number =>
  m === 2 ? (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28) : [4, 6, 9, 11].includes(m) ? 30 : 31;

/** RFC3339 with timezone and at most 3 fractional digits -> Date (an instant; responses render it as +05:30) or null. */
export function parseTs(value: unknown): Date | null {
  if (typeof value !== 'string') return null;
  const m = RE_TS.exec(value);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = [m[1], m[2], m[3], m[4], m[5], m[6]].map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > daysInMonth(y, mo) || h > 23 || mi > 59 || s > 59) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Query value only when the parameter appears exactly once. */
function single(q: Query, name: string): string | undefined {
  const v = q[name];
  return typeof v === 'string' ? v : undefined;
}

export function parseId(raw: string): number {
  if (!RE_ID.test(raw)) throw invalid();
  return Number(raw);
}

export function parseDeviceRange(q: Query): { device: number; from: Date; to: Date } {
  const dev = single(q, 'deviceId');
  const from = parseTs(single(q, 'from'));
  const to = parseTs(single(q, 'to'));
  if (dev === undefined || !RE_DEVICE.test(dev) || !from || !to || from >= to) throw invalid();
  return { device: Number(dev), from, to };
}

export function parsePaging(q: Query): { limit: number; offset: number } {
  const lim = 'limit' in q ? single(q, 'limit') : '50';
  const off = 'offset' in q ? single(q, 'offset') : '0';
  if (lim === undefined || off === undefined || !RE_UINT.test(lim) || !RE_UINT.test(off)) throw invalid();
  const limit = Number(lim);
  const offset = Number(off);
  if (limit < 1 || limit > 100 || offset > 1000) throw invalid();
  return { limit, offset };
}

/**
 * Stage 1: malformed JSON -> 400.
 * Limitation: JS cannot tell 2375.0 from 2375, so only non-integer numbers are rejected later.
 */
export function parseJson(body: unknown): unknown {
  try {
    return JSON.parse(Buffer.isBuffer(body) ? body.toString('utf8') : String(body));
  } catch {
    throw badRequest();
  }
}

const isInt = (v: unknown, lo: number, hi: number): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= lo && v <= hi;

/** One reading object -> pg args, or null when invalid. */
export function readingArgs(v: unknown): ReadingArgs | null {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return null;
  const o = v as Record<string, unknown>;
  const at = parseTs(o.observedAt);
  if (
    !isInt(o.deviceId, 1, 2147483647) ||
    !isInt(o.temperatureCenti, -5000, 10000) ||
    !isInt(o.humidityBp, 0, 10000) ||
    !at
  ) {
    return null;
  }
  return [o.deviceId, o.temperatureCenti, o.humidityBp, at];
}

/** 1-100 readings -> flat pg args, or null when any is invalid. */
export function batchArgs(body: unknown): unknown[] | null {
  const items = (body as { readings?: unknown } | null)?.readings;
  if (!Array.isArray(items) || items.length < 1 || items.length > 100) return null;
  const flat: unknown[] = [];
  for (const it of items) {
    const a = readingArgs(it);
    if (!a) return null;
    flat.push(...a);
  }
  return flat;
}
