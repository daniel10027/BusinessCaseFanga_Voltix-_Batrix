import { ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac } from 'crypto';
import { HmacGuard, SIGNATURE_HEADER } from '../src/swaps/hmac.guard';

const SECRET = 'test-secret';

function contextWith(headers: Record<string, string>, rawBody?: Buffer): ExecutionContext {
  const request = { headers, rawBody };
  return {
    switchToHttp: () => ({
      getRequest: () => request,
    }),
  } as unknown as ExecutionContext;
}

function configWithSecret(secret: string | undefined): ConfigService {
  return { get: () => secret } as unknown as ConfigService;
}

describe('HmacGuard', () => {
  it('accepts a request signed with the correct secret', () => {
    const body = Buffer.from(JSON.stringify({ hello: 'world' }));
    const signature = createHmac('sha256', SECRET).update(body).digest('hex');
    const guard = new HmacGuard(configWithSecret(SECRET));

    const result = guard.canActivate(contextWith({ [SIGNATURE_HEADER]: signature }, body));

    expect(result).toBe(true);
  });

  it('rejects a request with an invalid signature', () => {
    const body = Buffer.from(JSON.stringify({ hello: 'world' }));
    const guard = new HmacGuard(configWithSecret(SECRET));

    expect(() =>
      guard.canActivate(contextWith({ [SIGNATURE_HEADER]: 'deadbeef' }, body)),
    ).toThrow(UnauthorizedException);
  });

  it('rejects a request with no signature header', () => {
    const body = Buffer.from(JSON.stringify({ hello: 'world' }));
    const guard = new HmacGuard(configWithSecret(SECRET));

    expect(() => guard.canActivate(contextWith({}, body))).toThrow(UnauthorizedException);
  });

  it('rejects a request with no raw body available', () => {
    const signature = createHmac('sha256', SECRET).update('anything').digest('hex');
    const guard = new HmacGuard(configWithSecret(SECRET));

    expect(() =>
      guard.canActivate(contextWith({ [SIGNATURE_HEADER]: signature }, undefined)),
    ).toThrow(UnauthorizedException);
  });

  it('refuses to validate anything when the secret itself is not configured', () => {
    const body = Buffer.from('{}');
    const guard = new HmacGuard(configWithSecret(undefined));

    expect(() =>
      guard.canActivate(contextWith({ [SIGNATURE_HEADER]: 'whatever' }, body)),
    ).toThrow(UnauthorizedException);
  });
});
