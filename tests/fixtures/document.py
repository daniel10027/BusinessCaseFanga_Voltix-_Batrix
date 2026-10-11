"""Données brutes du business case (section 3 du brief), copiées telles quelles.

Centralise les trames Voltix et les messages Batrix de l'énoncé pour pouvoir les
rejouer à l'identique dans les tests unitaires, d'intégration et de bout en bout.
"""

CABINET_ID = "VTX-CAB-0042"

# Les 5 premières trames capturées sur le cabinet (LOGIN puis 4 SLOT_STATUS),
# dans l'ordre d'arrivée. La dernière porte un CRC volontairement faux.
CAPTURED_FRAMES_HEX = [
    "AA 55 0F 01 56 54 58 2D 43 41 42 2D 30 30 34 32 02 07 0F 3F",
    "AA 55 0F 10 03 02 42 54 30 30 34 38 31 37 60 02 A0 22 5A 66",
    "AA 55 0F 10 05 03 42 54 30 30 32 32 39 30 29 02 56 FD D0 27",
    "AA 55 0F 10 07 00 00 00 00 00 00 00 00 00 00 00 00 00 ED CF",
    "AA 55 0F 10 02 02 42 54 30 30 30 35 35 35 64 02 A8 1E F9 6B",
]

# Les deux lectures socket successives (SLOT_STATUS casier 01, SWAP_EVENT,
# HEARTBEAT), découpées exactement comme reçu par le serveur.
SOCKET_READ_1_HEX = (
    "AA 55 0F 10 01 01 42 54 30 30 33 31 30 35 3A 02 81 29 B7 DF " "AA 55 17 20 07 03 42 54 30"
)
SOCKET_READ_2_HEX = "30 31 39 37 37 42 54 30 30 34 38 31 37 6A BE 13 00 20 79 AA 55 01 30 00 34"


def _hex_to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str.replace(" ", ""))


def captured_frames_bytes() -> list[bytes]:
    """Les 5 trames capturées, chacune comme un bloc d'octets séparé."""
    return [_hex_to_bytes(h) for h in CAPTURED_FRAMES_HEX]


def socket_read_1() -> bytes:
    return _hex_to_bytes(SOCKET_READ_1_HEX)


def socket_read_2() -> bytes:
    return _hex_to_bytes(SOCKET_READ_2_HEX)


def all_voltix_bytes_in_one_block() -> bytes:
    """Les 8 trames concaténées en un seul bloc, comme si tout arrivait d'un coup."""
    return b"".join(captured_frames_bytes()) + socket_read_1() + socket_read_2()


# Messages Batrix (MQTT), tels que publiés, dans l'ordre d'arrivée sur le broker.
BATRIX_MESSAGES: list[dict] = [
    {
        "sn": "BT004817",
        "ts": 1790841540000,
        "soc": 920,
        "v": 67180,
        "t": [331, 345, 338],
        "cyc": 412,
        "st": "CHG",
    },
    {
        "sn": "BT002290",
        "ts": 1790841545000,
        "soc": 410,
        "v": 59790,
        "t": [-30, -28, -31],
        "cyc": 873,
        "st": "ERR",
        "err": ["CELL_UNDERTEMP"],
    },
    {
        "sn": "BT004817",
        "ts": 1790841660000,
        "soc": 918,
        "v": 66950,
        "t": [336, 349, 341],
        "cyc": 412,
        "st": "DSG",
    },
    {
        # Doublon volontaire du message précédent (republication QoS 1).
        "sn": "BT004817",
        "ts": 1790841660000,
        "soc": 918,
        "v": 66950,
        "t": [336, 349, 341],
        "cyc": 412,
        "st": "DSG",
    },
    {
        # Horodatage antérieur aux messages déjà reçus : message hors d'ordre.
        "sn": "BT001977",
        "ts": 1790841480000,
        "soc": 120,
        "v": 61020,
        "t": [402, 415, 409],
        "cyc": 198,
        "st": "DSG",
    },
    {
        # Numéro de série hors inventaire Fanga.
        "sn": "BT009999",
        "ts": 1790841700000,
        "soc": 1000,
        "v": 68400,
        "t": [290, 291, 290],
        "cyc": 3,
        "st": "IDLE",
    },
]

# Inventaire Fanga tel que donné dans l'énoncé (fait référence, section 3.2).
KNOWN_BATTERY_SERIALS = {"BT001977", "BT002290", "BT003105", "BT004817", "BT000555"}
