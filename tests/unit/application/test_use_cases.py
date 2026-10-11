from datetime import UTC, datetime

from fanga_ingest.application.use_cases import (
    ingest_slot_observed,
    ingest_swap_observed,
    ingest_telemetry_observed,
)
from fanga_ingest.domain.events import BatterySwapped, BatteryUnknownDetected
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    SwapObserved,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)

_KNOWN_SERIALS = frozenset({"BT001977", "BT002290", "BT003105", "BT004817", "BT000555"})


def _slot_observed(**overrides: object) -> SlotObserved:
    defaults: dict[str, object] = dict(
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
    defaults.update(overrides)
    return SlotObserved(**defaults)  # type: ignore[arg-type]


def _telemetry(**overrides: object) -> TelemetryObserved:
    defaults: dict[str, object] = dict(
        source=Source.BATRIX,
        battery_serial="BT004817",
        soc_pct=92.0,
        voltage_v=67.18,
        temperatures_c=(33.1, 34.5, 33.8),
        cycle_count=412,
        status=BatteryStatus.CHARGING,
        errors=(),
        observed_at=_T0,
        received_at=_T0,
    )
    defaults.update(overrides)
    return TelemetryObserved(**defaults)  # type: ignore[arg-type]


def _swap_observed(**overrides: object) -> SwapObserved:
    defaults: dict[str, object] = dict(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        observed_at=_T0,
        received_at=_T0,
    )
    defaults.update(overrides)
    return SwapObserved(**defaults)  # type: ignore[arg-type]


async def test_ingest_slot_observed_creates_cabinet_and_battery() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)

    await ingest_slot_observed(uow, _slot_observed())

    assert "VTX-CAB-0042" in uow.cabinets.store
    battery = uow.batteries.store["BT004817"]
    assert battery.in_inventory is True
    assert battery.soc_pct is not None and battery.soc_pct.value == 96.0
    assert uow.commits == 1


async def test_ingest_slot_observed_deduplicates_identical_frame() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    obs = _slot_observed()

    await ingest_slot_observed(uow, obs)
    await ingest_slot_observed(uow, obs)

    assert uow.commits == 1


async def test_ingest_telemetry_observed_for_unknown_serial_emits_event_once() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    telemetry = _telemetry(battery_serial="BT009999", soc_pct=100.0)

    await ingest_telemetry_observed(uow, telemetry)
    await ingest_telemetry_observed(
        uow, _telemetry(battery_serial="BT009999", soc_pct=100.0, observed_at=_T0)
    )

    battery = uow.batteries.store["BT009999"]
    assert battery.in_inventory is False
    unknown_events = [e for e in uow.outbox.published if isinstance(e, BatteryUnknownDetected)]
    assert len(unknown_events) == 1
    assert unknown_events[0].battery_serial == "BT009999"


async def test_ingest_telemetry_observed_for_known_serial_does_not_emit_unknown_event() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)

    await ingest_telemetry_observed(uow, _telemetry())

    assert not any(isinstance(e, BatteryUnknownDetected) for e in uow.outbox.published)
    assert uow.batteries.store["BT004817"].in_inventory is True


async def test_ingest_swap_observed_updates_both_batteries_and_emits_one_event() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    await ingest_slot_observed(
        uow, _slot_observed(slot_number=7, battery_serial=None, state=SlotState.EMPTY)
    )

    await ingest_swap_observed(uow, _swap_observed())

    swapped_events = [e for e in uow.outbox.published if isinstance(e, BatterySwapped)]
    assert len(swapped_events) == 1

    deposited = uow.batteries.store["BT001977"]
    withdrawn = uow.batteries.store["BT004817"]
    assert deposited.location is not None and deposited.location.value.slot_number == 7
    assert withdrawn.location is not None and withdrawn.location.value.kind == "out_of_cabinet"

    assert uow.cabinets.store["VTX-CAB-0042"].slots[7].battery_serial == "BT001977"
    assert uow.cabinets.store["VTX-CAB-0042"].slots[3].battery_serial is None


async def test_ingest_swap_observed_deduplicates_identical_frame() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    obs = _swap_observed()

    await ingest_swap_observed(uow, obs)
    await ingest_swap_observed(uow, obs)

    assert uow.commits == 1


async def test_ingest_telemetry_observed_deduplicates_identical_message() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    telemetry = _telemetry()

    await ingest_telemetry_observed(uow, telemetry)
    await ingest_telemetry_observed(uow, telemetry)

    assert uow.commits == 1


async def test_ingest_partial_swap_only_touches_the_withdrawal_side() -> None:
    uow = FakeUnitOfWork(known_serials=_KNOWN_SERIALS)
    await ingest_slot_observed(uow, _slot_observed(slot_number=3, battery_serial="BT004817"))

    await ingest_swap_observed(
        uow,
        _swap_observed(deposit_slot=0, deposited_battery_serial=None, withdrawal_slot=3),
    )

    assert "BT001977" not in uow.batteries.store
    withdrawn = uow.batteries.store["BT004817"]
    assert withdrawn.location is not None and withdrawn.location.value.kind == "out_of_cabinet"
