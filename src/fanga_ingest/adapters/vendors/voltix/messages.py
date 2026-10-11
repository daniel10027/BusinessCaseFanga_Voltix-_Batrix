"""Décodage sémantique des trames Voltix : LOGIN, SLOT_STATUS, SWAP_EVENT, HEARTBEAT.

Les entiers multi-octets des Données sont en big-endian (confirmé par le brief).
"""

from dataclasses import dataclass
from enum import IntEnum

from fanga_ingest.adapters.vendors.voltix.protocol import RawFrame


class CommandCode(IntEnum):
    LOGIN = 0x01
    SLOT_STATUS = 0x10
    SWAP_EVENT = 0x20
    HEARTBEAT = 0x30


class SlotState(IntEnum):
    EMPTY = 0x00
    CHARGING = 0x01
    FULL = 0x02
    FAULT = 0x03


@dataclass(frozen=True)
class LoginMessage:
    cabinet_id: str
    firmware_major: int
    firmware_minor: int


@dataclass(frozen=True)
class SlotStatusMessage:
    slot_number: int
    state: SlotState
    battery_serial: str | None
    soc_pct: int
    voltage_v: float
    temperature_c: int


@dataclass(frozen=True)
class SwapEventMessage:
    deposit_slot: int
    withdrawal_slot: int
    deposited_battery_serial: str | None
    withdrawn_battery_serial: str | None
    cabinet_clock_epoch_s: int


@dataclass(frozen=True)
class HeartbeatMessage:
    pass


VoltixMessage = LoginMessage | SlotStatusMessage | SwapEventMessage | HeartbeatMessage


class UnknownCommandError(Exception):
    """Commande non reconnue : par hypothèse (5.12), le serveur répond ACK 01 sans fermer."""

    def __init__(self, command: int) -> None:
        self.command = command
        super().__init__(f"commande Voltix inconnue : 0x{command:02X}")


class MalformedMessageError(Exception):
    """La taille ou le contenu des données ne correspond pas à ce qu'attend la commande."""


def decode_message(frame: RawFrame) -> VoltixMessage:
    if frame.command == CommandCode.LOGIN:
        return _decode_login(frame.data)
    if frame.command == CommandCode.SLOT_STATUS:
        return _decode_slot_status(frame.data)
    if frame.command == CommandCode.SWAP_EVENT:
        return _decode_swap_event(frame.data)
    if frame.command == CommandCode.HEARTBEAT:
        if frame.data:
            raise MalformedMessageError("HEARTBEAT ne doit porter aucune donnée")
        return HeartbeatMessage()
    raise UnknownCommandError(frame.command)


def decode_ascii_serial(raw: bytes) -> str | None:
    """Série vide si tous ses octets valent 0x00 ou l'ASCII '0' (hypothèse 5.12)."""
    if all(byte in (0x00, ord("0")) for byte in raw):
        return None
    return raw.decode("ascii").rstrip("\x00")


def _decode_login(data: bytes) -> LoginMessage:
    if len(data) != 14:
        raise MalformedMessageError(f"LOGIN attend 14 octets de données, reçu {len(data)}")
    # Hypothèse 5.12 : l'identifiant est complété par des espaces ou des 0x00.
    cabinet_id = data[0:12].decode("ascii").rstrip("\x00 ")
    return LoginMessage(cabinet_id=cabinet_id, firmware_major=data[12], firmware_minor=data[13])


def _decode_slot_status(data: bytes) -> SlotStatusMessage:
    if len(data) != 14:
        raise MalformedMessageError(f"SLOT_STATUS attend 14 octets de données, reçu {len(data)}")
    try:
        state = SlotState(data[1])
    except ValueError as exc:
        raise MalformedMessageError(f"état de casier inconnu : 0x{data[1]:02X}") from exc
    return SlotStatusMessage(
        slot_number=data[0],
        state=state,
        battery_serial=decode_ascii_serial(data[2:10]),
        soc_pct=data[10],
        voltage_v=int.from_bytes(data[11:13], "big") / 10,
        # Hypothèse 5.12 : la température est un octet signé.
        temperature_c=int.from_bytes(data[13:14], "big", signed=True),
    )


def _decode_swap_event(data: bytes) -> SwapEventMessage:
    if len(data) != 22:
        raise MalformedMessageError(f"SWAP_EVENT attend 22 octets de données, reçu {len(data)}")
    return SwapEventMessage(
        deposit_slot=data[0],
        withdrawal_slot=data[1],
        deposited_battery_serial=decode_ascii_serial(data[2:10]),
        withdrawn_battery_serial=decode_ascii_serial(data[10:18]),
        cabinet_clock_epoch_s=int.from_bytes(data[18:22], "big"),
    )
