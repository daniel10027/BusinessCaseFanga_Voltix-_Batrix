"""Serveur TCP Voltix : une connexion par cabinet, une `VoltixSession` chacune.

L'horloge est injectée (`now`) plutôt qu'appelée directement : le composition
root (`main.py`, phase 4) y branchera l'horloge de rejeu pour la démo.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from fanga_ingest.adapters.vendors.voltix.session import VoltixSession
from fanga_ingest.domain.observations import Observation

logger = logging.getLogger(__name__)

_READ_CHUNK_SIZE = 4096
_DEFAULT_READ_TIMEOUT_SECONDS = 180.0


class VoltixServer:
    def __init__(
        self,
        host: str,
        port: int,
        allowed_cabinet_ids: frozenset[str],
        handle_observation: Callable[[Observation], Awaitable[None]],
        now: Callable[[], datetime],
        read_timeout_seconds: float = _DEFAULT_READ_TIMEOUT_SECONDS,
        max_invalid_frames: int = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._allowed_cabinet_ids = allowed_cabinet_ids
        self._handle_observation = handle_observation
        self._now = now
        self._read_timeout_seconds = read_timeout_seconds
        self._max_invalid_frames = max_invalid_frames
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        """Le port effectivement lié (utile en test, en démarrant sur le port 0)."""
        assert self._server is not None, "le serveur n'est pas démarré"
        socket_name = self._server.sockets[0].getsockname()
        return int(socket_name[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self._host, self._port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session = VoltixSession(
            allowed_cabinet_ids=self._allowed_cabinet_ids,
            handle_observation=self._handle_observation,
            max_invalid_frames=self._max_invalid_frames,
        )
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        reader.read(_READ_CHUNK_SIZE), timeout=self._read_timeout_seconds
                    )
                except TimeoutError:
                    logger.info("cabinet_id=%s timeout de lecture, fermeture", session.cabinet_id)
                    break

                if not chunk:
                    break

                acks = await session.feed(chunk, self._now())
                for ack in acks:
                    writer.write(ack)
                if acks:
                    await writer.drain()

                if session.should_close:
                    break
        finally:
            writer.close()
            await writer.wait_closed()
