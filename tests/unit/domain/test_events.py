from datetime import UTC, datetime
from uuid import UUID

from fanga_ingest.domain.events import BatterySwapped, new_event_id

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)


def test_new_event_id_returns_a_unique_uuid() -> None:
    assert isinstance(new_event_id(), UUID)
    assert new_event_id() != new_event_id()


def test_battery_swapped_carries_received_at_separately_from_occurred_at() -> None:
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

    assert event.cabinet_id == "VTX-CAB-0042"
    assert event.received_at == _T0
