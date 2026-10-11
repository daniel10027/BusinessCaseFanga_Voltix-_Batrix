import { Injectable, Logger } from '@nestjs/common';
import { BatterySwappedPayload } from './dto/battery-swapped-payload.dto';
import { SessionStore } from './session-store.service';
import { SwapCorrelationOutcome } from './swap-correlation.types';

/**
 * Rattache un evenement `battery.swapped` a la session rider ouverte sur le
 * meme cabinet, et met a jour l'affectation batterie <-> rider (brief, 5.8).
 *
 * Idempotence par `event_id` (brief, 5.7) : un meme evenement livre deux
 * fois par le relais outbox (apres un timeout reseau, par exemple) ne doit
 * produire qu'un seul effet.
 */
@Injectable()
export class SwapsService {
  private readonly logger = new Logger(SwapsService.name);
  private readonly processedEventIds = new Set<string>();
  // Affectation courante : numero de serie -> identifiant rider. En
  // memoire pour ce bonus ; une vraie implementation la persisterait.
  private readonly batteryAssignments = new Map<string, string>();

  constructor(private readonly sessions: SessionStore) {}

  openSession(
    riderId: string,
    cabinetId: string,
    assignedBatterySerial: string,
    now: Date = new Date(),
  ) {
    return this.sessions.openSession(riderId, cabinetId, assignedBatterySerial, now);
  }

  /**
   * @returns true si l'evenement est traite pour la premiere fois, false
   * s'il s'agit d'un doublon deja vu (aucun effet dans ce cas).
   */
  handleBatterySwapped(eventId: string, payload: BatterySwappedPayload): boolean {
    if (this.processedEventIds.has(eventId)) {
      this.logger.log(`Evenement ${eventId} deja traite, ignore (idempotence).`);
      return false;
    }
    this.processedEventIds.add(eventId);

    const outcome = this.correlate(payload);
    this.logger.log(`Swap sur le cabinet ${payload.cabinet_id} : ${outcome.kind}`);
    return true;
  }

  correlate(payload: BatterySwappedPayload): SwapCorrelationOutcome {
    const receivedAt = new Date(payload.received_at);
    const session = this.sessions.getLatestForCabinet(payload.cabinet_id);

    if (!session || session.status === 'closed') {
      return { kind: 'orphan' };
    }

    if (session.status === 'expired' || receivedAt > session.expiresAt) {
      this.sessions.markExpired(session);
      return { kind: 'expired', session };
    }

    if (payload.deposited_battery_serial !== session.assignedBatterySerial) {
      return {
        kind: 'wrong_battery',
        session,
        expectedSerial: session.assignedBatterySerial,
        depositedSerial: payload.deposited_battery_serial ?? '',
      };
    }

    if (payload.withdrawn_battery_serial) {
      this.batteryAssignments.set(payload.withdrawn_battery_serial, session.riderId);
    }
    this.sessions.close(session);

    return {
      kind: 'assigned',
      riderId: session.riderId,
      batterySerial: payload.withdrawn_battery_serial ?? '',
      session,
    };
  }

  getAssignedRider(batterySerial: string): string | undefined {
    return this.batteryAssignments.get(batterySerial);
  }
}
