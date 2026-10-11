"""Ports attendus par les cas d'usage : persistance et inventaire.

Ce sont des `Protocol` : aucune dépendance concrète (SQLAlchemy, FastAPI...),
seulement la forme attendue. Les implémentations réelles vivent dans
`adapters/persistence/` (phase 4).
"""

from typing import Protocol

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import DomainEvent
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved


class BatteryRepository(Protocol):
    async def get(self, serial: str) -> Battery | None: ...
    async def add(self, battery: Battery) -> None: ...


class CabinetRepository(Protocol):
    async def get(self, cabinet_id: str) -> Cabinet | None: ...
    async def add(self, cabinet: Cabinet) -> None: ...


class ObservationStore(Protocol):
    """Enregistre une observation brute.

    Renvoie False si elle existait déjà (déduplication par `dedup_key`, via
    `INSERT ... ON CONFLICT DO NOTHING`, brief 5.3) : le cas d'usage appelant
    ne doit alors produire aucun effet.
    """

    async def record_slot_observed(self, obs: SlotObserved) -> bool: ...
    async def record_swap_observed(self, obs: SwapObserved) -> bool: ...
    async def record_telemetry_observed(self, obs: TelemetryObserved) -> bool: ...


class OutboxWriter(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class KnownInventory(Protocol):
    """Sait si un numéro de série est déjà connu de l'inventaire Fanga.

    Pour la démo, une liste statique suffit (5.9). Brancher ce port sur l'API
    métier réelle ou une réconciliation nocturne reste à faire (section « avec
    plus de temps »).
    """

    async def contains(self, serial: str) -> bool: ...


class UnitOfWork(Protocol):
    """Délimite une transaction : batteries, cabinets, observations et outbox
    sont engagés ou annulés ensemble."""

    batteries: BatteryRepository
    cabinets: CabinetRepository
    observations: ObservationStore
    outbox: OutboxWriter
    inventory: KnownInventory

    async def __aenter__(self) -> "UnitOfWork": ...
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    async def commit(self) -> None: ...
