import time
from datetime import UTC, datetime

from fanga_ingest.clock import replay_clock, system_clock


def test_system_clock_is_close_to_wall_clock() -> None:
    now = system_clock()
    before = datetime.now(UTC)
    value = now()
    after = datetime.now(UTC)

    assert before <= value <= after


def test_replay_clock_starts_at_replay_start() -> None:
    replay_start = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
    now = replay_clock(replay_start)

    value = now()

    assert abs((value - replay_start).total_seconds()) < 0.5


def test_replay_clock_advances_at_the_same_pace_as_real_time() -> None:
    replay_start = datetime(2026, 10, 1, 7, 59, 49, tzinfo=UTC)
    now = replay_clock(replay_start)

    first = now()
    time.sleep(0.2)
    second = now()

    elapsed = (second - first).total_seconds()
    assert 0.15 < elapsed < 1.0
