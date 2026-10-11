"""Consommateur MQTT Batrix : aiomqtt, QoS 1, session persistante (brief, 5.5).

`identifier` fixe + `clean_session=False` : en cas de coupure, le broker garde
la session et republie les messages QoS 1 manqués à la reconnexion, plutôt que
de les perdre. La boucle se reconnecte automatiquement toutes les 5 s.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

import aiomqtt
from pydantic import ValidationError

from fanga_ingest.adapters.vendors.batrix.schema import TelemetryMessage
from fanga_ingest.adapters.vendors.batrix.translate import translate_telemetry
from fanga_ingest.domain.observations import TelemetryObserved

logger = logging.getLogger(__name__)

_RECONNECT_INTERVAL_SECONDS = 5.0


class BatrixConsumer:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        topic_filter: str,
        handle_telemetry: Callable[[TelemetryObserved], Awaitable[None]],
        now: Callable[[], datetime],
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._topic_filter = topic_filter
        self._handle_telemetry = handle_telemetry
        self._now = now
        self.rejected_count = 0

    async def run_forever(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self._host,
                    port=self._port,
                    identifier=self._client_id,
                    clean_session=False,
                ) as client:
                    await client.subscribe(self._topic_filter, qos=1)
                    async for message in client.messages:
                        await self.handle_message(message.topic.value, message.payload)
            except aiomqtt.MqttError:
                logger.warning(
                    "connexion MQTT perdue, nouvelle tentative dans %ss",
                    _RECONNECT_INTERVAL_SECONDS,
                )
                await asyncio.sleep(_RECONNECT_INTERVAL_SECONDS)

    async def handle_message(
        self, topic: str, payload: str | bytes | bytearray | int | float | None
    ) -> None:
        serial_from_topic = _extract_serial(topic)

        try:
            raw = json.loads(payload if isinstance(payload, str | bytes | bytearray) else "")
            message = TelemetryMessage.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, TypeError):
            logger.warning("message Batrix invalide reçu sur %s", topic)
            self.rejected_count += 1
            return

        if message.sn != serial_from_topic:
            logger.warning(
                "numéro de série du topic (%s) différent du message (%s)", topic, message.sn
            )
            self.rejected_count += 1
            return

        observation = translate_telemetry(message, self._now())
        await self._handle_telemetry(observation)


def _extract_serial(topic: str) -> str | None:
    """`batrix/v1/{numero_serie}/telemetry` → le numéro de série, ou None."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "batrix" or parts[3] != "telemetry":
        return None
    return parts[2]
