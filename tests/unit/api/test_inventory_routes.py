import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from fanga_ingest.adapters.api.inventory_routes import router
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.observations import BatteryStatus, TelemetryObserved
from fanga_ingest.domain.value_objects import Source
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_SECRET = "test-inventory-secret"


def _app(uow: FakeUnitOfWork) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.uow_factory = lambda: uow
    app.state.inventory_hmac_secret = _SECRET
    return app


def _sign(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork(known_serials=frozenset())


async def test_registering_a_quarantined_battery_lifts_quarantine_and_keeps_soc(
    uow: FakeUnitOfWork,
) -> None:
    battery = Battery(serial="BT009999", in_inventory=False)
    battery.apply_telemetry_observed(
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT009999",
            soc_pct=100.0,
            voltage_v=68.4,
            temperatures_c=(29.0,),
            cycle_count=3,
            status=BatteryStatus.IDLE,
            errors=(),
            observed_at=datetime(2026, 10, 1, 8, 1, 40, tzinfo=UTC),
            received_at=datetime(2026, 10, 1, 8, 1, 40, tzinfo=UTC),
        )
    )
    await uow.batteries.save(battery)

    body = json.dumps({"sn": "BT009999", "action": "registered"}).encode()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/inventory/batteries",
            content=body,
            headers={"X-Fanga-Signature": _sign(body)},
        )

    assert response.status_code == 204
    reloaded = await uow.batteries.get("BT009999")
    assert reloaded is not None
    assert reloaded.in_inventory is True
    assert reloaded.soc_pct is not None
    assert reloaded.soc_pct.value == 100.0


async def test_registering_a_never_seen_serial_creates_it(uow: FakeUnitOfWork) -> None:
    body = json.dumps({"sn": "BT000111", "action": "registered"}).encode()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/inventory/batteries",
            content=body,
            headers={"X-Fanga-Signature": _sign(body)},
        )

    assert response.status_code == 204
    reloaded = await uow.batteries.get("BT000111")
    assert reloaded is not None
    assert reloaded.in_inventory is True


async def test_retiring_a_battery_marks_it_retired(uow: FakeUnitOfWork) -> None:
    body = json.dumps({"sn": "BT004817", "action": "retired"}).encode()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/inventory/batteries",
            content=body,
            headers={"X-Fanga-Signature": _sign(body)},
        )

    assert response.status_code == 204
    reloaded = await uow.batteries.get("BT004817")
    assert reloaded is not None
    assert reloaded.retired is True


async def test_invalid_signature_is_rejected(uow: FakeUnitOfWork) -> None:
    body = json.dumps({"sn": "BT004817", "action": "registered"}).encode()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/inventory/batteries",
            content=body,
            headers={"X-Fanga-Signature": "deadbeef"},
        )

    assert response.status_code == 401


async def test_missing_signature_is_rejected(uow: FakeUnitOfWork) -> None:
    body = json.dumps({"sn": "BT004817", "action": "registered"}).encode()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/internal/inventory/batteries", content=body)

    assert response.status_code == 401
