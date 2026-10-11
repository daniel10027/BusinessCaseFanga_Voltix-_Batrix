from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fanga_ingest.adapters.vendors.voltix.protocol import ACK_ERROR, ACK_OK, build_ack, build_frame
from fanga_ingest.adapters.vendors.voltix.session import VoltixSession
from fanga_ingest.domain.observations import Observation
from tests.fixtures import document

_RECEIVED_AT = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
_CABINET_ID = "VTX-CAB-0042"


def _login_frame(cabinet_id: str, major: int = 2, minor: int = 7) -> bytes:
    data = cabinet_id.encode("ascii").ljust(12, b"\x00") + bytes([major, minor])
    return build_frame(0x01, data)


async def _noop(_obs: Observation) -> None:
    return None


def _recording_handler() -> tuple[list[Observation], Callable[[Observation], Awaitable[None]]]:
    received: list[Observation] = []

    async def handler(obs: Observation) -> None:
        received.append(obs)

    return received, handler


async def test_frame_before_login_is_rejected_and_closes() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)

    acks = await session.feed(build_ack(ACK_OK), _RECEIVED_AT)  # une trame qui n'est pas un LOGIN

    assert acks == [build_ack(ACK_ERROR)]
    assert session.should_close is True


async def test_login_from_unknown_cabinet_is_rejected_and_closes() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)

    acks = await session.feed(_login_frame("UNKNOWN-CAB"), _RECEIVED_AT)

    assert acks == [build_ack(ACK_ERROR)]
    assert session.should_close is True
    assert session.cabinet_id is None


async def test_frame_with_bad_crc_before_login_is_rejected_and_closes() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)
    corrupted = bytearray(_login_frame(_CABINET_ID))
    corrupted[-1] ^= 0xFF  # abîme le CRC

    acks = await session.feed(bytes(corrupted), _RECEIVED_AT)

    assert acks == [build_ack(ACK_ERROR)]
    assert session.should_close is True
    assert session.cabinet_id is None


async def test_login_from_allowed_cabinet_is_accepted() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)

    acks = await session.feed(_login_frame(_CABINET_ID), _RECEIVED_AT)

    assert acks == [build_ack(ACK_OK)]
    assert session.should_close is False
    assert session.cabinet_id == _CABINET_ID


async def test_full_document_stream_produces_seven_ok_and_one_error() -> None:
    received, handler = _recording_handler()
    session = VoltixSession(
        allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=handler
    )

    stream = b"".join(document.captured_frames_bytes())
    acks = await session.feed(stream, _RECEIVED_AT)
    acks += await session.feed(document.socket_read_1(), _RECEIVED_AT)
    acks += await session.feed(document.socket_read_2(), _RECEIVED_AT)

    assert acks.count(build_ack(ACK_OK)) == 7
    assert acks.count(build_ack(ACK_ERROR)) == 1
    assert len(acks) == 8
    assert session.should_close is False
    # LOGIN et HEARTBEAT ne produisent pas d'observation ; la trame au CRC
    # faux non plus : il reste 4 SLOT_STATUS (casier vide inclus) + 1 SWAP_EVENT.
    assert len(received) == 5


async def test_unknown_command_after_login_is_rejected_without_closing() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)
    await session.feed(_login_frame(_CABINET_ID), _RECEIVED_AT)

    acks = await session.feed(build_frame(0x99, b""), _RECEIVED_AT)

    assert acks == [build_ack(ACK_ERROR)]
    assert session.should_close is False


async def test_handler_failure_acks_error_without_closing_or_counting_as_invalid() -> None:
    async def failing_handler(_obs: Observation) -> None:
        raise RuntimeError("écriture impossible")

    session = VoltixSession(
        allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=failing_handler
    )
    await session.feed(_login_frame(_CABINET_ID), _RECEIVED_AT)

    slot_status_frame = document.captured_frames_bytes()[1]  # casier 03, BT004817
    acks = await session.feed(slot_status_frame, _RECEIVED_AT)

    assert acks == [build_ack(ACK_ERROR)]
    assert session.should_close is False

    # La trame était valide : un échec d'écriture n'est pas une trame
    # invalide, donc 9 autres erreurs du même genre ne doivent pas fermer.
    for _ in range(9):
        acks = await session.feed(slot_status_frame, _RECEIVED_AT)
    assert session.should_close is False


async def test_closes_after_ten_consecutive_invalid_frames_once_logged_in() -> None:
    session = VoltixSession(
        allowed_cabinet_ids=frozenset({_CABINET_ID}),
        handle_observation=_noop,
        max_invalid_frames=10,
    )
    await session.feed(_login_frame(_CABINET_ID), _RECEIVED_AT)

    invalid_frame = build_frame(0x99, b"")
    for i in range(10):
        acks = await session.feed(invalid_frame, _RECEIVED_AT)
        assert acks == [build_ack(ACK_ERROR)]
        if i < 9:
            assert session.should_close is False

    assert session.should_close is True


async def test_heartbeat_is_acked_ok() -> None:
    session = VoltixSession(allowed_cabinet_ids=frozenset({_CABINET_ID}), handle_observation=_noop)
    await session.feed(_login_frame(_CABINET_ID), _RECEIVED_AT)

    acks = await session.feed(build_frame(0x30, b""), _RECEIVED_AT)

    assert acks == [build_ack(ACK_OK)]
