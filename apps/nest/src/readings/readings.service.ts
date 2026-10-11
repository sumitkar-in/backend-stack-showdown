import { Inject, Injectable } from '@nestjs/common';
import { Pool } from 'pg';
import { PG_POOL } from '../db';
import { invalid, notFound } from '../errors';
import * as serializers from '../serializers';
import * as sql from '../sql';
import * as v from '../validation';

const isConstraintError = (e: unknown): boolean => {
  const code = (e as { code?: string }).code;
  return code === '23503' || code === '23514'; // FK / CHECK -> 422
};

// Named queries => server-side prepared statements per connection (parity with pgx/asyncpg).
@Injectable()
export class ReadingsService {
  constructor(@Inject(PG_POOL) private readonly pool: Pool) {}

  async getById(rawId: string): Promise<string> {
    const id = v.parseId(rawId);
    const { rows } = await this.pool.query<serializers.ReadingRow>({ name: 'by_id', text: sql.BY_ID, values: [id] });
    if (rows.length === 0) throw notFound();
    return JSON.stringify(serializers.reading(rows[0]));
  }

  async list(q: v.Query): Promise<string> {
    const { device, from, to } = v.parseDeviceRange(q);
    const { limit, offset } = v.parsePaging(q);
    const { rows } = await this.pool.query<serializers.ReadingRow>({
      name: 'list',
      text: sql.LIST,
      values: [device, from, to, limit, offset],
    });
    return JSON.stringify({ items: rows.map(serializers.reading), limit, offset });
  }

  async stats(q: v.Query): Promise<string> {
    const { device, from, to } = v.parseDeviceRange(q);
    const { rows } = await this.pool.query<serializers.StatsRow>({
      name: 'stats',
      text: sql.STATS,
      values: [device, from, to],
    });
    return JSON.stringify(serializers.stats(device, rows[0]));
  }

  async create(rawBody: unknown): Promise<string> {
    const args = v.readingArgs(v.parseJson(rawBody));
    if (!args) throw invalid();
    try {
      const { rows } = await this.pool.query<serializers.ReadingRow>({ name: 'insert', text: sql.INSERT, values: args });
      return JSON.stringify(serializers.reading(rows[0]));
    } catch (e) {
      throw isConstraintError(e) ? invalid() : e;
    }
  }

  async createBatch(rawBody: unknown): Promise<string> {
    const body = v.parseJson(rawBody);
    if (typeof body !== 'object' || body === null || Array.isArray(body)) throw invalid();
    const args = v.batchArgs(body);
    if (!args) throw invalid();
    const n = args.length / 4;
    try {
      await this.pool.query({ name: `batch_${n}`, text: sql.batchInsert(n), values: args });
      return JSON.stringify({ inserted: n });
    } catch (e) {
      throw isConstraintError(e) ? invalid() : e;
    }
  }
}
