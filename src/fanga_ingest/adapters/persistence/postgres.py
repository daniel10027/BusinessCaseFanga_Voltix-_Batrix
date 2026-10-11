"""Implémentation PostgreSQL des ports de `application.ports` (SQLAlchemy 2 async).

Une `PostgresUnitOfWork` par cas d'usage : elle ouvre une session, l'engage
dans une transaction implicite, et ne la valide que si `commit()` est appelé
explicitement. Si le cas d'usage ressort sans avoir commité (doublon détecté,
exception), la transaction est annulée.
"""

from types import TracebackType

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fanga_ingest.adapters.event_codec import event_payload, event_type
from fanga_ingest.adapters.persistence.tables import (
    batteries,
    cabinets,
    inventory,
    observations,
    outbox,
)
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import DomainEvent
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class PostgresBatteryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, serial: str) -> Battery | None:
        result = await self._session.execute(
            select(batteries.c.state).where(batteries.c.serial == serial)
        )
        row = result.first()
        return Battery.from_state(row[0]) if row is not None else None

    async def save(self, battery: Battery) -> None:
        state = battery.to_state()
        stmt = pg_insert(batteries).values(
            serial=battery.serial,
            in_inventory=battery.in_inventory,
            faulted=battery.faulted,
            state=state,
            updated_at=func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[batteries.c.serial],
            set_={
                "in_inventory": stmt.excluded.in_inventory,
                "faulted": stmt.excluded.faulted,
                "state": stmt.excluded.state,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)


class PostgresCabinetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cabinet_id: str) -> Cabinet | None:
        result = await self._session.execute(
            select(cabinets.c.state).where(cabinets.c.cabinet_id == cabinet_id)
        )
        row = result.first()
        return Cabinet.from_state(row[0]) if row is not None else None

    async def save(self, cabinet: Cabinet) -> None:
        state = cabinet.to_state()
        stmt = pg_insert(cabinets).values(
            cabinet_id=cabinet.cabinet_id,
            online=cabinet.online,
            last_seen_at=cabinet.last_seen_at,
            state=state,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[cabinets.c.cabinet_id],
            set_={
                "online": stmt.excluded.online,
                "last_seen_at": stmt.excluded.last_seen_at,
                "state": stmt.excluded.state,
            },
        )
        await self._session.execute(stmt)

    async def list_all(self) -> list[Cabinet]:
        result = await self._session.execute(select(cabinets.c.state))
        return [Cabinet.from_state(row[0]) for row in result.all()]


class PostgresObservationStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_slot_observed(self, obs: SlotObserved) -> bool:
        return await self._record(obs.dedup_key, "slot_observed")

    async def record_swap_observed(self, obs: SwapObserved) -> bool:
        return await self._record(obs.dedup_key, "swap_observed")

    async def record_telemetry_observed(self, obs: TelemetryObserved) -> bool:
        return await self._record(obs.dedup_key, "telemetry_observed")

    async def _record(self, dedup_key: str, kind: str) -> bool:
        stmt = (
            pg_insert(observations)
            .values(dedup_key=dedup_key, kind=kind, created_at=func.now())
            .on_conflict_do_nothing(index_elements=[observations.c.dedup_key])
            .returning(observations.c.dedup_key)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None


class PostgresOutboxWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(self, event: DomainEvent) -> None:
        stmt = pg_insert(outbox).values(
            event_id=event.event_id,
            type=event_type(event),
            version=1,
            occurred_at=event.occurred_at,
            payload=event_payload(event),
        )
        await self._session.execute(stmt)


class PostgresInventoryRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def contains(self, serial: str) -> bool:
        result = await self._session.execute(
            select(inventory.c.status).where(inventory.c.serial == serial)
        )
        row = result.first()
        return row is not None and row[0] == "registered"

    async def set_status(self, serial: str, status: str) -> None:
        stmt = pg_insert(inventory).values(serial=serial, status=status, updated_at=func.now())
        stmt = stmt.on_conflict_do_update(
            index_elements=[inventory.c.serial],
            set_={"status": stmt.excluded.status, "updated_at": stmt.excluded.updated_at},
        )
        await self._session.execute(stmt)


class PostgresUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> "PostgresUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.batteries = PostgresBatteryRepository(self._session)
        self.cabinets = PostgresCabinetRepository(self._session)
        self.observations = PostgresObservationStore(self._session)
        self.outbox = PostgresOutboxWriter(self._session)
        self.inventory = PostgresInventoryRegistry(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        if not self._committed:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()
        self._committed = True
