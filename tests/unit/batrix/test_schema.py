import pytest
from pydantic import ValidationError

from fanga_ingest.adapters.vendors.batrix.schema import TelemetryMessage
from tests.fixtures.document import BATRIX_MESSAGES


@pytest.mark.parametrize("raw", BATRIX_MESSAGES)
def test_all_document_messages_are_valid(raw: dict) -> None:
    TelemetryMessage.model_validate(raw)


def test_err_is_optional() -> None:
    message = TelemetryMessage.model_validate(
        {"sn": "BT004817", "ts": 1, "soc": 500, "v": 60000, "t": [300], "cyc": 1, "st": "IDLE"}
    )
    assert message.err is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"sn": "bt004817"},  # minuscules
        {"sn": "BT0048"},  # trop court
        {"soc": -1},
        {"soc": 1001},
        {"t": []},  # liste vide
        {"st": "UNKNOWN"},
        {"extra_field": "nope"},
    ],
)
def test_invalid_messages_are_rejected(overrides: dict) -> None:
    base = {"sn": "BT004817", "ts": 1, "soc": 500, "v": 60000, "t": [300], "cyc": 1, "st": "IDLE"}
    base.update(overrides)

    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(base)
