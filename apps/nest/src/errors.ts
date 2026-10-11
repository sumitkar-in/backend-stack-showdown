import { ArgumentsHost, Catch, ExceptionFilter } from '@nestjs/common';
import type { FastifyReply } from 'fastify';

export const BODY = {
  health: '{"status":"ok"}',
  badRequest: '{"error":"bad_request"}',
  notFound: '{"error":"not_found"}',
  unauthorized: '{"error":"unauthorized"}',
  invalid: '{"error":"validation_error"}',
  internal: '{"error":"internal"}',
} as const;

export class ApiError extends Error {
  constructor(readonly status: number, readonly body: string) {
    super(body);
  }
}

export const badRequest = () => new ApiError(400, BODY.badRequest);
export const invalid = () => new ApiError(422, BODY.invalid);
export const notFound = () => new ApiError(404, BODY.notFound);
export const unauthorized = () => new ApiError(401, BODY.unauthorized);

/** Normalizes every error (ours, Nest's, Fastify's) to the canonical JSON shape. */
@Catch()
export class ErrorFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost): void {
    const reply = host.switchToHttp().getResponse<FastifyReply>();
    let status = 500;
    let body: string = BODY.internal;
    if (exception instanceof ApiError) {
      status = exception.status;
      body = exception.body;
    } else {
      const s = (exception as { status?: number; statusCode?: number }).status ??
        (exception as { statusCode?: number }).statusCode;
      if (s === 404 || s === 405) {
        status = 404;
        body = BODY.notFound;
      } else if (typeof s === 'number' && s >= 400 && s < 500) {
        status = 400; // unsupported media type, payload too large, ...
        body = BODY.badRequest;
      }
    }
    if (status === 401) void reply.header('WWW-Authenticate', 'Bearer');
    void reply.status(status).header('Content-Type', 'application/json').send(body);
  }
}
