import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, timingSafeEqual } from 'crypto';
import { Request } from 'express';

export const SIGNATURE_HEADER = 'x-fanga-signature';

/**
 * Verifie la signature HMAC-SHA256 du relais outbox de fanga-ingest (brief,
 * 5.7) : meme convention que cote Python, un en-tete `X-Fanga-Signature`
 * portant le HMAC hexadecimal du corps BRUT de la requete.
 *
 * On a besoin du corps brut (pas du JSON re-serialise par Express) car
 * fanga-ingest signe exactement les octets qu'il envoie
 * (`json.dumps(envelope, sort_keys=True)`), qui pourraient differer d'une
 * re-serialisation cote NestJS (ordre des cles, espaces). Voir `main.ts`
 * (`rawBody: true`).
 */
@Injectable()
export class HmacGuard implements CanActivate {
  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request & { rawBody?: Buffer }>();
    const signature = request.headers[SIGNATURE_HEADER];
    const secret = this.config.get<string>('OUTBOX_HMAC_SECRET');

    if (!secret) {
      throw new UnauthorizedException('signature non verifiable : secret non configure');
    }
    if (typeof signature !== 'string' || signature.length === 0) {
      throw new UnauthorizedException('signature manquante');
    }
    if (!request.rawBody) {
      throw new UnauthorizedException('corps brut indisponible pour la verification');
    }

    const expected = createHmac('sha256', secret).update(request.rawBody).digest('hex');
    const expectedBuffer = Buffer.from(expected, 'utf8');
    const signatureBuffer = Buffer.from(signature, 'utf8');

    if (
      expectedBuffer.length !== signatureBuffer.length ||
      !timingSafeEqual(expectedBuffer, signatureBuffer)
    ) {
      throw new UnauthorizedException('signature invalide');
    }

    return true;
  }
}
