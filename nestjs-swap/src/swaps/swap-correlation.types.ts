import { RiderSession } from './session.types';

/**
 * Resultat de la correlation d'un swap avec une session rider (brief, 5.8).
 * Les trois anomalies nommees par le brief : `orphan` (aucune session),
 * `expired` (session connue mais fenetre depassee), `wrong_battery`
 * (mauvaise batterie deposee).
 */
export type SwapCorrelationOutcome =
  | { kind: 'assigned'; riderId: string; batterySerial: string; session: RiderSession }
  | { kind: 'orphan' }
  | { kind: 'expired'; session: RiderSession }
  | {
      kind: 'wrong_battery';
      session: RiderSession;
      expectedSerial: string;
      depositedSerial: string;
    };
