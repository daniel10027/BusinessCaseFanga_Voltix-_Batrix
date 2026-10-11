"""Rejeu complet du business case contre une vraie base PostgreSQL.

Vérifie que le passage par la persistance réelle (sérialisation JSONB,
déduplication par contrainte unique) donne le même résultat que le rejeu pur
domaine (`tests/scenario.py`), et que rejouer deux fois ne change rien :
aucune nouvelle ligne d'observation, aucun nouvel événement.
"""

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.postgres import (
    PostgresBatteryRepository,
    PostgresCabinetRepository,
    PostgresUnitOfWork,
)
from fanga_ingest.adapters.persistence.tables import inventory as inventory_table
from fanga_ingest.adapters.persistence.tables import observations, outbox
from fanga_ingest.application.use_cases import (
    ingest_slot_observed,
    ingest_swap_observed,
    ingest_telemetry_observed,
)
from fanga_ingest.domain.battery import LocationKind
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved
from tests.scenario import CABINET_ID, KNOWN_BATTERY_SERIALS, document_observations

_KNOWN_SERIALS = KNOWN_BATTERY_SERIALS


async def _ingest_all(session_factory: async_sessionmaker[AsyncSession]) -> None:
    for obs in document_observations():
        uow = PostgresUnitOfWork(session_factory)
        if isinstance(obs, SlotObserved):
            await ingest_slot_observed(uow, obs)
        elif isinstance(obs, SwapObserved):
            await ingest_swap_observed(uow, obs)
        elif isinstance(obs, TelemetryObserved):
            await ingest_telemetry_observed(uow, obs)


async def test_full_document_replay_matches_expected_state_and_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_inventory(session_factory)

    await _ingest_all(session_factory)

    async with session_factory() as session:
        observation_count = (
            await session.execute(select(func.count()).select_from(observations))
        ).scalar_one()
        event_count = (await session.execute(select(func.count()).select_from(outbox))).scalar_one()

    assert (
        observation_count == 10
    )  # 5 Voltix (4 SLOT_STATUS + 1 SWAP) + 5 Batrix (6 messages, 1 doublon)
    assert event_count == 3  # battery.swapped, battery.faulted, battery.unknown_detected

    await _assert_expected_state(session_factory)

    # Rejouer l'intégralité du scénario une seconde fois ne doit rien changer.
    await _ingest_all(session_factory)

    async with session_factory() as session:
        observation_count_again = (
            await session.execute(select(func.count()).select_from(observations))
        ).scalar_one()
        event_count_again = (
            await session.execute(select(func.count()).select_from(outbox))
        ).scalar_one()

    assert observation_count_again == observation_count
    assert event_count_again == event_count
    await _assert_expected_state(session_factory)


async def _seed_inventory(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        for serial in _KNOWN_SERIALS:
            await session.execute(
                insert(inventory_table).values(
                    serial=serial, status="registered", updated_at=func.now()
                )
            )
        await session.commit()


async def _assert_expected_state(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        battery_repo = PostgresBatteryRepository(session)
        cabinet_repo = PostgresCabinetRepository(session)

        bt004817 = await battery_repo.get("BT004817")
        assert bt004817 is not None
        assert bt004817.location is not None
        assert bt004817.location.value.kind == LocationKind.OUT_OF_CABINET
        assert bt004817.soc_pct is not None
        assert bt004817.soc_pct.value == 91.8

        bt009999 = await battery_repo.get("BT009999")
        assert bt009999 is not None
        assert bt009999.in_inventory is False

        cabinet = await cabinet_repo.get(CABINET_ID)
        assert cabinet is not None
        assert cabinet.slots[7].battery_serial == "BT001977"
        assert cabinet.slots[3].battery_serial is None
