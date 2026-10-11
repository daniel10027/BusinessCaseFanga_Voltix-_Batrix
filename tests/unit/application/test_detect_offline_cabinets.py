from datetime import UTC, datetime, timedelta

from fanga_ingest.application.use_cases import detect_offline_cabinets
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import CabinetOffline
from tests.unit.application.fake_unit_of_work import FakeUnitOfWork

_T0 = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
_OFFLINE_AFTER = timedelta(seconds=180)


async def test_silent_cabinet_past_the_threshold_is_marked_offline_once() -> None:
    uow = FakeUnitOfWork()
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=_T0, online=True)
    await uow.cabinets.save(cabinet)

    now = _T0 + _OFFLINE_AFTER + timedelta(seconds=1)
    await detect_offline_cabinets(uow, now, _OFFLINE_AFTER)

    reloaded = await uow.cabinets.get("VTX-CAB-0042")
    assert reloaded is not None
    assert reloaded.online is False
    offline_events = [e for e in uow.outbox.published if isinstance(e, CabinetOffline)]
    assert len(offline_events) == 1

    # Un deuxième passage, toujours silencieux : pas de second événement.
    await detect_offline_cabinets(uow, now + timedelta(seconds=30), _OFFLINE_AFTER)
    offline_events = [e for e in uow.outbox.published if isinstance(e, CabinetOffline)]
    assert len(offline_events) == 1


async def test_cabinet_still_within_the_window_is_left_online() -> None:
    uow = FakeUnitOfWork()
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=_T0, online=True)
    await uow.cabinets.save(cabinet)

    now = _T0 + timedelta(seconds=10)
    await detect_offline_cabinets(uow, now, _OFFLINE_AFTER)

    reloaded = await uow.cabinets.get("VTX-CAB-0042")
    assert reloaded is not None
    assert reloaded.online is True
    assert uow.outbox.published == []


async def test_cabinet_never_seen_is_left_alone() -> None:
    uow = FakeUnitOfWork()
    cabinet = Cabinet(cabinet_id="VTX-CAB-0042", last_seen_at=None, online=True)
    await uow.cabinets.save(cabinet)

    await detect_offline_cabinets(uow, _T0, _OFFLINE_AFTER)

    reloaded = await uow.cabinets.get("VTX-CAB-0042")
    assert reloaded is not None
    assert reloaded.online is True
