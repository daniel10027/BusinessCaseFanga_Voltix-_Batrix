"""Relais outbox contre une vraie base, avec un faux NestJS (`httpx.MockTransport`)."""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.outbox_relay import (
    SIGNATURE_HEADER,
    OutboxRelay,
    sign_payload,
)
from fanga_ingest.adapters.persistence.postgres import PostgresOutboxWriter
from fanga_ingest.adapters.persistence.tables import outbox
from fanga_ingest.domain.events import (
    BatteryFaulted,
    BatterySwapped,
    BatteryUnknownDetected,
    new_event_id,
)

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
_SECRET = "test-secret"
_WEBHOOK_URL = "http://nestjs.internal/webhooks/fanga"


async def _seed_three_events(session_factory: async_sessionmaker[AsyncSession]) -> None:
    # Horodatages distincts et croissants : l'ordre de traitement par le
    # relais (ORDER BY occurred_at) doit être déterministe pour ces tests.
    events = [
        BatterySwapped(
            event_id=new_event_id(),
            occurred_at=_T0,
            cabinet_id="VTX-CAB-0042",
            deposit_slot=7,
            withdrawal_slot=3,
            deposited_battery_serial="BT001977",
            withdrawn_battery_serial="BT004817",
            received_at=_T0,
        ),
        BatteryFaulted(
            event_id=new_event_id(),
            occurred_at=_T0 + timedelta(seconds=1),
            battery_serial="BT002290",
        ),
        BatteryUnknownDetected(
            event_id=new_event_id(),
            occurred_at=_T0 + timedelta(seconds=2),
            battery_serial="BT009999",
        ),
    ]
    async with session_factory() as session:
        writer = PostgresOutboxWriter(session)
        for event in events:
            await writer.publish(event)
        await session.commit()


async def test_relay_publishes_all_events_once_with_a_valid_signature(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_three_events(session_factory)
    received_signatures: list[str] = []
    received_bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_signatures.append(request.headers[SIGNATURE_HEADER])
        received_bodies.append(request.content)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        relay = OutboxRelay(session_factory, client, _WEBHOOK_URL, _SECRET)

        published_first_round = await relay.relay_once()
        published_second_round = await relay.relay_once()

    assert published_first_round == 3
    assert published_second_round == 0  # tout est déjà publié
    assert len(received_bodies) == 3
    for signature, body in zip(received_signatures, received_bodies, strict=True):
        assert signature == sign_payload(_SECRET, body)

    async with session_factory() as session:
        rows = (await session.execute(select(outbox.c.published_at))).scalars().all()
    assert all(row is not None for row in rows)


async def test_relay_stops_when_the_webhook_is_unreachable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_three_events(session_factory)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unreachable)) as client:
        relay = OutboxRelay(session_factory, client, _WEBHOOK_URL, _SECRET)
        published = await relay.relay_once()

    assert published == 0


async def test_relay_stops_on_first_failure_and_retries_next_round(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_three_events(session_factory)
    call_count = 0

    def failing_then_ok(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_then_ok)) as client:
        relay = OutboxRelay(session_factory, client, _WEBHOOK_URL, _SECRET)

        published_first_round = await relay.relay_once()
        async with session_factory() as session:
            attempts = (
                await session.execute(
                    select(outbox.c.attempts).order_by(outbox.c.occurred_at).limit(1)
                )
            ).scalar_one()
        assert published_first_round == 0
        assert attempts == 1  # rien perdu : la ligne en échec garde sa trace

        published_second_round = await relay.relay_once()

    assert published_second_round == 3

    async with session_factory() as session:
        rows = (await session.execute(select(outbox.c.published_at))).scalars().all()
    assert all(row is not None for row in rows)
