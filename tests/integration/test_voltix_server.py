"""Serveur TCP Voltix réel, sur le port 0 : pas de base, mais une vraie socket
loopback. C'est pour ça que ce test vit ici plutôt que dans tests/unit, même
si aucun service externe (PostgreSQL, Mosquitto) n'est nécessaire.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fanga_ingest.adapters.vendors.voltix.protocol import ACK_ERROR, ACK_OK, build_ack, build_frame
from fanga_ingest.adapters.vendors.voltix.server import VoltixServer
from fanga_ingest.domain.observations import Observation
from tests.fixtures import document

_CABINET_ID = "VTX-CAB-0042"
_ACK_SIZE = 7  # AA 55 02 81 <statut> <crc_lo> <crc_hi>


async def _noop(_obs: Observation) -> None:
    return None


def _login_frame(cabinet_id: str, major: int = 2, minor: int = 7) -> bytes:
    data = cabinet_id.encode("ascii").ljust(12, b"\x00") + bytes([major, minor])
    return build_frame(0x01, data)


async def _start_server(
    handle_observation: Callable[[Observation], Awaitable[None]] = _noop,
    max_invalid_frames: int = 10,
    read_timeout_seconds: float = 180.0,
) -> VoltixServer:
    server = VoltixServer(
        host="127.0.0.1",
        port=0,
        allowed_cabinet_ids=frozenset({_CABINET_ID}),
        handle_observation=handle_observation,
        now=lambda: datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC),
        max_invalid_frames=max_invalid_frames,
        read_timeout_seconds=read_timeout_seconds,
    )
    await server.start()
    return server


async def _read_acks(reader: asyncio.StreamReader, count: int) -> list[bytes]:
    return [await reader.readexactly(_ACK_SIZE) for _ in range(count)]


async def test_full_document_stream_over_a_real_socket_gets_seven_ok_and_one_error() -> None:
    received: list[Observation] = []

    async def handler(obs: Observation) -> None:
        received.append(obs)

    server = await _start_server(handle_observation=handler)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            writer.write(document.all_voltix_bytes_in_one_block())
            await writer.drain()

            acks = await _read_acks(reader, 8)

            assert acks.count(build_ack(ACK_OK)) == 7
            assert acks.count(build_ack(ACK_ERROR)) == 1
            assert len(received) == 5
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()


async def test_login_from_unknown_cabinet_is_refused_and_connection_closed() -> None:
    server = await _start_server()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            writer.write(_login_frame("UNKNOWN-CAB"))
            await writer.drain()

            ack = (await _read_acks(reader, 1))[0]
            assert ack == build_ack(ACK_ERROR)

            # Le serveur doit fermer la connexion derrière l'ACK d'erreur.
            remaining = await reader.read(1)
            assert remaining == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()


async def test_frame_before_login_is_refused_and_connection_closed() -> None:
    server = await _start_server()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            writer.write(build_frame(0x30, b""))  # HEARTBEAT avant tout LOGIN
            await writer.drain()

            ack = (await _read_acks(reader, 1))[0]
            assert ack == build_ack(ACK_ERROR)

            remaining = await reader.read(1)
            assert remaining == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()


async def test_connection_is_closed_after_the_read_timeout() -> None:
    server = await _start_server(read_timeout_seconds=0.05)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            writer.write(_login_frame(_CABINET_ID))
            await writer.drain()
            await _read_acks(reader, 1)

            # Rien n'est envoyé ensuite : le serveur doit fermer après le délai.
            remaining = await asyncio.wait_for(reader.read(1), timeout=1.0)
            assert remaining == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()


async def test_closes_connection_after_ten_consecutive_invalid_frames() -> None:
    server = await _start_server()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            writer.write(_login_frame(_CABINET_ID))
            await writer.drain()
            await _read_acks(reader, 1)

            invalid_frame = build_frame(0x99, b"")  # commande inconnue
            writer.write(invalid_frame * 10)
            await writer.drain()

            acks = await _read_acks(reader, 10)
            assert all(ack == build_ack(ACK_ERROR) for ack in acks)

            remaining = await reader.read(1)
            assert remaining == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()
