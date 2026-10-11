from datetime import UTC, datetime

from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    SwapObserved,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)


def test_slot_observed_dedup_key_depends_on_received_at() -> None:
    a = SlotObserved(
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
    b = SlotObserved(
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
    assert a.dedup_key == b.dedup_key

    c = SlotObserved(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        slot_number=3,
        state=SlotState.FULL,
        battery_serial="BT004817",
        soc_pct=96,
        voltage_v=67.2,
        temperature_c=34,
        observed_at=_T0,
        received_at=_T0.replace(second=50),
    )
    assert a.dedup_key != c.dedup_key


def test_swap_observed_dedup_key_depends_on_series_and_observed_at() -> None:
    swap = SwapObserved(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        observed_at=_T0,
        received_at=_T0,
    )
    duplicate = SwapObserved(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        observed_at=_T0,
        # Reçu un peu plus tard (rejoué après une coupure 4G), même dedup_key :
        # c'est bien l'événement rapporté, pas l'instant de réception, qui identifie le swap.
        received_at=_T0.replace(minute=5),
    )
    assert swap.dedup_key == duplicate.dedup_key


def test_telemetry_observed_dedup_key_depends_on_serial_and_observed_at() -> None:
    first = TelemetryObserved(
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
    duplicate_republished = TelemetryObserved(
        source=Source.BATRIX,
        battery_serial="BT004817",
        soc_pct=91.8,
        voltage_v=66.95,
        temperatures_c=(33.6, 34.9, 34.1),
        cycle_count=412,
        status=BatteryStatus.DISCHARGING,
        errors=(),
        observed_at=_T0,
        received_at=_T0.replace(second=5),
    )
    assert first.dedup_key == duplicate_republished.dedup_key
