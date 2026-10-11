"""Rejeu du scénario du business case (brief, section 4), partagé entre les
tests de domaine, d'intégration et de bout en bout.

Construit directement les observations canoniques, plutôt que de repartir des
trames brutes : les traducteurs ACL des adaptateurs (Voltix/Batrix) sont
exercés séparément par leurs propres tests. Les valeurs sont celles de
l'énoncé (tables 4.1 à 4.3), horodatées de façon cohérente avec
`REPLAY_START=2026-10-01T07:59:49Z` (brief, section 7).

La trame SLOT_STATUS casier 02 / BT000555 (CRC faux) n'apparaît pas ici : une
trame invalide est rejetée avant même de produire une observation (brief,
5.4). La trame HEARTBEAT n'en produit aucune non plus (elle ne fait que tenir
`last_seen_at` à jour, un mécanisme de session, pas une observation).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.observations import (
    BatteryStatus,
    Observation,
    SlotObserved,
    SlotState,
    SwapObserved,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source

CABINET_ID = "VTX-CAB-0042"
REPLAY_START = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
SWAP_AT = datetime(
    2026, 10, 1, 8, 0, 0, tzinfo=UTC
)  # 1790841600, horloge cabinet retenue (< 5 min d'écart)

KNOWN_BATTERY_SERIALS = frozenset({"BT001977", "BT002290", "BT003105", "BT004817", "BT000555"})


def document_observations() -> list[Observation]:
    """Les observations du document. L'ordre ici n'a pas d'importance pour le
    résultat final (c'est justement ce que vérifie le test de rejeu)."""

    return [
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id=CABINET_ID,
            slot_number=3,
            state=SlotState.FULL,
            battery_serial="BT004817",
            soc_pct=96,
            voltage_v=67.2,
            temperature_c=34,
            observed_at=REPLAY_START,
            received_at=REPLAY_START,
        ),
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id=CABINET_ID,
            slot_number=5,
            state=SlotState.FAULT,
            battery_serial="BT002290",
            soc_pct=41,
            voltage_v=59.8,
            temperature_c=-3,
            observed_at=REPLAY_START + timedelta(seconds=1),
            received_at=REPLAY_START + timedelta(seconds=1),
        ),
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id=CABINET_ID,
            slot_number=7,
            state=SlotState.EMPTY,
            battery_serial=None,
            soc_pct=0,
            voltage_v=0.0,
            temperature_c=0,
            observed_at=REPLAY_START + timedelta(seconds=2),
            received_at=REPLAY_START + timedelta(seconds=2),
        ),
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id=CABINET_ID,
            slot_number=1,
            state=SlotState.CHARGING,
            battery_serial="BT003105",
            soc_pct=58,
            voltage_v=64.1,
            temperature_c=41,
            observed_at=REPLAY_START + timedelta(seconds=3),
            received_at=REPLAY_START + timedelta(seconds=3),
        ),
        SwapObserved(
            source=Source.VOLTIX,
            cabinet_id=CABINET_ID,
            deposit_slot=7,
            withdrawal_slot=3,
            deposited_battery_serial="BT001977",
            withdrawn_battery_serial="BT004817",
            observed_at=SWAP_AT,
            received_at=SWAP_AT,
        ),
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT004817",
            soc_pct=92.0,
            voltage_v=67.18,
            temperatures_c=(33.1, 34.5, 33.8),
            cycle_count=412,
            status=BatteryStatus.CHARGING,
            errors=(),
            observed_at=datetime(2026, 10, 1, 7, 59, 0, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 7, 59, 0, tzinfo=UTC),
        ),
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT002290",
            soc_pct=41.0,
            voltage_v=59.79,
            temperatures_c=(-3.0, -2.8, -3.1),
            cycle_count=873,
            status=BatteryStatus.ERROR,
            errors=("CELL_UNDERTEMP",),
            observed_at=datetime(2026, 10, 1, 7, 59, 5, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 7, 59, 5, tzinfo=UTC),
        ),
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT004817",
            soc_pct=91.8,
            voltage_v=66.95,
            temperatures_c=(33.6, 34.9, 34.1),
            cycle_count=412,
            status=BatteryStatus.DISCHARGING,
            errors=(),
            observed_at=datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC),
        ),
        # Doublon volontaire (republication QoS 1) du message précédent.
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT004817",
            soc_pct=91.8,
            voltage_v=66.95,
            temperatures_c=(33.6, 34.9, 34.1),
            cycle_count=412,
            status=BatteryStatus.DISCHARGING,
            errors=(),
            observed_at=datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC),
        ),
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT001977",
            soc_pct=12.0,
            voltage_v=61.02,
            temperatures_c=(40.2, 41.5, 40.9),
            cycle_count=198,
            status=BatteryStatus.DISCHARGING,
            errors=(),
            observed_at=datetime(2026, 10, 1, 7, 58, 0, tzinfo=UTC),  # hors d'ordre
            received_at=datetime(2026, 10, 1, 8, 1, 20, tzinfo=UTC),
        ),
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT009999",
            soc_pct=100.0,
            voltage_v=68.40,
            temperatures_c=(29.0, 29.1, 29.0),
            cycle_count=3,
            status=BatteryStatus.IDLE,
            errors=(),
            observed_at=datetime(2026, 10, 1, 8, 1, 40, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 8, 1, 40, tzinfo=UTC),
        ),
    ]


@dataclass
class ReplayResult:
    batteries: dict[str, Battery]
    cabinets: dict[str, Cabinet]


def replay(
    observations: list[Observation], known_serials: frozenset[str] = KNOWN_BATTERY_SERIALS
) -> ReplayResult:
    """Applique les observations, dans l'ordre donné, à des agrégats neufs.

    Pure domaine : ni base, ni outbox, ni déduplication par la persistance
    (celle-ci est testée séparément). Un doublon exact reste sans effet grâce
    à l'idempotence des agrégats eux-mêmes (clés d'ordre total strictes).
    """

    batteries: dict[str, Battery] = {}
    cabinets: dict[str, Cabinet] = {}

    def battery(serial: str) -> Battery:
        if serial not in batteries:
            batteries[serial] = Battery(serial=serial, in_inventory=serial in known_serials)
        return batteries[serial]

    def cabinet(cabinet_id: str) -> Cabinet:
        if cabinet_id not in cabinets:
            cabinets[cabinet_id] = Cabinet(cabinet_id=cabinet_id)
        return cabinets[cabinet_id]

    for obs in observations:
        if isinstance(obs, SlotObserved):
            cabinet(obs.cabinet_id).apply_slot_observed(obs)
            if obs.battery_serial is not None:
                battery(obs.battery_serial).apply_slot_observed(obs)
        elif isinstance(obs, SwapObserved):
            cabinet(obs.cabinet_id).apply_swap_observed(obs)
            if obs.deposited_battery_serial is not None:
                battery(obs.deposited_battery_serial).apply_swap_as_deposit(obs)
            if obs.withdrawn_battery_serial is not None:
                battery(obs.withdrawn_battery_serial).apply_swap_as_withdrawal(obs)
        elif isinstance(obs, TelemetryObserved):
            battery(obs.battery_serial).apply_telemetry_observed(obs)

    return ReplayResult(batteries=batteries, cabinets=cabinets)
