from datetime import UTC, datetime, timedelta

from fanga_ingest.domain.battery import Battery, LocationKind
from fanga_ingest.domain.events import BatteryFaulted, BatterySocDiscrepancy
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    SwapObserved,
    TelemetryObserved,
)
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


def test_slot_observed_sets_location_from_cabinet() -> None:
    battery = Battery(serial="BT004817")

    battery.apply_slot_observed(_slot_observed())

    assert battery.location is not None
    assert battery.location.value.kind == LocationKind.IN_CABINET
    assert battery.location.value.cabinet_id == "VTX-CAB-0042"
    assert battery.location.value.slot_number == 3
    assert battery.location.source == Source.VOLTIX


def test_bms_wins_electrical_state_when_close_in_time() -> None:
    battery = Battery(serial="BT002290")

    battery.apply_slot_observed(
        _slot_observed(slot_number=5, soc_pct=41, voltage_v=59.8, temperature_c=-3, observed_at=_T0)
    )
    battery.apply_telemetry_observed(
        _telemetry(
            soc_pct=41.0, voltage_v=59.79, temperatures_c=(-3.0, -2.8, -3.1), observed_at=_T0
        )
    )

    assert battery.soc_pct is not None
    assert battery.soc_pct.source == Source.BATRIX
    assert battery.soc_pct.value == 41.0


def test_cabinet_wins_electrical_state_when_more_than_three_minutes_newer() -> None:
    battery = Battery(serial="BT003105")
    bms_time = _T0
    cabinet_time = _T0 + timedelta(minutes=5)

    battery.apply_telemetry_observed(_telemetry(observed_at=bms_time))
    battery.apply_slot_observed(
        _slot_observed(soc_pct=58, voltage_v=64.1, observed_at=cabinet_time)
    )

    assert battery.soc_pct is not None
    assert battery.soc_pct.source == Source.VOLTIX
    assert battery.soc_pct.value == 58.0


def test_electrical_state_is_independent_of_arrival_order() -> None:
    cabinet_time = _T0
    bms_time = _T0 + timedelta(seconds=71)  # moins de 3 min : le BMS gagne malgré sa bonification

    def build_and_apply(order: list[str]) -> Battery:
        battery = Battery(serial="BT004817")
        for kind in order:
            if kind == "cabinet":
                battery.apply_slot_observed(_slot_observed(soc_pct=96, observed_at=cabinet_time))
            else:
                battery.apply_telemetry_observed(_telemetry(soc_pct=91.8, observed_at=bms_time))
        return battery

    first = build_and_apply(["cabinet", "bms"])
    second = build_and_apply(["bms", "cabinet"])

    assert first.soc_pct == second.soc_pct
    assert first.soc_pct is not None
    assert first.soc_pct.source == Source.BATRIX
    assert first.soc_pct.value == 91.8


def test_applying_the_same_telemetry_twice_is_a_no_op() -> None:
    battery = Battery(serial="BT004817")
    telemetry = _telemetry(soc_pct=91.8, observed_at=_T0 + timedelta(minutes=2))

    first_events = battery.apply_telemetry_observed(telemetry)
    state_after_first = (battery.soc_pct, battery.voltage_v, battery.cycle_count)

    second_events = battery.apply_telemetry_observed(telemetry)

    assert (battery.soc_pct, battery.voltage_v, battery.cycle_count) == state_after_first
    assert first_events == []
    assert second_events == []


def test_out_of_order_telemetry_older_than_known_is_ignored() -> None:
    battery = Battery(serial="BT001977")
    battery.apply_telemetry_observed(
        _telemetry(soc_pct=12.0, observed_at=_T0 + timedelta(minutes=10))
    )

    battery.apply_telemetry_observed(
        _telemetry(soc_pct=99.0, observed_at=_T0)
    )  # plus ancien : ignoré

    assert battery.soc_pct is not None
    assert battery.soc_pct.value == 12.0


def test_fault_is_the_union_of_cabinet_and_bms_and_fires_once() -> None:
    battery = Battery(serial="BT002290")

    events_1 = battery.apply_slot_observed(_slot_observed(state=SlotState.FAULT, observed_at=_T0))
    assert any(isinstance(e, BatteryFaulted) for e in events_1)
    assert battery.faulted is True

    events_2 = battery.apply_telemetry_observed(
        _telemetry(status=BatteryStatus.ERROR, observed_at=_T0 + timedelta(seconds=5))
    )
    assert not any(isinstance(e, BatteryFaulted) for e in events_2)
    assert battery.faulted is True


def test_soc_discrepancy_below_threshold_does_not_fire() -> None:
    battery = Battery(serial="BT004817")

    battery.apply_slot_observed(_slot_observed(soc_pct=96, observed_at=_T0))
    events = battery.apply_telemetry_observed(
        _telemetry(soc_pct=92.0, observed_at=_T0 + timedelta(seconds=1))
    )

    assert not any(isinstance(e, BatterySocDiscrepancy) for e in events)


def test_soc_discrepancy_above_threshold_within_window_fires() -> None:
    battery = Battery(serial="BT004817")

    battery.apply_slot_observed(_slot_observed(soc_pct=96, observed_at=_T0))
    events = battery.apply_telemetry_observed(
        _telemetry(soc_pct=80.0, observed_at=_T0 + timedelta(seconds=1))
    )

    discrepancies = [e for e in events if isinstance(e, BatterySocDiscrepancy)]
    assert len(discrepancies) == 1
    assert discrepancies[0].cabinet_soc_pct == 96
    assert discrepancies[0].bms_soc_pct == 80.0


def test_soc_discrepancy_is_not_rechecked_for_the_same_pair_of_readings() -> None:
    battery = Battery(serial="BT004817")
    battery.apply_slot_observed(_slot_observed(soc_pct=96, observed_at=_T0))
    first_events = battery.apply_telemetry_observed(
        _telemetry(soc_pct=80.0, observed_at=_T0 + timedelta(seconds=1))
    )
    assert any(isinstance(e, BatterySocDiscrepancy) for e in first_events)

    # Un nouveau message BMS qui ne change pas la mesure cabinet retenue ne
    # doit pas re-déclencher l'événement pour exactement le même couple.
    second_events = battery.apply_telemetry_observed(
        _telemetry(soc_pct=80.0, observed_at=_T0 + timedelta(seconds=1))
    )
    assert not any(isinstance(e, BatterySocDiscrepancy) for e in second_events)


def test_soc_discrepancy_above_threshold_but_outside_window_does_not_fire() -> None:
    battery = Battery(serial="BT004817")

    battery.apply_slot_observed(_slot_observed(soc_pct=96, observed_at=_T0))
    events = battery.apply_telemetry_observed(
        _telemetry(soc_pct=80.0, observed_at=_T0 + timedelta(minutes=10))
    )

    assert not any(isinstance(e, BatterySocDiscrepancy) for e in events)


def test_swap_deposit_then_withdrawal_sets_location() -> None:
    deposited = Battery(serial="BT001977")
    withdrawn = Battery(serial="BT004817")
    swap = SwapObserved(
        source=Source.VOLTIX,
        cabinet_id="VTX-CAB-0042",
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        observed_at=_T0 + timedelta(minutes=1),
        received_at=_T0 + timedelta(minutes=1),
    )

    deposited.apply_swap_as_deposit(swap)
    withdrawn.apply_swap_as_withdrawal(swap)

    assert deposited.location is not None
    assert deposited.location.value.kind == LocationKind.IN_CABINET
    assert deposited.location.value.slot_number == 7

    assert withdrawn.location is not None
    assert withdrawn.location.value.kind == LocationKind.OUT_OF_CABINET
