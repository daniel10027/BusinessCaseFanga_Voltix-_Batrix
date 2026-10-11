"""Unité de travail en mémoire, utilisée uniquement par les tests unitaires.

Ce n'est pas l'adaptateur de persistance réel (celui-ci viendra avec
PostgreSQL en phase 4) : juste assez pour exercer les cas d'usage sans réseau
ni base de données, en respectant la forme attendue par `application.ports`.
"""

from dataclasses import dataclass, field

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import DomainEvent
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved


@dataclass
class FakeBatteryRepository:
    store: dict[str, Battery] = field(default_factory=dict)

    async def get(self, serial: str) -> Battery | None:
        return self.store.get(serial)

    async def add(self, battery: Battery) -> None:
        self.store[battery.serial] = battery


@dataclass
class FakeCabinetRepository:
    store: dict[str, Cabinet] = field(default_factory=dict)

    async def get(self, cabinet_id: str) -> Cabinet | None:
        return self.store.get(cabinet_id)

    async def add(self, cabinet: Cabinet) -> None:
        self.store[cabinet.cabinet_id] = cabinet


@dataclass
class FakeObservationStore:
    seen_dedup_keys: set[str] = field(default_factory=set)

    async def _record(self, dedup_key: str) -> bool:
        if dedup_key in self.seen_dedup_keys:
            return False
        self.seen_dedup_keys.add(dedup_key)
        return True

    async def record_slot_observed(self, obs: SlotObserved) -> bool:
        return await self._record(obs.dedup_key)

    async def record_swap_observed(self, obs: SwapObserved) -> bool:
        return await self._record(obs.dedup_key)

    async def record_telemetry_observed(self, obs: TelemetryObserved) -> bool:
        return await self._record(obs.dedup_key)


@dataclass
class FakeOutboxWriter:
    published: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


@dataclass
class FakeKnownInventory:
    known_serials: frozenset[str] = frozenset()

    async def contains(self, serial: str) -> bool:
        return serial in self.known_serials


class FakeUnitOfWork:
    def __init__(self, known_serials: frozenset[str] = frozenset()) -> None:
        self.batteries = FakeBatteryRepository()
        self.cabinets = FakeCabinetRepository()
        self.observations = FakeObservationStore()
        self.outbox = FakeOutboxWriter()
        self.inventory = FakeKnownInventory(known_serials)
        self.commits = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
