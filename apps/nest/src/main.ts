import cluster from 'node:cluster';
import { config } from './config';

if (cluster.isPrimary) {
  const workers = Array.from({ length: config.workers }, () => cluster.fork());
  let stopping = false;

  // A dying worker invalidates a benchmark run: fail loudly instead of silently respawning.
  cluster.on('exit', (worker, code, signal) => {
    if (!stopping) {
      console.error(`worker ${worker.process.pid} exited unexpectedly (code=${code} signal=${signal})`);
      process.exit(1);
    }
    if (Object.values(cluster.workers ?? {}).every((w) => !w || w.isDead())) process.exit(0);
  });

  const stop = () => {
    if (stopping) return;
    stopping = true;
    workers.forEach((w) => w.process.kill('SIGTERM'));
    setTimeout(() => process.exit(1), 10_000).unref();
  };
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
} else {
  void import('./server').then((m) => m.startWorker()).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
