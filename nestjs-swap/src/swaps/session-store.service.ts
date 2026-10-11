import { Injectable } from '@nestjs/common';
import { randomUUID } from 'crypto';
import { RiderSession } from './session.types';

const SESSION_DURATION_MS = 5 * 60 * 1000;

/**
 * Stockage en memoire des sessions rider, une par cabinet au plus (brief,
 * 5.8). On garde la derniere session connue d'un cabinet meme apres sa
 * fermeture ou son expiration : c'est ce qui permet a `SwapsService` de
 * distinguer un swap orphelin (aucune session n'a jamais existe) d'un swap
 * trop tardif (une session a existe, mais a expire avant le swap).
 */
@Injectable()
export class SessionStore {
  private readonly sessionsByCabinet = new Map<string, RiderSession>();

  openSession(
    riderId: string,
    cabinetId: string,
    assignedBatterySerial: string,
    now: Date = new Date(),
  ): RiderSession {
    const existing = this.sessionsByCabinet.get(cabinetId);
    if (existing && existing.status === 'open' && now <= existing.expiresAt) {
      throw new Error(`Une session rider est deja ouverte sur le cabinet ${cabinetId}.`);
    }

    const session: RiderSession = {
      id: randomUUID(),
      riderId,
      cabinetId,
      assignedBatterySerial,
      openedAt: now,
      expiresAt: new Date(now.getTime() + SESSION_DURATION_MS),
      status: 'open',
    };
    this.sessionsByCabinet.set(cabinetId, session);
    return session;
  }

  /** La session la plus recente connue pour ce cabinet, quel que soit son etat. */
  getLatestForCabinet(cabinetId: string): RiderSession | undefined {
    return this.sessionsByCabinet.get(cabinetId);
  }

  markExpired(session: RiderSession): void {
    session.status = 'expired';
  }

  close(session: RiderSession): void {
    session.status = 'closed';
  }
}
