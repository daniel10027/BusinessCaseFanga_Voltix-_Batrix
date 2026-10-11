from fanga_ingest.adapters.vendors.voltix.protocol import (
    ACK_ERROR,
    ACK_OK,
    FrameDecoder,
    RawFrame,
    build_ack,
    crc16_modbus,
)
from tests.fixtures import document


def test_crc16_modbus_reference_value() -> None:
    assert crc16_modbus(b"123456789") == 0x4B37


def test_build_ack_ok_matches_brief_example() -> None:
    assert build_ack(ACK_OK) == bytes.fromhex("AA 55 02 81 00 B0 50".replace(" ", ""))


def test_build_ack_error_matches_brief_example() -> None:
    assert build_ack(ACK_ERROR) == bytes.fromhex("AA 55 02 81 01 71 90".replace(" ", ""))


def test_decoder_parses_the_five_captured_frames_one_with_bad_crc() -> None:
    decoder = FrameDecoder()
    stream = b"".join(document.captured_frames_bytes())

    frames = decoder.feed(stream)

    assert len(frames) == 5
    assert [f.crc_ok for f in frames] == [True, True, True, True, False]
    # Après une trame au CRC faux non suivie d'un nouvel en-tête, il reste au
    # plus un octet en buffer (resynchronisation potentielle au prochain feed).
    assert len(decoder.pending_bytes) <= 1


def test_decoder_handles_a_frame_split_across_two_socket_reads() -> None:
    decoder = FrameDecoder()

    frames_from_read_1 = decoder.feed(document.socket_read_1())
    frames_from_read_2 = decoder.feed(document.socket_read_2())

    frames = frames_from_read_1 + frames_from_read_2
    assert [(f.command, f.crc_ok) for f in frames] == [(0x10, True), (0x20, True), (0x30, True)]


def test_decoder_result_is_independent_of_how_bytes_are_chunked() -> None:
    full_stream = document.all_voltix_bytes_in_one_block()

    decoder_whole = FrameDecoder()
    frames_whole = decoder_whole.feed(full_stream)

    decoder_byte_by_byte = FrameDecoder()
    frames_byte_by_byte: list[RawFrame] = []
    for byte in full_stream:
        frames_byte_by_byte.extend(decoder_byte_by_byte.feed(bytes([byte])))

    assert frames_whole == frames_byte_by_byte
    assert len(frames_whole) == 8


def test_decoder_resynchronises_past_an_isolated_stray_header_byte() -> None:
    decoder = FrameDecoder()
    ack_ok = build_ack(ACK_OK)
    # Un octet AA isolé (pas suivi de 55) ne doit pas empêcher de décoder la
    # trame valide qui suit.
    stream = b"\xaa\x01\x02" + ack_ok

    frames = decoder.feed(stream)

    assert len(frames) == 1
    assert frames[0] == RawFrame(command=0x81, data=bytes([ACK_OK]), crc_ok=True)


def test_decoder_ignores_a_frame_announcing_zero_length() -> None:
    decoder = FrameDecoder()
    ack_ok = build_ack(ACK_OK)
    # AA 55 avec longueur nulle : trame invalide, aucune commande à en tirer.
    stream = b"\xaa\x55\x00" + ack_ok

    frames = decoder.feed(stream)

    assert len(frames) == 1
    assert frames[0].crc_ok is True


def test_decoder_buffer_is_capped_even_when_fed_only_garbage() -> None:
    decoder = FrameDecoder()

    decoder.feed(b"\x00" * 10_000)

    assert len(decoder.pending_bytes) <= 4096


def test_decoder_still_works_after_a_long_garbage_stream() -> None:
    decoder = FrameDecoder()
    decoder.feed(b"\x00" * 10_000)

    frames = decoder.feed(build_ack(ACK_OK))

    assert len(frames) == 1
    assert frames[0].crc_ok is True
