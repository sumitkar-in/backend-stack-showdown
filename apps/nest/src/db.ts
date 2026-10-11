import { Global, Inject, Injectable, Module, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { Pool, types } from 'pg';
import { config } from './config';

export const PG_POOL = 'PG_POOL';

// int8 (id, COUNT, SUM) -> JS number; safe for the benchmark's data size.
types.setTypeParser(20, (v: string) => Number(v));
// timestamptz stays text ("2026-01-01 00:00:00.5+05:30", the server session runs in Asia/Kolkata): building a Date per row
// only to format it again is the most expensive part of reading a row. serializers.formatTs turns the text into ISO form.
types.setTypeParser(1184, (v: string) => v);

@Injectable()
export class PoolLifecycle implements OnModuleInit, OnModuleDestroy {
  constructor(@Inject(PG_POOL) private readonly pool: Pool) {}

  /** Open every connection before traffic starts (pool min == max). */
  async onModuleInit(): Promise<void> {
    const clients = await Promise.all(Array.from({ length: config.poolPerWorker }, () => this.pool.connect()));
    clients.forEach((c) => c.release());
  }

  async onModuleDestroy(): Promise<void> {
    await this.pool.end();
  }
}

@Global()
@Module({
  providers: [
    {
      provide: PG_POOL,
      useFactory: () => {
        const pool = new Pool({
          ...config.db,
          max: config.poolPerWorker,
          min: config.poolPerWorker,
          idleTimeoutMillis: 0,
          connectionTimeoutMillis: 10000,
          statement_timeout: 10000,
        });
        // An idle connection killed by the server (restart, failover) emits 'error'; unhandled it would crash the worker.
        pool.on('error', (e) => console.error('pg idle client error:', e.message));
        return pool;
      },
    },
    PoolLifecycle,
  ],
  exports: [PG_POOL],
})
export class DbModule {}
