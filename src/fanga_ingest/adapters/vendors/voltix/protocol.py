"""Trame binaire du protocole cabinet Voltix.

Format : en-tête (AA 55, 2 octets) · longueur (1 octet, nombre d'octets de
Commande + Données) · commande (1 octet) · données (variable) · CRC-16/Modbus
(2 octets, poids faible en premier) calculé sur Longueur + Commande + Données.
"""

from dataclasses import dataclass

HEADER = b"\xaa\x55"

_MAX_BUFFER_SIZE = 4096
_MIN_FRAME_LENGTH = 1  # une trame porte toujours au moins l'octet Commande

ACK_OK = 0x00
ACK_ERROR = 0x01
_CMD_ACK = 0x81


def crc16_modbus(data: bytes) -> int:
    """CRC-16/Modbus (polynôme 0xA001, registre initial 0xFFFF).

    Valeur de contrôle du brief : crc16_modbus(b"123456789") == 0x4B37.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


@dataclass(frozen=True)
class RawFrame:
    """Trame décodée au niveau binaire, avant interprétation de la commande."""

    command: int
    data: bytes
    crc_ok: bool


def build_frame(command: int, data: bytes = b"") -> bytes:
    """Construit une trame complète prête à être envoyée sur le fil."""
    length = 1 + len(data)
    body = bytes([length, command]) + data
    crc = crc16_modbus(body)
    return HEADER + body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_ack(status: int) -> bytes:
    """Construit la trame ACK (commande 0x81) envoyée par le serveur au cabinet."""
    return build_frame(_CMD_ACK, bytes([status]))


class FrameDecoder:
    """Découpeur de trames sans I/O, à état, un par connexion TCP.

    Accumule les octets reçus et restitue les trames complètes au fil de l'eau,
    quel que soit le découpage des lectures socket (`feed` peut être appelé avec
    un octet, avec un bloc entier, ou n'importe quel découpage intermédiaire :
    le résultat est identique).

    Resynchronisation : si l'en-tête AA 55 n'est pas trouvé dans le buffer, on ne
    garde que son dernier octet (il peut être le début d'un en-tête coupé entre
    deux lectures). Si le CRC d'une trame candidate est faux, on la restitue tout
    de même (avec crc_ok=False) mais on n'avance le buffer que d'un seul octet :
    la longueur annoncée peut elle-même être corrompue, on ne peut donc pas lui
    faire confiance pour sauter toute la trame d'un coup.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def pending_bytes(self) -> bytes:
        """Contenu actuel du buffer interne, exposé pour les tests."""
        return bytes(self._buffer)

    def feed(self, chunk: bytes) -> list[RawFrame]:
        self._buffer.extend(chunk)
        if len(self._buffer) > _MAX_BUFFER_SIZE:
            del self._buffer[: len(self._buffer) - _MAX_BUFFER_SIZE]

        frames: list[RawFrame] = []
        while True:
            frame = self._extract_one()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def _extract_one(self) -> RawFrame | None:
        # Boucle plutôt que récursion : une longueur nulle ne fait que
        # consommer un octet de resynchronisation, il faut aussitôt retenter
        # l'extraction au cas où une trame valide suivrait immédiatement.
        while True:
            index = self._buffer.find(HEADER)
            if index == -1:
                if len(self._buffer) > 1:
                    del self._buffer[:-1]
                return None
            if index > 0:
                del self._buffer[:index]

            if len(self._buffer) < 3:
                return None  # la longueur n'est pas encore arrivée

            length = self._buffer[2]
            if length < _MIN_FRAME_LENGTH:
                del self._buffer[:1]
                continue

            frame_size = 2 + 1 + length + 2
            if len(self._buffer) < frame_size:
                return None  # trame incomplète, on attend la suite

            frame_bytes = bytes(self._buffer[:frame_size])
            command_and_data = frame_bytes[3 : 3 + length]
            crc_received = frame_bytes[3 + length] | (frame_bytes[4 + length] << 8)
            crc_calculated = crc16_modbus(frame_bytes[2 : 3 + length])
            crc_ok = crc_received == crc_calculated

            if crc_ok:
                del self._buffer[:frame_size]
            else:
                del self._buffer[:1]

            return RawFrame(
                command=command_and_data[0],
                data=command_and_data[1:],
                crc_ok=crc_ok,
            )
