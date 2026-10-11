export type SessionStatus = 'open' | 'closed' | 'expired';

/**
 * Session de swap ouverte par l'application mobile du rider (brief, 5.8).
 * Stockage en memoire : une vraie implementation la persisterait (Redis ou
 * table SQL) pour survivre a un redemarrage — hors perimetre de ce bonus.
 */
export interface RiderSession {
  id: string;
  riderId: string;
  cabinetId: string;
  assignedBatterySerial: string;
  openedAt: Date;
  expiresAt: Date;
  status: SessionStatus;
}
