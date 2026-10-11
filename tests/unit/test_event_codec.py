from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from fanga_ingest.adapters.event_codec import event_envelope, event_payload, event_type
from fanga_ingest.domain.events import (
    BatteryFaulted,
    BatterySocDiscrepancy,
    BatterySwapped,
    BatteryUnknownDetected,
    DomainEvent,
    new_event_id,
)

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)


def test_battery_swapped_payload_and_type() -> None:
    event = BatterySwapped(
        event_id=new_event_id(),
        occurred_at=_T0,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        received_at=_T0,
    )

    assert event_type(event) == "battery.swapped"
    payload = event_payload(event)
    assert payload["cabinet_id"] == "VTX-CAB-0042"
    assert payload["received_at"] == _T0.isoformat()


def test_battery_faulted_payload_and_type() -> None:
    event = BatteryFaulted(event_id=new_event_id(), occurred_at=_T0, battery_serial="BT002290")

    assert event_type(event) == "battery.faulted"
    assert event_payload(event) == {"battery_serial": "BT002290"}


def test_battery_unknown_detected_payload_and_type() -> None:
    event = BatteryUnknownDetected(
        event_id=new_event_id(), occurred_at=_T0, battery_serial="BT009999"
    )

    assert event_type(event) == "battery.unknown_detected"
    assert event_payload(event) == {"battery_serial": "BT009999"}


def test_battery_soc_discrepancy_payload_and_type() -> None:
    event = BatterySocDiscrepancy(
        event_id=new_event_id(),
        occurred_at=_T0,
        battery_serial="BT004817",
        cabinet_soc_pct=96,
        bms_soc_pct=80.0,
    )

    assert event_type(event) == "battery.soc_discrepancy"
    assert event_payload(event) == {
        "battery_serial": "BT004817",
        "cabinet_soc_pct": 96,
        "bms_soc_pct": 80.0,
    }


def test_event_envelope_matches_the_outbox_wire_format() -> None:
    event = BatteryFaulted(event_id=new_event_id(), occurred_at=_T0, battery_serial="BT002290")

    envelope = event_envelope(event)

    assert envelope == {
        "event_id": str(event.event_id),
        "type": "battery.faulted",
        "version": 1,
        "occurred_at": _T0.isoformat(),
        "payload": {"battery_serial": "BT002290"},
    }


def test_unhandled_event_type_raises() -> None:
    @dataclass(frozen=True)
    class SomeOtherEvent(DomainEvent):
        pass

    with pytest.raises(TypeError):
        event_payload(SomeOtherEvent(event_id=new_event_id(), occurred_at=_T0))
