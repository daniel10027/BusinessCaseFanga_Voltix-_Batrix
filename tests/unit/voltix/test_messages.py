import pytest

from fanga_ingest.adapters.vendors.voltix.messages import (
    CommandCode,
    HeartbeatMessage,
    LoginMessage,
    MalformedMessageError,
    SlotState,
    SlotStatusMessage,
    SwapEventMessage,
    UnknownCommandError,
    decode_message,
)
from fanga_ingest.adapters.vendors.voltix.protocol import FrameDecoder, RawFrame
from tests.fixtures import document


def _decode_all_document_frames() -> list[RawFrame]:
    decoder = FrameDecoder()
    frames = decoder.feed(b"".join(document.captured_frames_bytes()))
    frames += decoder.feed(document.socket_read_1())
    frames += decoder.feed(document.socket_read_2())
    return frames


def test_decode_login_frame() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[0])

    assert message == LoginMessage(cabinet_id="VTX-CAB-0042", firmware_major=2, firmware_minor=7)


def test_decode_slot_status_full_battery() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[1])

    assert message == SlotStatusMessage(
        slot_number=3,
        state=SlotState.FULL,
        battery_serial="BT004817",
        soc_pct=96,
        voltage_v=67.2,
        temperature_c=34,
    )


def test_decode_slot_status_faulted_battery_has_negative_temperature() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[2])

    assert message == SlotStatusMessage(
        slot_number=5,
        state=SlotState.FAULT,
        battery_serial="BT002290",
        soc_pct=41,
        voltage_v=59.8,
        temperature_c=-3,
    )


def test_decode_slot_status_empty_slot_has_no_serial() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[3])

    assert message == SlotStatusMessage(
        slot_number=7,
        state=SlotState.EMPTY,
        battery_serial=None,
        soc_pct=0,
        voltage_v=0.0,
        temperature_c=0,
    )


def test_decode_slot_status_charging_battery_from_split_socket_read() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[5])

    assert message == SlotStatusMessage(
        slot_number=1,
        state=SlotState.CHARGING,
        battery_serial="BT003105",
        soc_pct=58,
        voltage_v=64.1,
        temperature_c=41,
    )


def test_decode_swap_event() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[6])

    assert message == SwapEventMessage(
        deposit_slot=7,
        withdrawal_slot=3,
        deposited_battery_serial="BT001977",
        withdrawn_battery_serial="BT004817",
        cabinet_clock_epoch_s=1790841600,
    )


def test_decode_heartbeat() -> None:
    frames = _decode_all_document_frames()
    message = decode_message(frames[7])

    assert message == HeartbeatMessage()


def test_decode_unknown_command_raises() -> None:
    frame = RawFrame(command=0x99, data=b"", crc_ok=True)

    with pytest.raises(UnknownCommandError) as excinfo:
        decode_message(frame)
    assert excinfo.value.command == 0x99


@pytest.mark.parametrize(
    "command",
    [CommandCode.LOGIN, CommandCode.SLOT_STATUS, CommandCode.SWAP_EVENT, CommandCode.HEARTBEAT],
)
def test_decode_wrong_data_size_raises(command: CommandCode) -> None:
    frame = RawFrame(command=command, data=b"\x01\x02\x03", crc_ok=True)

    with pytest.raises(MalformedMessageError):
        decode_message(frame)


def test_decode_slot_status_unknown_state_raises() -> None:
    data = bytes([1, 0x09]) + b"\x00" * 8 + bytes([0, 0, 0, 0])
    frame = RawFrame(command=CommandCode.SLOT_STATUS, data=data, crc_ok=True)

    with pytest.raises(MalformedMessageError):
        decode_message(frame)
