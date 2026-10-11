"""Trame binaire du protocole cabinet Voltix.

Format : en-tête (AA 55, 2 octets) · longueur (1 octet, nombre d'octets de
Commande + Données) · commande (1 octet) · données (variable) · CRC-16/Modbus
(2 octets, poids faible en premier) calculé sur Longueur + Commande + Données.
"""

HEADER = b"\xaa\x55"

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


def build_frame(command: int, data: bytes = b"") -> bytes:
    """Construit une trame complète prête à être envoyée sur le fil."""
    length = 1 + len(data)
    body = bytes([length, command]) + data
    crc = crc16_modbus(body)
    return HEADER + body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_ack(status: int) -> bytes:
    """Construit la trame ACK (commande 0x81) envoyée par le serveur au cabinet."""
    return build_frame(_CMD_ACK, bytes([status]))
