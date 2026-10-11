"""Unité de travail en mémoire, utilisée uniquement par les tests unitaires.

Ce n'est pas l'adaptateur de persistance réel (celui-ci vit dans
`adapters/persistence/`, branché sur PostgreSQL) : juste assez pour exercer
les cas d'usage sans réseau ni base de données, en respectant la forme
attendue par `application.ports`.

`get()` et `save()` passent par `to_state()`/`from_state()` plutôt que de
stocker directement la référence Python : c'est ce qui simule fidèlement la
frontière de (dé)sérialisation d'un vrai dépôt, et qui aurait détecté le bug
« batterie mutée en mémoire mais jamais sauvegardée » dès les tests
unitaires, sans attendre une vraie base.
"""

from dataclasses import dataclass, field
from typing import Any

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import DomainEvent
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved


@dataclass
class FakeBatteryRepository:
    _states: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def get(self, serial: str) -> Battery | None:
        state = self._states.get(serial)
        return Battery.from_state(state) if state is not None else None

    async def save(self, battery: Battery) -> None:
        self._states[battery.serial] = battery.to_state()

    @property
    def store(self) -> dict[str, Battery]:
        """Pour les assertions de test : un aperçu désérialisé de chaque batterie."""
        return {serial: Battery.from_state(state) for serial, state in self._states.items()}


@dataclass
class FakeCabinetRepository:
    _states: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def get(self, cabinet_id: str) -> Cabinet | None:
        state = self._states.get(cabinet_id)
        return Cabinet.from_state(state) if state is not None else None

    async def save(self, cabinet: Cabinet) -> None:
        self._states[cabinet.cabinet_id] = cabinet.to_state()

    async def list_all(self) -> list[Cabinet]:
        return [Cabinet.from_state(state) for state in self._states.values()]

    @property
    def store(self) -> dict[str, Cabinet]:
        return {cid: Cabinet.from_state(state) for cid, state in self._states.items()}


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
class FakeInventoryRegistry:
    known_serials: set[str] = field(default_factory=set)

    async def contains(self, serial: str) -> bool:
        return serial in self.known_serials

    async def set_status(self, serial: str, status: str) -> None:
        if status == "registered":
            self.known_serials.add(serial)
        else:
            self.known_serials.discard(serial)


class FakeUnitOfWork:
    def __init__(self, known_serials: frozenset[str] = frozenset()) -> None:
        self.batteries = FakeBatteryRepository()
        self.cabinets = FakeCabinetRepository()
        self.observations = FakeObservationStore()
        self.outbox = FakeOutboxWriter()
        self.inventory = FakeInventoryRegistry(set(known_serials))
        self.commits = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
