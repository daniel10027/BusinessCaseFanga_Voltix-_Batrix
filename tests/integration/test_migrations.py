"""`alembic upgrade head` puis `downgrade base` sur une base vide.

Utilise le même mécanisme que la CLI (`alembic.config.Config`) plutôt que
d'appeler les scripts de révision directement, pour tester exactement ce que
`make migrate` exécute en vrai.

`command.upgrade`/`command.downgrade` sont synchrones et pilotent leur propre
boucle asyncio (`env.py` fait `asyncio.run(...)`) : on les lance dans un
thread séparé (`asyncio.to_thread`) pour ne pas entrer en conflit avec la
boucle asyncio déjà en cours du test lui-même.
"""

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PERSISTENCE_DIR = _PROJECT_ROOT / "src" / "fanga_ingest" / "adapters" / "persistence"

_EXPECTED_TABLES = {"cabinets", "batteries", "observations", "outbox", "inventory"}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_PERSISTENCE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_PERSISTENCE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    return config


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(
            await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        )


async def test_upgrade_head_then_downgrade_base_on_an_empty_database(engine: AsyncEngine) -> None:
    # str(engine.url) masquerait le mot de passe ("***") : il faut le vrai pour se connecter.
    config = _alembic_config(engine.url.render_as_string(hide_password=False))

    await asyncio.to_thread(command.downgrade, config, "base")
    assert not (await _table_names(engine)) & _EXPECTED_TABLES

    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _table_names(engine) >= _EXPECTED_TABLES

    await asyncio.to_thread(command.downgrade, config, "base")
    assert not (await _table_names(engine)) & _EXPECTED_TABLES

    # On remet la base dans l'état attendu par les autres tests d'intégration.
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _table_names(engine) >= _EXPECTED_TABLES
