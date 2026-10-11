"""Session Voltix : logique de handshake et de décodage pour une connexion.

Ne fait aucune I/O : reçoit des octets via `feed()`, renvoie les trames ACK à
écrire. C'est `server.py` qui relie ça à une vraie socket asyncio. Cette
séparation permet de tester toute la logique de session sans ouvrir de port.

Règles (brief, section 5.4) :
- rien n'est accepté avant LOGIN (ACK 01 + fermeture) ;
- LOGIN d'un cabinet hors liste blanche ⇒ ACK 01 + fermeture ;
- une fois loggé, une commande inconnue ou mal formée ⇒ ACK 01, sans fermer
  (hypothèse 5.12), mais compte comme trame invalide ;
- fermeture après `max_invalid_frames` trames invalides consécutives ;
- ACK 00 seulement après que l'observation a été traitée avec succès par le
  gestionnaire injecté ; un échec de traitement ⇒ ACK 01 (sans compter comme
  trame invalide : la trame elle-même était valide).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime

from fanga_ingest.adapters.api.metrics import VOLTIX_CRC_ERRORS_TOTAL, VOLTIX_FRAMES_TOTAL
from fanga_ingest.adapters.vendors.voltix.messages import (
    HeartbeatMessage,
    LoginMessage,
    MalformedMessageError,
    SlotStatusMessage,
    SwapEventMessage,
    UnknownCommandError,
    decode_message,
)
from fanga_ingest.adapters.vendors.voltix.protocol import (
    ACK_ERROR,
    ACK_OK,
    FrameDecoder,
    RawFrame,
    build_ack,
)
from fanga_ingest.adapters.vendors.voltix.translate import (
    translate_slot_status,
    translate_swap_event,
)
from fanga_ingest.domain.observations import Observation

_DEFAULT_MAX_INVALID_FRAMES = 10


class VoltixSession:
    def __init__(
        self,
        allowed_cabinet_ids: frozenset[str],
        handle_observation: Callable[[Observation], Awaitable[None]],
        max_invalid_frames: int = _DEFAULT_MAX_INVALID_FRAMES,
    ) -> None:
        self._decoder = FrameDecoder()
        self._allowed_cabinet_ids = allowed_cabinet_ids
        self._handle_observation = handle_observation
        self._max_invalid_frames = max_invalid_frames
        self._cabinet_id: str | None = None
        self._invalid_frame_count = 0
        self._closed = False

    @property
    def cabinet_id(self) -> str | None:
        return self._cabinet_id

    @property
    def should_close(self) -> bool:
        return self._closed

    async def feed(self, chunk: bytes, received_at: datetime) -> list[bytes]:
        """Traite les octets reçus, renvoie les trames ACK à écrire, dans l'ordre."""
        acks: list[bytes] = []
        for raw_frame in self._decoder.feed(chunk):
            acks.append(await self._handle_frame(raw_frame, received_at))
            if self._closed:
                break
        return acks

    async def _handle_frame(self, raw_frame: RawFrame, received_at: datetime) -> bytes:
        if self._cabinet_id is None:
            return self._handle_login(raw_frame)

        if not raw_frame.crc_ok:
            VOLTIX_CRC_ERRORS_TOTAL.inc()
            return self._reject_frame()

        try:
            message = decode_message(raw_frame)
        except (UnknownCommandError, MalformedMessageError):
            return self._reject_frame()

        try:
            observation = self._translate(message, received_at)
            if observation is not None:
                await self._handle_observation(observation)
        except Exception:
            # Frontière de la session : une trame syntaxiquement valide dont le
            # traitement échoue (écriture, etc.) ne doit pas faire tomber la
            # connexion ni compter comme trame invalide (5.4).
            VOLTIX_FRAMES_TOTAL.labels(result="error").inc()
            return build_ack(ACK_ERROR)

        self._invalid_frame_count = 0
        VOLTIX_FRAMES_TOTAL.labels(result="ok").inc()
        return build_ack(ACK_OK)

    def _translate(
        self,
        message: LoginMessage | SlotStatusMessage | SwapEventMessage | HeartbeatMessage,
        received_at: datetime,
    ) -> Observation | None:
        assert self._cabinet_id is not None
        if isinstance(message, SlotStatusMessage):
            return translate_slot_status(self._cabinet_id, message, received_at)
        if isinstance(message, SwapEventMessage):
            return translate_swap_event(self._cabinet_id, message, received_at)
        return None  # HEARTBEAT (et un second LOGIN, ignoré) ne produisent rien

    def _handle_login(self, raw_frame: RawFrame) -> bytes:
        if not raw_frame.crc_ok:
            VOLTIX_CRC_ERRORS_TOTAL.inc()
            VOLTIX_FRAMES_TOTAL.labels(result="error").inc()
            self._closed = True
            return build_ack(ACK_ERROR)

        try:
            message = decode_message(raw_frame)
        except (UnknownCommandError, MalformedMessageError):
            VOLTIX_FRAMES_TOTAL.labels(result="error").inc()
            self._closed = True
            return build_ack(ACK_ERROR)

        if (
            not isinstance(message, LoginMessage)
            or message.cabinet_id not in self._allowed_cabinet_ids
        ):
            VOLTIX_FRAMES_TOTAL.labels(result="error").inc()
            self._closed = True
            return build_ack(ACK_ERROR)

        self._cabinet_id = message.cabinet_id
        VOLTIX_FRAMES_TOTAL.labels(result="ok").inc()
        return build_ack(ACK_OK)

    def _reject_frame(self) -> bytes:
        VOLTIX_FRAMES_TOTAL.labels(result="error").inc()
        self._invalid_frame_count += 1
        if self._invalid_frame_count >= self._max_invalid_frames:
            self._closed = True
        return build_ack(ACK_ERROR)
