from datetime import UTC, datetime

from fanga_ingest.adapters.vendors.batrix.schema import TelemetryMessage
from fanga_ingest.adapters.vendors.batrix.translate import translate_telemetry
from fanga_ingest.domain.observations import BatteryStatus
from fanga_ingest.domain.value_objects import Source
from tests.fixtures.document import BATRIX_MESSAGES

_RECEIVED_AT = datetime(2026, 10, 1, 8, 5, 0, tzinfo=UTC)


def test_translate_bt004817_first_message() -> None:
    message = TelemetryMessage.model_validate(BATRIX_MESSAGES[0])

    obs = translate_telemetry(message, _RECEIVED_AT)

    assert obs.source == Source.BATRIX
    assert obs.battery_serial == "BT004817"
    assert obs.soc_pct == 92.0
    assert obs.voltage_v == 67.18
    assert obs.temperatures_c == (33.1, 34.5, 33.8)
    assert obs.cycle_count == 412
    assert obs.status == BatteryStatus.CHARGING
    assert obs.errors == ()
    assert obs.observed_at == datetime(2026, 10, 1, 7, 59, 0, tzinfo=UTC)
    assert obs.received_at == _RECEIVED_AT


def test_translate_bt002290_with_negative_temperatures_and_error() -> None:
    message = TelemetryMessage.model_validate(BATRIX_MESSAGES[1])

    obs = translate_telemetry(message, _RECEIVED_AT)

    assert obs.battery_serial == "BT002290"
    assert obs.soc_pct == 41.0
    assert obs.voltage_v == 59.79
    assert obs.temperatures_c == (-3.0, -2.8, -3.1)
    assert obs.status == BatteryStatus.ERROR
    assert obs.errors == ("CELL_UNDERTEMP",)


def test_translate_bt009999_idle_at_full_charge() -> None:
    message = TelemetryMessage.model_validate(BATRIX_MESSAGES[5])

    obs = translate_telemetry(message, _RECEIVED_AT)

    assert obs.battery_serial == "BT009999"
    assert obs.soc_pct == 100.0
    assert obs.status == BatteryStatus.IDLE
