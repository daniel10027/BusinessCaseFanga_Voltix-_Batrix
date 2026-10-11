"""Détection de cabinet hors ligne : tâche périodique (brief, 5.10).

Tourne toutes les `sweep_interval_seconds`. Un cabinet est déclaré hors ligne
s'il n'a donné aucun signe de vie (trame, HEARTBEAT compris) depuis plus de
`offline_after`. L'horloge est injectée (`now`), jamais appelée directement :
la démo s'appuie sur l'horloge de rejeu, pas sur l'heure système.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from fanga_ingest.application.ports import UnitOfWork
from fanga_ingest.application.use_cases import detect_offline_cabinets

logger = logging.getLogger(__name__)


class OfflineCabinetSupervisor:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        now: Callable[[], datetime],
        offline_after: timedelta,
        sweep_interval_seconds: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._now = now
        self._offline_after = offline_after
        self._sweep_interval_seconds = sweep_interval_seconds

    async def run_forever(self) -> None:
        while True:
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("passage de supervision des cabinets interrompu par une erreur")
            await asyncio.sleep(self._sweep_interval_seconds)

    async def sweep_once(self) -> None:
        await detect_offline_cabinets(self._uow_factory(), self._now(), self._offline_after)
