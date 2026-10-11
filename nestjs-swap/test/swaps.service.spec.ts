import { BatterySwappedPayload } from '../src/swaps/dto/battery-swapped-payload.dto';
import { SessionStore } from '../src/swaps/session-store.service';
import { SwapsService } from '../src/swaps/swaps.service';

const CABINET_ID = 'VTX-CAB-0042';

function swapPayload(overrides: Partial<BatterySwappedPayload> = {}): BatterySwappedPayload {
  return {
    cabinet_id: CABINET_ID,
    deposit_slot: 7,
    withdrawal_slot: 3,
    deposited_battery_serial: 'BT001977',
    withdrawn_battery_serial: 'BT004817',
    received_at: '2026-10-01T08:00:01Z',
    ...overrides,
  };
}

describe('SwapsService', () => {
  it('assigns the withdrawn battery to the rider on the nominal case', () => {
    const service = new SwapsService(new SessionStore());
    service.openSession('rider-1', CABINET_ID, 'BT001977', new Date('2026-10-01T07:59:00Z'));

    const outcome = service.correlate(swapPayload());

    expect(outcome.kind).toBe('assigned');
    if (outcome.kind === 'assigned') {
      expect(outcome.riderId).toBe('rider-1');
      expect(outcome.batterySerial).toBe('BT004817');
    }
    expect(service.getAssignedRider('BT004817')).toBe('rider-1');
  });

  it('reports an orphan swap when no session was ever opened on the cabinet', () => {
    const service = new SwapsService(new SessionStore());

    const outcome = service.correlate(swapPayload());

    expect(outcome.kind).toBe('orphan');
  });

  it('reports an expired session when the swap arrives after the 5 minute window', () => {
    const service = new SwapsService(new SessionStore());
    service.openSession('rider-1', CABINET_ID, 'BT001977', new Date('2026-10-01T07:50:00Z'));

    const outcome = service.correlate(
      swapPayload({ received_at: '2026-10-01T08:00:01Z' }), // 10 min later
    );

    expect(outcome.kind).toBe('expired');
  });

  it('reports a wrong-battery anomaly when the deposited serial does not match', () => {
    const service = new SwapsService(new SessionStore());
    service.openSession('rider-1', CABINET_ID, 'BT001977', new Date('2026-10-01T07:59:00Z'));

    const outcome = service.correlate(swapPayload({ deposited_battery_serial: 'BT999999' }));

    expect(outcome.kind).toBe('wrong_battery');
    if (outcome.kind === 'wrong_battery') {
      expect(outcome.expectedSerial).toBe('BT001977');
      expect(outcome.depositedSerial).toBe('BT999999');
    }
    // La session reste ouverte : on n'a pas assigne la mauvaise batterie.
    expect(service.getAssignedRider('BT004817')).toBeUndefined();
  });

  it('is idempotent: processing the same event_id twice has no extra effect', () => {
    const service = new SwapsService(new SessionStore());
    service.openSession('rider-1', CABINET_ID, 'BT001977', new Date('2026-10-01T07:59:00Z'));

    const firstCall = service.handleBatterySwapped('event-1', swapPayload());
    const secondCall = service.handleBatterySwapped('event-1', swapPayload());

    expect(firstCall).toBe(true);
    expect(secondCall).toBe(false);
    expect(service.getAssignedRider('BT004817')).toBe('rider-1');
  });
});
