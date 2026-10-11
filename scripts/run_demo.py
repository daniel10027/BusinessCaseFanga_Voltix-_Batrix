#!/usr/bin/env python3
"""Démo : rejoue les trames du document contre la pile `docker compose` déjà
démarrée, puis affiche l'état consolidé de BT004817 (cible : hors cabinet,
91,8 %, source batrix).

Enregistre d'abord l'inventaire connu (brief, 5.9) : sans cet appel, les
batteries BT001977/BT002290/BT003105/BT004817 seraient elles aussi mises en
quarantaine comme BT009999, et le document produirait 7 événements au lieu
des 3 attendus (battery.swapped, battery.faulted, battery.unknown_detected).
"""

import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixtures.document import KNOWN_BATTERY_SERIALS  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_API_URL = "http://localhost:8000"
_INVENTORY_HMAC_SECRET = "change-me-demo-secret"  # valeur de démo du docker-compose.yml


def _wait_for_health(timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{_API_URL}/health", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(
        "le service n'a pas répondu sur /health à temps : `docker compose up` est-il lancé ?"
    )


def _register_known_inventory() -> None:
    for serial in sorted(KNOWN_BATTERY_SERIALS):
        body = json.dumps({"sn": serial, "action": "registered"}).encode()
        signature = hmac.new(_INVENTORY_HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()
        response = httpx.post(
            f"{_API_URL}/internal/inventory/batteries",
            content=body,
            headers={"Content-Type": "application/json", "X-Fanga-Signature": signature},
            timeout=5.0,
        )
        response.raise_for_status()


def main() -> None:
    print("Attente de /health...")
    _wait_for_health()

    print("Enregistrement de l'inventaire connu...")
    _register_known_inventory()

    print("Rejeu du cabinet Voltix (VTX-CAB-0042)...")
    subprocess.run([sys.executable, str(_PROJECT_ROOT / "scripts" / "fake_cabinet.py")], check=True)

    print("Publication de la télémétrie Batrix...")
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "scripts" / "publish_batrix.py")], check=True
    )

    time.sleep(1.0)

    response = httpx.get(f"{_API_URL}/batteries/BT004817", timeout=5.0)
    response.raise_for_status()
    body = response.json()

    print()
    print("BT004817 :")
    print(f"  localisation : {body['location']}")
    print(f"  SOC          : {body['soc_pct']}")
    print(f"  statut       : {body['status']}")


if __name__ == "__main__":
    main()
