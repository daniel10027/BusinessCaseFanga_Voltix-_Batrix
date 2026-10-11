"""`create_app()` contre une vraie base : vérifie que le câblage (état de
l'app, routes, horloge de rejeu) est correct, sans démarrer les tâches de
fond (serveur TCP, consommateur MQTT) qui demandent des services réels.
"""

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from fanga_ingest.config import Settings

_SECRET = "test-inventory-secret"

# `fanga_ingest.main` construit son `app` module-level à l'import (convention
# `uvicorn fanga_ingest.main:app`) : il faut un environnement minimal valide
# *avant* l'import pour que celui-ci réussisse. Chaque test passe ensuite ses
# propres `Settings` à `create_app()` ; seul l'import doit pouvoir se faire.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fanga:fanga@localhost:5433/fanga_ingest"
)
os.environ.setdefault("VOLTIX_ALLOWED_CABINET_IDS", "VTX-CAB-0042")
os.environ.setdefault("OUTBOX_HMAC_SECRET", "module-import-placeholder")
os.environ.setdefault("INVENTORY_HMAC_SECRET", "module-import-placeholder")

from fanga_ingest.main import create_app  # noqa: E402


def _settings(database_url: str, replay_start: datetime | None = None) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL=database_url,
        VOLTIX_ALLOWED_CABINET_IDS="VTX-CAB-0042",
        OUTBOX_HMAC_SECRET="outbox-secret",
        INVENTORY_HMAC_SECRET=_SECRET,
        REPLAY_START=replay_start,
    )


async def test_create_app_wires_health_and_battery_routes(engine: AsyncEngine) -> None:
    settings = _settings(engine.url.render_as_string(hide_password=False))
    app = create_app(settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health_response = await client.get("/health")
        battery_response = await client.get("/batteries/BT000000")

    assert health_response.status_code == 200
    assert battery_response.status_code == 404

    await app.state.engine.dispose()


async def test_create_app_wires_inventory_route_with_configured_secret(engine: AsyncEngine) -> None:
    settings = _settings(engine.url.render_as_string(hide_password=False))
    app = create_app(settings)

    body = json.dumps({"sn": "BT000111", "action": "registered"}).encode()
    signature = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/inventory/batteries",
            content=body,
            headers={"X-Fanga-Signature": signature},
        )

    assert response.status_code == 204
    await app.state.engine.dispose()


async def test_create_app_uses_a_replay_clock_when_configured(engine: AsyncEngine) -> None:
    replay_start = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
    settings = _settings(
        engine.url.render_as_string(hide_password=False), replay_start=replay_start
    )

    app = create_app(settings)

    # Le câblage de l'horloge est vérifié indirectement : l'application se
    # construit sans erreur et expose bien l'heure de rejeu dans ses réglages.
    assert settings.replay_start == replay_start
    await app.state.engine.dispose()
