import { CanActivate, ExecutionContext, Injectable, UseGuards } from '@nestjs/common';
import { createHmac, timingSafeEqual } from 'node:crypto';
import type { FastifyRequest } from 'fastify';
import { config } from './config';
import { unauthorized } from './errors';

const secret = Buffer.from(config.jwtSecret, 'utf8');
const b64url = (s: string): Buffer | null => (/^[A-Za-z0-9_-]+$/.test(s) ? Buffer.from(s, 'base64url') : null);

/**
 * Verifies an HS256 bearer token on every request (no caching of verified tokens).
 * Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
 * valid HMAC-SHA256 signature, integer exp in the future, non-empty sub.
 */
export function verifyJwt(header: string | undefined): boolean {
  if (!header || !header.startsWith('Bearer ')) return false;
  const parts = header.slice(7).split('.');
  if (parts.length !== 3 || parts.some((p) => p.length === 0)) return false;
  const [h, p, s] = parts;
  const sig = b64url(s);
  if (!sig) return false;
  const expected = createHmac('sha256', secret).update(`${h}.${p}`).digest();
  if (sig.length !== expected.length || !timingSafeEqual(sig, expected)) return false;
  try {
    const hb = b64url(h);
    const pb = b64url(p);
    if (!hb || !pb) return false;
    const hdr = JSON.parse(hb.toString('utf8'));
    if (hdr?.alg !== 'HS256') return false;
    const claims = JSON.parse(pb.toString('utf8'));
    // Number.isInteger(1700000000.0) is true in JS: a float exp that is integral cannot be told apart.
    return typeof claims?.sub === 'string' && claims.sub.length > 0 &&
      Number.isInteger(claims.exp) && claims.exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

@Injectable()
export class JwtGuard implements CanActivate {
  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest<FastifyRequest>();
    if (!verifyJwt(req.headers.authorization)) throw unauthorized();
    return true;
  }
}

/** Class decorator: guards a controller only when AUTH_MODE=jwt (no guard, no overhead otherwise). */
export const AuthGuard: ClassDecorator = config.authMode === 'jwt' ? UseGuards(JwtGuard) : () => undefined;
