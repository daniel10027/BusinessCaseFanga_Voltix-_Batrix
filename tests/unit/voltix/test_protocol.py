from fanga_ingest.adapters.vendors.voltix.protocol import (
    ACK_ERROR,
    ACK_OK,
    build_ack,
    crc16_modbus,
)


def test_crc16_modbus_reference_value() -> None:
    assert crc16_modbus(b"123456789") == 0x4B37


def test_build_ack_ok_matches_brief_example() -> None:
    assert build_ack(ACK_OK) == bytes.fromhex("AA 55 02 81 00 B0 50".replace(" ", ""))


def test_build_ack_error_matches_brief_example() -> None:
    assert build_ack(ACK_ERROR) == bytes.fromhex("AA 55 02 81 01 71 90".replace(" ", ""))
