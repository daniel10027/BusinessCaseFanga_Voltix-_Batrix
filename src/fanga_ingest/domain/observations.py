"""Observations canoniques : le contrat que doit produire tout adaptateur fournisseur.

Trois observations possibles (brief, section 5.2), chacune avec sa source,
l'instant de la mesure (`observed_at`), l'instant de réception côté serveur
(`received_at`) et une clé de déduplication unique utilisée par la persistance
(`INSERT ... ON CONFLICT DO NOTHING`).

Un nouveau fournisseur n'a besoin de produire que ces trois types : c'est tout
le contrat entre `adapters/vendors/<fournisseur>/` et le reste du système.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fanga_ingest.domain.value_objects import Source


class SlotState(StrEnum):
    """État d'un casier, tel que rapporté par le cabinet ou déduit d'un swap."""

    EMPTY = "empty"
    CHARGING = "charging"
    FULL = "full"
    FAULT = "fault"
    # Déduit d'un SWAP_EVENT : on sait qu'une batterie est présente, mais pas
    # encore dans quel état précis (le cabinet n'a pas encore renvoyé de
    # SLOT_STATUS pour ce casier depuis le dépôt).
    OCCUPIED = "occupied"


class BatteryStatus(StrEnum):
    """État électrique rapporté par le BMS (champ `st` des messages Batrix)."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"
    ERROR = "error"


@dataclass(frozen=True)
class SlotObserved:
    """Un cabinet rapporte l'état d'un de ses casiers (trame SLOT_STATUS)."""

    source: Source
    cabinet_id: str
    slot_number: int
    state: SlotState
    battery_serial: str | None
    soc_pct: int
    voltage_v: float
    temperature_c: int
    observed_at: datetime
    received_at: datetime

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.cabinet_id}:{self.slot_number}:{self.received_at.isoformat()}"


@dataclass(frozen=True)
class SwapObserved:
    """Un cabinet rapporte un échange de batteries (trame SWAP_EVENT).

    Un swap partiel (hypothèse 5.12 : casier 00 + série vide) laisse
    `deposit_slot` ou `withdrawal_slot` à 0 et la série correspondante à None.
    """

    source: Source
    cabinet_id: str
    deposit_slot: int
    withdrawal_slot: int
    deposited_battery_serial: str | None
    withdrawn_battery_serial: str | None
    observed_at: datetime
    received_at: datetime

    @property
    def dedup_key(self) -> str:
        return (
            f"{self.source}:{self.cabinet_id}:{self.observed_at.isoformat()}:"
            f"{self.deposited_battery_serial}:{self.withdrawn_battery_serial}"
        )


@dataclass(frozen=True)
class TelemetryObserved:
    """Un BMS rapporte sa télémétrie (message MQTT Batrix)."""

    source: Source
    battery_serial: str
    soc_pct: float
    voltage_v: float
    temperatures_c: tuple[float, ...]
    cycle_count: int
    status: BatteryStatus
    errors: tuple[str, ...]
    observed_at: datetime
    received_at: datetime

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.battery_serial}:{self.observed_at.isoformat()}"


Observation = SlotObserved | SwapObserved | TelemetryObserved
