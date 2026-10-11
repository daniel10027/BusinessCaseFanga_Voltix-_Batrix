"""Événements métier produits par les agrégats, destinés à l'outbox (section 5.7).

`event_id` sert à l'idempotence côté NestJS ; `occurred_at` est toujours
l'instant de réception serveur de l'observation déclenchante (jamais l'horloge
du cabinet), pour rester cohérent même en cas de dérive d'horloge.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class BatterySwapped(DomainEvent):
    cabinet_id: str
    deposit_slot: int
    withdrawal_slot: int
    deposited_battery_serial: str | None
    withdrawn_battery_serial: str | None
    received_at: datetime


@dataclass(frozen=True)
class BatteryFaulted(DomainEvent):
    battery_serial: str


@dataclass(frozen=True)
class BatteryUnknownDetected(DomainEvent):
    battery_serial: str


@dataclass(frozen=True)
class BatterySocDiscrepancy(DomainEvent):
    battery_serial: str
    cabinet_soc_pct: float
    bms_soc_pct: float


@dataclass(frozen=True)
class CabinetOffline(DomainEvent):
    cabinet_id: str


@dataclass(frozen=True)
class CabinetOnline(DomainEvent):
    cabinet_id: str


def new_event_id() -> UUID:
    return uuid4()
