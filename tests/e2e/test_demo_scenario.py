"""Bout en bout : pile `docker compose` complète, rejouée comme le document.

Lent (construit et démarre toute la pile) : à lancer via `make test-e2e`, pas
dans la boucle rapide des tests unitaires/intégration.

Enregistre d'abord l'inventaire connu (brief, 5.9), sinon
BT001977/BT002290/BT003105/BT004817 seraient eux aussi mis en quarantaine
comme BT009999, et le document produirait 7 événements au lieu des 3
attendus par la table 4.3 (battery.swapped, battery.faulted,
battery.unknown_detected).
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from tests.fixtures.document import KNOWN_BATTERY_SERIALS  # noqa: E402

_API_URL = "http://localhost:8000"
_REPLAY_START = "2026-10-01T07:59:49Z"
_INVENTORY_HMAC_SECRET = "change-me-demo-secret"  # valeur de démo du docker-compose.yml


def _compose_env() -> dict[str, str]:
    return {**os.environ, "REPLAY_START": _REPLAY_START}


def _wait_for_health(timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{_API_URL}/health", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise TimeoutError("le service n'a pas répondu sur /health à temps")


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


@pytest.fixture(scope="module")
def running_stack() -> Iterator[None]:
    env = _compose_env()
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"], cwd=_PROJECT_ROOT, env=env, check=True
        )
        _wait_for_health()
        yield
    except Exception:
        subprocess.run(["docker", "compose", "logs"], cwd=_PROJECT_ROOT, env=env, check=False)
        raise
    finally:
        subprocess.run(["docker", "compose", "down", "-v"], cwd=_PROJECT_ROOT, env=env, check=False)


def test_full_demo_scenario_end_to_end(running_stack: None) -> None:
    _register_known_inventory()

    subprocess.run([sys.executable, str(_PROJECT_ROOT / "scripts" / "fake_cabinet.py")], check=True)
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "scripts" / "publish_batrix.py")], check=True
    )
    time.sleep(1.0)

    bt004817 = httpx.get(f"{_API_URL}/batteries/BT004817", timeout=5.0).json()
    assert bt004817["location"]["kind"] == "out_of_cabinet"
    assert bt004817["soc_pct"] == {
        "value": 91.8,
        "source": "batrix",
        "observed_at": "2026-10-01T08:01:00Z",
    }
    assert bt004817["in_inventory"] is True

    bt009999 = httpx.get(f"{_API_URL}/batteries/BT009999", timeout=5.0).json()
    assert bt009999["in_inventory"] is False
    assert bt009999["soc_pct"]["value"] == 100.0

    slots = httpx.get(f"{_API_URL}/cabinets/VTX-CAB-0042/slots", timeout=5.0).json()
    by_number = {slot["slot_number"]: slot for slot in slots["slots"]}
    assert by_number[1]["state"] == "charging"
    assert by_number[2]["state"] == "unknown"
    assert by_number[3]["state"] == "empty"
    assert by_number[5]["state"] == "fault"
    assert by_number[7]["state"] == "occupied"
    assert by_number[7]["battery_serial"] == "BT001977"
