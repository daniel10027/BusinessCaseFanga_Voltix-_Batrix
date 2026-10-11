from datetime import UTC, datetime

import httpx
from fastapi import FastAPI

from fanga_ingest.adapters.api.battery_routes import router
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_T_CABINET = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
_T_BMS = datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC)


def _app(uow: FakeUnitOfWork) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.uow_factory = lambda: uow
    return app


async def test_get_battery_returns_the_document_shape_for_bt004817() -> None:
    uow = FakeUnitOfWork(known_serials=frozenset({"BT004817"}))
    battery = Battery(serial="BT004817")
    battery.apply_slot_observed(
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id="VTX-CAB-0042",
            slot_number=3,
            state=SlotState.FULL,
            battery_serial="BT004817",
            soc_pct=96,
            voltage_v=67.2,
            temperature_c=34,
            observed_at=_T_CABINET,
            received_at=_T_CABINET,
        )
    )
    battery.apply_telemetry_observed(
        TelemetryObserved(
            source=Source.BATRIX,
            battery_serial="BT004817",
            soc_pct=91.8,
            voltage_v=66.95,
            temperatures_c=(33.6, 34.9, 34.1),
            cycle_count=412,
            status=BatteryStatus.DISCHARGING,
            errors=(),
            observed_at=_T_BMS,
            received_at=_T_BMS,
        )
    )
    await uow.batteries.save(battery)

    transport = httpx.ASGITransport(app=_app(uow))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/batteries/BT004817")

    assert response.status_code == 200
    body = response.json()
    assert body["serial"] == "BT004817"
    assert body["soc_pct"] == {
        "value": 91.8,
        "source": "batrix",
        "observed_at": "2026-10-01T08:01:00Z",
    }
    assert body["temperature_max_c"]["value"] == 34.9
    assert body["location"]["kind"] == "in_cabinet"
    assert body["location"]["slot"] == 3
    assert body["in_inventory"] is True
    assert body["faulted"] is False


async def test_get_battery_never_seen_returns_404() -> None:
    uow = FakeUnitOfWork()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/batteries/BT000000")

    assert response.status_code == 404
