from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.postgres import (
    PostgresBatteryRepository,
    PostgresCabinetRepository,
    PostgresInventoryRegistry,
    PostgresObservationStore,
    PostgresOutboxWriter,
)
from fanga_ingest.adapters.persistence.tables import inventory as inventory_table
from fanga_ingest.adapters.persistence.tables import outbox
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import BatteryFaulted, new_event_id
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)


async def test_battery_save_then_get_round_trips_through_jsonb(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    battery = Battery(serial="BT004817")
    battery.apply_telemetry_observed(
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT004817",
            soc_pct=91.8,
            voltage_v=66.95,
            temperatures_c=(33.6, 34.9, 34.1),
            cycle_count=412,
            status=BatteryStatus.DISCHARGING,
            errors=(),
            observed_at=_T0,
            received_at=_T0,
        )
    )

    async with session_factory() as session:
        repo = PostgresBatteryRepository(session)
        await repo.save(battery)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresBatteryRepository(session)
        reloaded = await repo.get("BT004817")

    assert reloaded == battery
    assert reloaded is not None
    assert reloaded.soc_pct is not None
    assert reloaded.soc_pct.value == 91.8


async def test_battery_save_upserts_an_existing_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = PostgresBatteryRepository(session)
        await repo.save(Battery(serial="BT004817", in_inventory=True))
        await session.commit()

    async with session_factory() as session:
        repo = PostgresBatteryRepository(session)
        battery = await repo.get("BT004817")
        assert battery is not None
        battery.apply_slot_observed(
            SlotObserved(
                source=Source.VOLTIX,
                cabinet_id="VTX-CAB-0042",
                slot_number=3,
                state=SlotState.FULL,
                battery_serial="BT004817",
                soc_pct=96,
                voltage_v=67.2,
                temperature_c=34,
                observed_at=_T0,
                received_at=_T0,
            )
        )
        await repo.save(battery)
        await session.commit()

    async with session_factory() as session:
        reloaded = await PostgresBatteryRepository(session).get("BT004817")

    assert reloaded is not None
    assert reloaded.soc_pct is not None and reloaded.soc_pct.value == 96


async def test_cabinet_save_then_get_round_trips(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet.apply_slot_observed(
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id="VTX-CAB-0042",
            slot_number=1,
            state=SlotState.CHARGING,
            battery_serial="BT003105",
            soc_pct=58,
            voltage_v=64.1,
            temperature_c=41,
            observed_at=_T0,
            received_at=_T0,
        )
    )

    async with session_factory() as session:
        repo = PostgresCabinetRepository(session)
        await repo.save(cabinet)
        await session.commit()

    async with session_factory() as session:
        reloaded = await PostgresCabinetRepository(session).get("VTX-CAB-0042")

    assert reloaded == cabinet
    assert reloaded is not None
    assert reloaded.slots[1].battery_serial == "BT003105"
    assert reloaded.slots[2].state is None  # jamais signalé


async def test_observation_store_deduplicates_identical_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    telemetry = TelemetryObserved(
        source=Source.BATRIX,
        battery_serial="BT004817",
        soc_pct=91.8,
        voltage_v=66.95,
        temperatures_c=(33.6,),
        cycle_count=412,
        status=BatteryStatus.DISCHARGING,
        errors=(),
        observed_at=_T0,
        received_at=_T0,
    )

    async with session_factory() as session:
        store = PostgresObservationStore(session)
        first = await store.record_telemetry_observed(telemetry)
        second = await store.record_telemetry_observed(telemetry)
        await session.commit()

    assert first is True
    assert second is False


async def test_outbox_writer_inserts_a_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = BatteryFaulted(event_id=new_event_id(), occurred_at=_T0, battery_serial="BT002290")

    async with session_factory() as session:
        await PostgresOutboxWriter(session).publish(event)
        await session.commit()

    async with session_factory() as session:
        row = (
            await session.execute(
                select(outbox.c.type, outbox.c.payload).where(outbox.c.event_id == event.event_id)
            )
        ).first()

    assert row is not None
    assert row[0] == "battery.faulted"
    assert row[1]["battery_serial"] == "BT002290"


async def test_known_inventory_reflects_registered_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await session.execute(
            insert(inventory_table).values(serial="BT004817", status="registered", updated_at=_T0)
        )
        await session.commit()

    async with session_factory() as session:
        known = PostgresInventoryRegistry(session)
        assert await known.contains("BT004817") is True
        assert await known.contains("BT009999") is False


async def test_inventory_registry_set_status_upserts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        registry = PostgresInventoryRegistry(session)
        await registry.set_status("BT009999", "registered")
        await session.commit()

    async with session_factory() as session:
        assert await PostgresInventoryRegistry(session).contains("BT009999") is True

    async with session_factory() as session:
        registry = PostgresInventoryRegistry(session)
        await registry.set_status("BT009999", "retired")
        await session.commit()

    async with session_factory() as session:
        assert await PostgresInventoryRegistry(session).contains("BT009999") is False
