"""Fixtures communes aux tests d'intégration PostgreSQL.

`DATABASE_URL` doit pointer vers une base déjà migrée (`make migrate`). Par
défaut, celle du conteneur de développement local sur le port 5433 — en CI,
la variable d'environnement du service `postgres` prend le dessus.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.postgres import create_engine, create_session_factory
from fanga_ingest.adapters.persistence.tables import (
    batteries,
    cabinets,
    inventory,
    observations,
    outbox,
)

_DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://fanga:fanga@localhost:5433/fanga_ingest"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(_database_url())
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        for table in (outbox, observations, batteries, cabinets, inventory):
            await session.execute(table.delete())
        await session.commit()
    return factory
