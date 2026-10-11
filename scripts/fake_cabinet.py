#!/usr/bin/env python3
"""Rejoue les trames Voltix du document sur un cabinet simulé (démo et E2E).

Envoie les mêmes octets, découpés exactement comme reçus par le serveur dans
l'énoncé : le bloc des 5 premières trames capturées, puis les deux lectures
socket (`socket_read_1`, `socket_read_2`) séparément, avec une courte pause
entre chaque pour laisser le serveur traiter et accuser réception.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixtures import document  # noqa: E402


async def main(host: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        for chunk in (
            b"".join(document.captured_frames_bytes()),
            document.socket_read_1(),
            document.socket_read_2(),
        ):
            writer.write(chunk)
            await writer.drain()
            await asyncio.sleep(0.2)

        try:
            while True:
                data = await asyncio.wait_for(reader.read(4096), timeout=0.5)
                if not data:
                    break
        except TimeoutError:
            pass
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
