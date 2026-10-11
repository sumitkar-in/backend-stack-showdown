import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from './app.module';
import { config } from './config';
import { ErrorFilter } from './errors';

/** One Nest/Fastify instance (with its own pg pool) per worker process. */
export async function startWorker(): Promise<void> {
  const adapter = new FastifyAdapter({
    logger: false,
    bodyLimit: 1024 * 1024,
    keepAliveTimeout: 60_000,
    connectionTimeout: 0,
  });
  // Keep the raw body so validation can split malformed JSON (400) from invalid fields (422).
  adapter
    .getInstance()
    .addContentTypeParser('application/json', { parseAs: 'buffer' }, (_req, body, done) => done(null, body));

  const app = await NestFactory.create<NestFastifyApplication>(AppModule, adapter, {
    logger: ['error'],
    bodyParser: false, // we registered the raw-buffer JSON parser above
  });
  app.useGlobalFilters(new ErrorFilter());
  app.enableShutdownHooks();
  await app.listen(config.port, '0.0.0.0');
}
