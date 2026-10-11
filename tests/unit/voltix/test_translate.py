from datetime import UTC, datetime, timedelta

from fanga_ingest.adapters.vendors.voltix.messages import SlotState as WireSlotState
from fanga_ingest.adapters.vendors.voltix.messages import SlotStatusMessage, SwapEventMessage
from fanga_ingest.adapters.vendors.voltix.translate import (
    translate_slot_status,
    translate_swap_event,
)
from fanga_ingest.domain.observations import SlotState as DomainSlotState
from fanga_ingest.domain.value_objects import Source

_RECEIVED_AT = datetime(2026, 10, 1, 7, 59, 50, tzinfo=UTC)


def test_translate_slot_status_dates_at_received_at_and_maps_fields() -> None:
    message = SlotStatusMessage(
        slot_number=3,
        state=WireSlotState.FULL,
        battery_serial="BT004817",
        soc_pct=96,
        voltage_v=67.2,
        temperature_c=34,
    )

    obs = translate_slot_status("VTX-CAB-0042", message, _RECEIVED_AT)

    assert obs.source == Source.VOLTIX
    assert obs.cabinet_id == "VTX-CAB-0042"
    assert obs.slot_number == 3
    assert obs.state == DomainSlotState.FULL
    assert obs.battery_serial == "BT004817"
    assert obs.soc_pct == 96
    assert obs.voltage_v == 67.2
    assert obs.temperature_c == 34
    assert obs.observed_at == _RECEIVED_AT
    assert obs.received_at == _RECEIVED_AT


def test_translate_swap_event_keeps_cabinet_clock_when_close_to_server_time() -> None:
    message = SwapEventMessage(
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        cabinet_clock_epoch_s=1790841600,  # 2026-10-01T08:00:00Z
    )
    received_at = datetime(2026, 10, 1, 8, 0, 1, tzinfo=UTC)

    obs = translate_swap_event("VTX-CAB-0042", message, received_at)

    assert obs.observed_at == datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
    assert obs.received_at == received_at
    assert obs.deposited_battery_serial == "BT001977"
    assert obs.withdrawn_battery_serial == "BT004817"


def test_translate_swap_event_falls_back_to_server_time_on_clock_drift() -> None:
    message = SwapEventMessage(
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        cabinet_clock_epoch_s=1790841600,
    )
    received_at = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC) + timedelta(minutes=10)

    obs = translate_swap_event("VTX-CAB-0042", message, received_at)

    assert obs.observed_at == received_at
