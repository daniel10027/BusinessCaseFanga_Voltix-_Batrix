from datetime import UTC, datetime, timedelta

from fanga_ingest.adapters.supervision import OfflineCabinetSupervisor
from fanga_ingest.domain.cabinet import Cabinet
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)


async def test_sweep_once_marks_a_silent_cabinet_offline() -> None:
    uow = FakeUnitOfWork()
    await uow.cabinets.save(Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=_T0, online=True))
    now = _T0 + timedelta(minutes=10)

    supervisor = OfflineCabinetSupervisor(
        uow_factory=lambda: uow,
        now=lambda: now,
        offline_after=timedelta(seconds=180),
        sweep_interval_seconds=30,
    )
    await supervisor.sweep_once()

    reloaded = await uow.cabinets.get("VTX-CAB-0042")
    assert reloaded is not None
    assert reloaded.online is False
