from datetime import UTC, datetime, timedelta

from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import BatterySwapped, CabinetOffline, CabinetOnline
from fanga_ingest.domain.observations import SlotObserved, SlotState, SwapObserved
from fanga_ingest.domain.value_objects import Source

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)


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


def _swap_observed(**overrides: object) -> SwapObserved:
    defaults: dict[str, object] = dict(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        observed_at=_T0 + timedelta(minutes=1),
        received_at=_T0 + timedelta(minutes=1),
    )
    defaults.update(overrides)
    return SwapObserved(**defaults)  # type: ignore[arg-type]


def test_slot_never_reported_stays_unknown() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    assert cabinet.slots[2].state is None
    assert cabinet.slots[2].battery_serial is None


def test_slot_observed_updates_the_matching_slot_only() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    cabinet.apply_slot_observed(_slot_observed(slot_number=3, state=SlotState.FULL))

    assert cabinet.slots[3].state == SlotState.FULL
    assert cabinet.slots[3].battery_serial == "BT004817"
    assert cabinet.slots[4].state is None


def test_latest_observation_wins_regardless_of_arrival_order() -> None:
    cabinet_a = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet_a.apply_slot_observed(_slot_observed(state=SlotState.FULL, observed_at=_T0))
    cabinet_a.apply_slot_observed(
        _slot_observed(state=SlotState.EMPTY, observed_at=_T0 + timedelta(minutes=1))
    )

    cabinet_b = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet_b.apply_slot_observed(
        _slot_observed(state=SlotState.EMPTY, observed_at=_T0 + timedelta(minutes=1))
    )
    cabinet_b.apply_slot_observed(_slot_observed(state=SlotState.FULL, observed_at=_T0))

    assert cabinet_a.slots[3].state == SlotState.EMPTY
    assert cabinet_b.slots[3].state == SlotState.EMPTY


def test_swap_sets_deposit_slot_occupied_and_withdrawal_slot_empty() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet.apply_slot_observed(
        _slot_observed(slot_number=3, state=SlotState.FULL, observed_at=_T0)
    )
    cabinet.apply_slot_observed(
        _slot_observed(
            slot_number=7, state=SlotState.EMPTY, battery_serial=None, soc_pct=0, observed_at=_T0
        )
    )

    cabinet.apply_swap_observed(_swap_observed())

    assert cabinet.slots[7].state == SlotState.OCCUPIED
    assert cabinet.slots[7].battery_serial == "BT001977"
    assert cabinet.slots[3].state == SlotState.EMPTY
    assert cabinet.slots[3].battery_serial is None


def test_partial_swap_with_zero_slot_does_not_touch_that_side() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet.apply_slot_observed(
        _slot_observed(slot_number=3, state=SlotState.FULL, observed_at=_T0)
    )

    cabinet.apply_swap_observed(
        _swap_observed(deposit_slot=0, deposited_battery_serial=None, withdrawal_slot=3)
    )

    assert cabinet.slots[3].state == SlotState.EMPTY
    assert 0 not in cabinet.slots


def test_swap_emits_exactly_one_battery_swapped_event() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    events = cabinet.apply_swap_observed(_swap_observed())

    assert len(events) == 1
    assert isinstance(events[0], BatterySwapped)
    assert events[0].deposited_battery_serial == "BT001977"
    assert events[0].withdrawn_battery_serial == "BT004817"


def test_any_frame_updates_last_seen_at() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    cabinet.apply_slot_observed(_slot_observed(received_at=_T0))

    assert cabinet.last_seen_at == _T0


def test_mark_offline_flips_the_flag_and_emits_one_event() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    events = cabinet.mark_offline(_T0)

    assert cabinet.online is False
    assert len(events) == 1
    assert isinstance(events[0], CabinetOffline)
    assert events[0].cabinet_id == "VTX-CAB-0042"


def test_mark_offline_is_idempotent() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet.mark_offline(_T0)

    events = cabinet.mark_offline(_T0 + timedelta(seconds=1))

    assert events == []


def test_frame_from_an_offline_cabinet_brings_it_back_online() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")
    cabinet.mark_offline(_T0)

    events = cabinet.apply_slot_observed(_slot_observed(received_at=_T0 + timedelta(minutes=5)))

    assert cabinet.online is True
    assert any(isinstance(e, CabinetOnline) for e in events)


def test_frame_from_an_already_online_cabinet_does_not_reemit_online() -> None:
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042")

    events = cabinet.apply_slot_observed(_slot_observed())

    assert not any(isinstance(e, CabinetOnline) for e in events)
