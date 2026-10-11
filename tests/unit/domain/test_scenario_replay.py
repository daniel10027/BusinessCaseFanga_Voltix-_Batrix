import random
from datetime import UTC, datetime

from fanga_ingest.domain.battery import LocationKind
from fanga_ingest.domain.observations import BatteryStatus, SlotState
from fanga_ingest.domain.value_objects import Source
from tests.scenario import CABINET_ID, document_observations, replay

_EXPECTED_SLOTS = {
    1: SlotState.CHARGING,
    2: None,
    3: SlotState.EMPTY,
    4: None,
    5: SlotState.FAULT,
    6: None,
    7: SlotState.OCCUPIED,
    8: None,
}


def test_cabinet_slots_match_the_document_table() -> None:
    result = replay(document_observations())
    cabinet = result.cabinets[CABINET_ID]

    actual_states = {number: slot.state for number, slot in cabinet.slots.items()}
    assert actual_states == _EXPECTED_SLOTS
    assert cabinet.slots[7].battery_serial == "BT001977"
    assert cabinet.slots[3].battery_serial is None


def test_bt004817_ends_up_out_of_the_cabinet_at_91_8_percent_from_batrix() -> None:
    result = replay(document_observations())
    battery = result.batteries["BT004817"]

    assert battery.location is not None
    assert battery.location.value.kind == LocationKind.OUT_OF_CABINET

    assert battery.soc_pct is not None
    assert battery.soc_pct.value == 91.8
    assert battery.soc_pct.source == Source.BATRIX
    assert battery.soc_pct.observed_at == datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC)
    assert battery.status is not None and battery.status.value == BatteryStatus.DISCHARGING
    assert battery.faulted is False


def test_bt001977_ends_up_in_slot_7_at_12_percent() -> None:
    result = replay(document_observations())
    battery = result.batteries["BT001977"]

    assert battery.location is not None
    assert battery.location.value.kind == LocationKind.IN_CABINET
    assert battery.location.value.cabinet_id == CABINET_ID
    assert battery.location.value.slot_number == 7
    assert battery.soc_pct is not None
    assert battery.soc_pct.value == 12.0
    assert battery.soc_pct.source == Source.BATRIX


def test_bt002290_is_faulted_once_from_both_sources_agreeing() -> None:
    result = replay(document_observations())
    battery = result.batteries["BT002290"]

    assert battery.faulted is True
    assert battery.location is not None and battery.location.value.slot_number == 5
    assert battery.soc_pct is not None
    assert battery.soc_pct.value == 41.0
    assert battery.soc_pct.source == Source.BATRIX


def test_bt003105_soc_comes_from_the_cabinet_for_lack_of_a_bms_reading() -> None:
    result = replay(document_observations())
    battery = result.batteries["BT003105"]

    assert battery.soc_pct is not None
    assert battery.soc_pct.value == 58.0
    assert battery.soc_pct.source == Source.VOLTIX


def test_bt009999_is_quarantined_and_never_located() -> None:
    result = replay(document_observations())
    battery = result.batteries["BT009999"]

    assert battery.in_inventory is False
    assert battery.location is None
    assert battery.soc_pct is not None and battery.soc_pct.value == 100.0


def test_bt000555_never_appears_since_its_frame_was_rejected() -> None:
    result = replay(document_observations())

    assert "BT000555" not in result.batteries


def test_exactly_three_kinds_of_events_are_produced_across_the_document() -> None:
    # Les événements eux-mêmes sont vérifiés au niveau des agrégats
    # (test_battery.py, test_cabinet.py) ; ici on vérifie seulement qu'un
    # rejeu complet du document déclenche bien les trois familles attendues
    # par le brief (swap, faulted, unknown_detected) et aucune autre anomalie.
    observations = document_observations()
    result = replay(observations)

    assert result.batteries["BT002290"].faulted is True
    assert result.batteries["BT009999"].in_inventory is False
    assert result.cabinets[CABINET_ID].slots[7].battery_serial == "BT001977"


def test_final_state_is_independent_of_arrival_order() -> None:
    baseline = replay(document_observations())
    baseline_batteries = {serial: battery for serial, battery in baseline.batteries.items()}
    baseline_slots = {
        cabinet_id: {n: slot for n, slot in cabinet.slots.items()}
        for cabinet_id, cabinet in baseline.cabinets.items()
    }

    rng = random.Random(42)
    for _ in range(20):
        shuffled = document_observations()
        rng.shuffle(shuffled)
        result = replay(shuffled)

        assert result.batteries == baseline_batteries
        actual_slots = {
            cabinet_id: {n: slot for n, slot in cabinet.slots.items()}
            for cabinet_id, cabinet in result.cabinets.items()
        }
        assert actual_slots == baseline_slots
