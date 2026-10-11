"""Point d'assemblage : le seul fichier qui connaît tous les adaptateurs à la
fois (brief, section 5.1). Il construit l'application FastAPI, démarre le
serveur TCP Voltix, le consommateur MQTT Batrix, le relais outbox et la
supervision des cabinets comme tâches de fond, et les arrête proprement à
l'extinction.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI

from fanga_ingest.adapters.api import (
    battery_routes,
    cabinet_routes,
    health_routes,
    inventory_routes,
    metrics_routes,
)
from fanga_ingest.adapters.persistence.outbox_relay import OutboxRelay
from fanga_ingest.adapters.persistence.postgres import (
    PostgresUnitOfWork,
    create_engine,
    create_session_factory,
)
from fanga_ingest.adapters.supervision import OfflineCabinetSupervisor
from fanga_ingest.adapters.vendors.batrix.consumer import BatrixConsumer
from fanga_ingest.adapters.vendors.voltix.server import VoltixServer
from fanga_ingest.application.use_cases import (
    ingest_slot_observed,
    ingest_swap_observed,
    ingest_telemetry_observed,
)
from fanga_ingest.clock import replay_clock, system_clock
from fanga_ingest.config import Settings
from fanga_ingest.domain.observations import (
    Observation,
    SlotObserved,
    SwapObserved,
    TelemetryObserved,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    now = (
        replay_clock(settings.replay_start) if settings.replay_start is not None else system_clock()
    )

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    def uow_factory() -> PostgresUnitOfWork:
        return PostgresUnitOfWork(session_factory)

    async def handle_observation(obs: Observation) -> None:
        uow = uow_factory()
        if isinstance(obs, SlotObserved):
            await ingest_slot_observed(uow, obs)
        elif isinstance(obs, SwapObserved):
            await ingest_swap_observed(uow, obs)
        elif isinstance(obs, TelemetryObserved):
            await ingest_telemetry_observed(uow, obs)

    voltix_server = VoltixServer(
        host=settings.voltix_tcp_host,
        port=settings.voltix_tcp_port,
        allowed_cabinet_ids=settings.voltix_allowed_cabinet_ids_set,
        handle_observation=handle_observation,
        now=now,
        read_timeout_seconds=settings.voltix_read_timeout_seconds,
        max_invalid_frames=settings.voltix_max_invalid_frames,
    )

    batrix_consumer = BatrixConsumer(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        client_id=settings.mqtt_client_id,
        topic_filter=settings.mqtt_topic_filter,
        handle_telemetry=handle_observation,
        now=now,
    )

    http_client = httpx.AsyncClient()
    outbox_relay = OutboxRelay(
        session_factory, http_client, settings.nestjs_webhook_url, settings.outbox_hmac_secret
    )

    supervisor = OfflineCabinetSupervisor(
        uow_factory=uow_factory,
        now=now,
        offline_after=timedelta(seconds=settings.cabinet_offline_after_seconds),
        sweep_interval_seconds=settings.cabinet_sweep_interval_seconds,
    )

    background_tasks: list[asyncio.Task[None]] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await voltix_server.start()
        background_tasks.append(asyncio.create_task(batrix_consumer.run_forever()))
        background_tasks.append(
            asyncio.create_task(outbox_relay.run_forever(settings.outbox_relay_interval_seconds))
        )
        background_tasks.append(asyncio.create_task(supervisor.run_forever()))
        logger.info("fanga-ingest démarré (replay_start=%s)", settings.replay_start)
        try:
            yield
        finally:
            for task in background_tasks:
                task.cancel()
            await voltix_server.stop()
            await http_client.aclose()
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.engine = engine
    app.state.uow_factory = uow_factory
    app.state.inventory_hmac_secret = settings.inventory_hmac_secret

    app.include_router(battery_routes.router)
    app.include_router(cabinet_routes.router)
    app.include_router(health_routes.router)
    app.include_router(metrics_routes.router)
    app.include_router(inventory_routes.router)

    return app


app = create_app(Settings())  # type: ignore[call-arg]
