import { SessionStore } from '../src/swaps/session-store.service';

describe('SessionStore', () => {
  it('opens a session with a 5 minute window', () => {
    const store = new SessionStore();
    const now = new Date('2026-10-01T08:00:00Z');

    const session = store.openSession('rider-1', 'VTX-CAB-0042', 'BT001977', now);

    expect(session.status).toBe('open');
    expect(session.expiresAt.getTime() - session.openedAt.getTime()).toBe(5 * 60 * 1000);
  });

  it('rejects opening a second session on a cabinet that already has one open', () => {
    const store = new SessionStore();
    const now = new Date('2026-10-01T08:00:00Z');
    store.openSession('rider-1', 'VTX-CAB-0042', 'BT001977', now);

    expect(() => store.openSession('rider-2', 'VTX-CAB-0042', 'BT003105', now)).toThrow();
  });

  it('allows opening a new session once the previous one is closed', () => {
    const store = new SessionStore();
    const now = new Date('2026-10-01T08:00:00Z');
    const first = store.openSession('rider-1', 'VTX-CAB-0042', 'BT001977', now);
    store.close(first);

    expect(() =>
      store.openSession('rider-2', 'VTX-CAB-0042', 'BT003105', now),
    ).not.toThrow();
  });

  it('allows opening a new session once the previous one has expired', () => {
    const store = new SessionStore();
    const opened = new Date('2026-10-01T08:00:00Z');
    store.openSession('rider-1', 'VTX-CAB-0042', 'BT001977', opened);

    const sixMinutesLater = new Date(opened.getTime() + 6 * 60 * 1000);
    expect(() =>
      store.openSession('rider-2', 'VTX-CAB-0042', 'BT003105', sixMinutesLater),
    ).not.toThrow();
  });

  it('returns undefined for a cabinet that never had a session', () => {
    const store = new SessionStore();
    expect(store.getLatestForCabinet('VTX-CAB-0042')).toBeUndefined();
  });
});
