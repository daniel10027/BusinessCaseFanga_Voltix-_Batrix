/**
 * Charge utile de l'evenement `battery.swapped` (brief, section 5.7 et 5.8).
 * `received_at` est l'heure de reception serveur du swap cote fanga-ingest —
 * c'est elle qu'on utilise pour la correlation avec la session rider,
 * jamais l'horloge du cabinet.
 */
export interface BatterySwappedPayload {
  cabinet_id: string;
  deposit_slot: number;
  withdrawal_slot: number;
  deposited_battery_serial: string | null;
  withdrawn_battery_serial: string | null;
  received_at: string;
}
