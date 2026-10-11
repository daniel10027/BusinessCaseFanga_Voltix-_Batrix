from datetime import UTC, datetime

import httpx
from fastapi import FastAPI

from fanga_ingest.adapters.api.cabinet_routes import router
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.observations import SlotObserved, SlotState
from fanga_ingest.domain.value_objects import Source
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_T0 = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)


def _app(uow: FakeUnitOfWork) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.uow_factory = lambda: uow
    return app


async def test_get_cabinet_slots_marks_never_reported_slots_as_unknown() -> None:
    uow = FakeUnitOfWork()
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=_T0, online=True)
    cabinet.apply_slot_observed(
        SlotObserved(
            source=Source.VOLTIX,
            cabinet_id="VTX-CAB-0042",
            slot_number=1,
            state=SlotState.CHARGING,
            battery_serial="BT003105",
            soc_pct=58,
            voltage_v=64.1,
            temperature_c=41,
            observed_at=_T0,
            received_at=_T0,
        )
    )
    await uow.cabinets.save(cabinet)

    transport = httpx.ASGITransport(app=_app(uow))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/cabinets/VTX-CAB-0042/slots")

    assert response.status_code == 200
    body = response.json()
    assert body["online"] is True
    slots_by_number = {slot["slot_number"]: slot for slot in body["slots"]}
    assert len(slots_by_number) == 8
    assert slots_by_number[1]["state"] == "charging"
    assert slots_by_number[1]["battery_serial"] == "BT003105"
    assert slots_by_number[2]["state"] == "unknown"
    assert slots_by_number[2]["battery_serial"] is None


async def test_get_cabinet_slots_unknown_cabinet_returns_404() -> None:
    uow = FakeUnitOfWork()
    transport = httpx.ASGITransport(app=_app(uow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/cabinets/UNKNOWN/slots")

    assert response.status_code == 404
