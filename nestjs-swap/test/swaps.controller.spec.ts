import { INestApplication } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { createHmac } from 'crypto';
import request from 'supertest';
import { SIGNATURE_HEADER } from '../src/swaps/hmac.guard';
import { SwapsModule } from '../src/swaps/swaps.module';
import { SwapsService } from '../src/swaps/swaps.service';

const SECRET = 'controller-test-secret';
const CABINET_ID = 'VTX-CAB-0042';

describe('SwapsController (integration)', () => {
  let app: INestApplication;
  let swapsService: SwapsService;

  beforeAll(async () => {
    process.env.OUTBOX_HMAC_SECRET = SECRET;

    const moduleRef: TestingModule = await Test.createTestingModule({
      imports: [ConfigModule.forRoot({ isGlobal: true, ignoreEnvFile: true }), SwapsModule],
    }).compile();

    // rawBody: true — necessaire a HmacGuard, voir src/main.ts.
    app = moduleRef.createNestApplication({ rawBody: true });
    await app.init();
    swapsService = moduleRef.get(SwapsService);
  });

  afterAll(async () => {
    await app.close();
  });

  function sign(body: unknown): { raw: string; signature: string } {
    const raw = JSON.stringify(body);
    const signature = createHmac('sha256', SECRET).update(raw).digest('hex');
    return { raw, signature };
  }

  it('accepts a correctly signed battery.swapped event and assigns the rider', async () => {
    swapsService.openSession('rider-1', CABINET_ID, 'BT001977', new Date('2026-10-01T07:59:00Z'));

    const event = {
      event_id: 'event-1',
      type: 'battery.swapped',
      version: 1,
      occurred_at: '2026-10-01T08:00:01Z',
      payload: {
        cabinet_id: CABINET_ID,
        deposit_slot: 7,
        withdrawal_slot: 3,
        deposited_battery_serial: 'BT001977',
        withdrawn_battery_serial: 'BT004817',
        received_at: '2026-10-01T08:00:01Z',
      },
    };
    const { raw, signature } = sign(event);

    await request(app.getHttpServer())
      .post('/webhooks/fanga')
      .set('Content-Type', 'application/json')
      .set(SIGNATURE_HEADER, signature)
      .send(raw)
      .expect(204);

    expect(swapsService.getAssignedRider('BT004817')).toBe('rider-1');
  });

  it('is idempotent when the same event is delivered twice', async () => {
    swapsService.openSession('rider-2', 'VTX-CAB-0099', 'BT111111', new Date('2026-10-01T07:59:00Z'));
    const event = {
      event_id: 'event-repeat',
      type: 'battery.swapped',
      version: 1,
      occurred_at: '2026-10-01T08:00:01Z',
      payload: {
        cabinet_id: 'VTX-CAB-0099',
        deposit_slot: 1,
        withdrawal_slot: 2,
        deposited_battery_serial: 'BT111111',
        withdrawn_battery_serial: 'BT222222',
        received_at: '2026-10-01T08:00:01Z',
      },
    };
    const { raw, signature } = sign(event);

    for (let i = 0; i < 2; i += 1) {
      await request(app.getHttpServer())
        .post('/webhooks/fanga')
        .set('Content-Type', 'application/json')
        .set(SIGNATURE_HEADER, signature)
        .send(raw)
        .expect(204);
    }

    expect(swapsService.getAssignedRider('BT222222')).toBe('rider-2');
  });

  it('rejects an event with an invalid signature', async () => {
    const event = {
      event_id: 'event-bad-signature',
      type: 'battery.swapped',
      version: 1,
      occurred_at: '2026-10-01T08:00:01Z',
      payload: {},
    };

    await request(app.getHttpServer())
      .post('/webhooks/fanga')
      .set('Content-Type', 'application/json')
      .set(SIGNATURE_HEADER, 'not-the-right-signature')
      .send(JSON.stringify(event))
      .expect(401);
  });

  it('accepts (but ignores) an event type this module does not act on', async () => {
    const event = {
      event_id: 'event-faulted',
      type: 'battery.faulted',
      version: 1,
      occurred_at: '2026-10-01T08:00:01Z',
      payload: { battery_serial: 'BT002290' },
    };
    const { raw, signature } = sign(event);

    await request(app.getHttpServer())
      .post('/webhooks/fanga')
      .set('Content-Type', 'application/json')
      .set(SIGNATURE_HEADER, signature)
      .send(raw)
      .expect(204);
  });
});
