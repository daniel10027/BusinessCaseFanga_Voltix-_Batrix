"""GET /metrics : format texte Prometheus (brief, 5.10).

Les compteurs (trames, messages MQTT) vivent déjà en mémoire de process
(`adapters.api.metrics`) ; les jauges d'état courant sont recalculées à
chaque appel en interrogeant la base, pour ne pas avoir à les tenir à jour
depuis chaque endroit qui change cet état.
"""

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from fanga_ingest.adapters.api.metrics import BATTERIES_UNKNOWN, CABINETS_CONNECTED, OUTBOX_PENDING
from fanga_ingest.adapters.persistence.tables import batteries, cabinets, outbox

router = APIRouter()


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as connection:
        unknown = (
            await connection.execute(
                select(func.count())
                .select_from(batteries)
                .where(batteries.c.in_inventory.is_(False))
            )
        ).scalar_one()
        connected = (
            await connection.execute(
                select(func.count()).select_from(cabinets).where(cabinets.c.online.is_(True))
            )
        ).scalar_one()
        pending = (
            await connection.execute(
                select(func.count()).select_from(outbox).where(outbox.c.published_at.is_(None))
            )
        ).scalar_one()

    BATTERIES_UNKNOWN.set(unknown)
    CABINETS_CONNECTED.set(connected)
    OUTBOX_PENDING.set(pending)

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
