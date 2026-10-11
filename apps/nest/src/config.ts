const num = (key: string, def: number): number => {
  const v = process.env[key];
  return v ? Number(v) : def;
};

export const config = {
  port: num('PORT', 8080),
  workers: num('APP_WORKERS', 2),
  poolPerWorker: num('DB_POOL_PER_WORKER', 10),
  poolTotal: num('DB_POOL_TOTAL', 20),
  authMode: process.env.AUTH_MODE ?? 'none',
  jwtSecret: process.env.JWT_SECRET ?? 'bench-jwt-secret-local-only',
  db: {
    host: process.env.DB_HOST ?? 'postgres',
    port: num('DB_PORT', 5432),
    database: process.env.DB_NAME ?? 'sensorpulse',
    user: process.env.DB_USER ?? 'bench',
    password: process.env.DB_PASSWORD ?? '',
  },
};

if (config.poolPerWorker * config.workers !== config.poolTotal) {
  throw new Error(
    `pool mismatch: ${config.poolPerWorker} x ${config.workers} workers != DB_POOL_TOTAL=${config.poolTotal}`,
  );
}
