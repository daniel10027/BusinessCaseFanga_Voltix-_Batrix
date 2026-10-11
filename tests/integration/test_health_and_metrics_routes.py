"""GET /health et GET /metrics contre une vraie base (brief, 5.10, 5.11)."""

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from fanga_ingest.adapters.api.health_routes import router as health_router
from fanga_ingest.adapters.api.metrics_routes import router as metrics_router
from fanga_ingest.adapters.persistence.postgres import create_engine


def _app(engine: AsyncEngine) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.state.engine = engine
    return app


async def test_health_returns_ok_when_the_database_is_reachable(engine: AsyncEngine) -> None:
    transport = httpx.ASGITransport(app=_app(engine))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_returns_503_when_the_database_is_unreachable() -> None:
    unreachable_engine = create_engine(
        "postgresql+asyncpg://fanga:fanga@localhost:1/does_not_exist"
    )
    transport = httpx.ASGITransport(app=_app(unreachable_engine))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error"}
    await unreachable_engine.dispose()


async def test_metrics_exposes_prometheus_text_format(engine: AsyncEngine) -> None:
    transport = httpx.ASGITransport(app=_app(engine))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "cabinets_connected" in response.text
    assert "outbox_pending" in response.text
    assert "batteries_unknown" in response.text
