from datetime import UTC, datetime, timedelta

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import BatterySocDiscrepancy
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source
from tests.scenario import CABINET_ID, document_observations, replay

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)


def test_battery_round_trip_preserves_public_state() -> None:
    result = replay(document_observations())
    original = result.batteries["BT004817"]

    restored = Battery.from_state(original.to_state())

    assert restored == original


def test_battery_round_trip_preserves_electrical_ordering_cursor() -> None:
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

    restored = Battery.from_state(battery.to_state())

    # Une lecture cabinet plus ancienne que la télémétrie déjà retenue ne doit
    # pas régresser l'état, même après un rechargement depuis la persistance.
    older_slot_status = SlotObserved(
        source=Source.VOLTIX,
        cabinet_id=CABINET_ID,
        slot_number=3,
        state=SlotState.FULL,
        battery_serial="BT004817",
        soc_pct=50,
        voltage_v=60.0,
        temperature_c=30,
        observed_at=_T0 - timedelta(minutes=10),
        received_at=_T0 - timedelta(minutes=10),
    )
    restored.apply_slot_observed(older_slot_status)

    assert restored.soc_pct is not None
    assert restored.soc_pct.value == 91.8
    assert restored.soc_pct.source == Source.BATRIX


def test_battery_round_trip_preserves_discrepancy_dedup_guard() -> None:
    battery = Battery(serial="BT004817")
    cabinet_reading = SlotObserved(
        source=Source.VOLTIX,
        cabinet_id=CABINET_ID,
        slot_number=3,
        state=SlotState.FULL,
        battery_serial="BT004817",
        soc_pct=96,
        voltage_v=67.2,
        temperature_c=34,
        observed_at=_T0,
        received_at=_T0,
    )
    bms_reading = TelemetryObserved(
        source=Source.BATRIX,
        battery_serial="BT004817",
        soc_pct=80.0,
        voltage_v=66.0,
        temperatures_c=(30.0,),
        cycle_count=10,
        status=BatteryStatus.DISCHARGING,
        errors=(),
        observed_at=_T0 + timedelta(seconds=1),
        received_at=_T0 + timedelta(seconds=1),
    )
    battery.apply_slot_observed(cabinet_reading)
    first_events = battery.apply_telemetry_observed(bms_reading)
    assert any(isinstance(e, BatterySocDiscrepancy) for e in first_events)

    restored = Battery.from_state(battery.to_state())
    second_events = restored.apply_telemetry_observed(bms_reading)

    assert not any(isinstance(e, BatterySocDiscrepancy) for e in second_events)


def test_cabinet_round_trip_preserves_all_slots() -> None:
    result = replay(document_observations())
    original = result.cabinets[CABINET_ID]

    restored = Cabinet.from_state(original.to_state())

    assert restored == original
