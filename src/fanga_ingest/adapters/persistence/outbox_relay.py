"""Relais outbox : publie les événements en attente vers NestJS par webhook
HTTP signé HMAC-SHA256 (brief, 5.7).

Un tour de relais verrouille les lignes non publiées (`FOR UPDATE SKIP
LOCKED`, pour cohabiter avec d'autres instances sans se marcher dessus), les
envoie dans l'ordre chronologique, et s'arrête au premier échec : on ne veut
jamais publier un événement plus récent avant un événement plus ancien du
même agrégat. La ligne en échec voit son compteur `attempts` incrémenté ; le
tour suivant repartira d'elle.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fanga_ingest.adapters.persistence.tables import outbox

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Fanga-Signature"
_BATCH_SIZE = 100


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        webhook_url: str,
        hmac_secret: str,
    ) -> None:
        self._session_factory = session_factory
        self._http_client = http_client
        self._webhook_url = webhook_url
        self._hmac_secret = hmac_secret

    async def run_forever(self, interval_seconds: float) -> None:
        while True:
            try:
                await self.relay_once()
            except Exception:
                logger.exception("tour de relais outbox interrompu par une erreur inattendue")
            await asyncio.sleep(interval_seconds)

    async def relay_once(self) -> int:
        """Un tour : publie ce qu'il peut, s'arrête au premier échec.

        Renvoie le nombre d'événements publiés avec succès durant ce tour.
        """
        published = 0
        async with self._session_factory() as session, session.begin():
            stmt = (
                select(outbox)
                .where(outbox.c.published_at.is_(None))
                .order_by(outbox.c.occurred_at)
                .limit(_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).mappings().all()

            for row in rows:
                if not await self._send(row):
                    await session.execute(
                        update(outbox)
                        .where(outbox.c.event_id == row["event_id"])
                        .values(attempts=outbox.c.attempts + 1)
                    )
                    break

                await session.execute(
                    update(outbox)
                    .where(outbox.c.event_id == row["event_id"])
                    .values(published_at=func.now())
                )
                published += 1

        return published

    async def _send(self, row: RowMapping) -> bool:
        body = _build_body(row)
        signature = sign_payload(self._hmac_secret, body)
        try:
            response = await self._http_client.post(
                self._webhook_url,
                content=body,
                headers={"Content-Type": "application/json", SIGNATURE_HEADER: signature},
            )
        except httpx.HTTPError:
            logger.warning("webhook NestJS inatteignable, arrêt du tour de relais")
            return False

        if response.status_code >= 300:
            logger.warning(
                "webhook NestJS a répondu %s, arrêt du tour de relais", response.status_code
            )
            return False
        return True


def _build_body(row: RowMapping) -> bytes:
    envelope: dict[str, Any] = {
        "event_id": str(row["event_id"]),
        "type": row["type"],
        "version": row["version"],
        "occurred_at": row["occurred_at"].isoformat(),
        "payload": row["payload"],
    }
    return json.dumps(envelope, sort_keys=True).encode()
