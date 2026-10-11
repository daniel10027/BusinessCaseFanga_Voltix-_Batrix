"""Supervision des cabinets contre une vraie base (brief, 7.12) :
cabinet silencieux > 180 s ⇒ `cabinet.offline` une seule fois ; trame
suivante ⇒ `cabinet.online`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.postgres import PostgresCabinetRepository, PostgresUnitOfWork
from fanga_ingest.adapters.persistence.tables import outbox
from fanga_ingest.adapters.supervision import OfflineCabinetSupervisor
from fanga_ingest.application.use_cases import ingest_slot_observed
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.observations import SlotObserved, SlotState
from fanga_ingest.domain.value_objects import Source

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
_OFFLINE_AFTER = timedelta(seconds=180)


async def _event_count(session_factory: async_sessionmaker[AsyncSession], event_type: str) -> int:
    async with session_factory() as session:
        rows = (
            await session.execute(select(outbox.c.event_id).where(outbox.c.type == event_type))
        ).all()
    return len(rows)


async def test_silent_cabinet_goes_offline_then_back_online_on_next_frame(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await PostgresCabinetRepository(session).save(
            Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=_T0, online=True)
        )
        await session.commit()

    now = _T0 + _OFFLINE_AFTER + timedelta(seconds=1)
    supervisor = OfflineCabinetSupervisor(
        uow_factory=lambda: PostgresUnitOfWork(session_factory),
        now=lambda: now,
        offline_after=_OFFLINE_AFTER,
        sweep_interval_seconds=30,
    )

    await supervisor.sweep_once()
    await supervisor.sweep_once()  # un deuxième passage ne doit pas doubler l'événement

    assert await _event_count(session_factory, "cabinet.offline") == 1

    await ingest_slot_observed(
        PostgresUnitOfWork(session_factory),
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id="VTX-CAB-0042",
            slot_number=1,
            state=SlotState.CHARGING,
            battery_serial="BT003105",
            soc_pct=58,
            voltage_v=64.1,
            temperature_c=41,
            observed_at=now + timedelta(minutes=1),
            received_at=now + timedelta(minutes=1),
        ),
    )

    async with session_factory() as session:
        reloaded = await PostgresCabinetRepository(session).get("VTX-CAB-0042")

    assert reloaded is not None
    assert reloaded.online is True
    assert await _event_count(session_factory, "cabinet.online") == 1
