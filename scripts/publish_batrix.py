#!/usr/bin/env python3
"""Publie les messages Batrix du document sur le broker MQTT (démo et E2E).

N'utilise pas `mosquitto_pub` : un client MQTT Python (`aiomqtt`, déjà une
dépendance du service) suffit, donc rien à installer sur l'hôte qui lance ce
script.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiomqtt  # noqa: E402
from tests.fixtures import document  # noqa: E402


async def main(host: str, port: int) -> None:
    async with aiomqtt.Client(hostname=host, port=port) as client:
        for message in document.BATRIX_MESSAGES:
            topic = f"batrix/v1/{message['sn']}/telemetry"
            await client.publish(topic, payload=json.dumps(message), qos=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
