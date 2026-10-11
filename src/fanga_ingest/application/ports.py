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

    async def save(self, battery: Battery) -> None:
        """Insère ou met à jour (upsert) : fonctionne pour un agrégat neuf
        comme pour un agrégat déjà existant, puisque `get()` renvoie une
        instance désérialisée indépendante de celle persistée."""
        ...


class CabinetRepository(Protocol):
    async def get(self, cabinet_id: str) -> Cabinet | None: ...
    async def save(self, cabinet: Cabinet) -> None: ...


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


class InventoryRegistry(Protocol):
    """Sait quels numéros de série l'inventaire Fanga connaît, et les tient à jour.

    `contains()` sert à décider si une batterie jamais vue est mise en
    quarantaine ou non. `set_status()` est appelé quand l'API métier (via
    NestJS) confirme un enregistrement ou un retrait (brief, 5.9).
    """

    async def contains(self, serial: str) -> bool: ...
    async def set_status(self, serial: str, status: str) -> None: ...


class UnitOfWork(Protocol):
    """Délimite une transaction : batteries, cabinets, observations et outbox
    sont engagés ou annulés ensemble."""

    batteries: BatteryRepository
    cabinets: CabinetRepository
    observations: ObservationStore
    outbox: OutboxWriter
    inventory: InventoryRegistry

    async def __aenter__(self) -> "UnitOfWork": ...
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    async def commit(self) -> None: ...
