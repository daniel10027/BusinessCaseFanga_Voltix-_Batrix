import json
from datetime import UTC, datetime

from fanga_ingest.adapters.vendors.batrix.consumer import BatrixConsumer
from fanga_ingest.domain.observations import TelemetryObserved
from tests.fixtures.document import BATRIX_MESSAGES

_NOW = datetime(2026, 10, 1, 8, 5, 0, tzinfo=UTC)


def _consumer() -> tuple[BatrixConsumer, list[TelemetryObserved]]:
    received: list[TelemetryObserved] = []

    async def handler(obs: TelemetryObserved) -> None:
        received.append(obs)

    consumer = BatrixConsumer(
        host="localhost",
        port=1883,
        client_id="test",
        topic_filter="batrix/v1/+/telemetry",
        handle_telemetry=handler,
        now=lambda: _NOW,
    )
    return consumer, received


async def test_valid_message_is_translated_and_handed_to_handler() -> None:
    consumer, received = _consumer()
    payload = json.dumps(BATRIX_MESSAGES[0]).encode()

    await consumer.handle_message("batrix/v1/BT004817/telemetry", payload)

    assert len(received) == 1
    assert received[0].battery_serial == "BT004817"
    assert consumer.rejected_count == 0


async def test_invalid_json_is_rejected_and_counted() -> None:
    consumer, received = _consumer()

    await consumer.handle_message("batrix/v1/BT004817/telemetry", b"not json")

    assert received == []
    assert consumer.rejected_count == 1


async def test_message_failing_schema_validation_is_rejected_and_counted() -> None:
    consumer, received = _consumer()
    invalid = {**BATRIX_MESSAGES[0], "soc": 9999}
    payload = json.dumps(invalid).encode()

    await consumer.handle_message("batrix/v1/BT004817/telemetry", payload)

    assert received == []
    assert consumer.rejected_count == 1


async def test_topic_serial_mismatching_payload_serial_is_rejected() -> None:
    consumer, received = _consumer()
    payload = json.dumps(BATRIX_MESSAGES[0]).encode()  # sn = BT004817

    await consumer.handle_message("batrix/v1/BT999999/telemetry", payload)

    assert received == []
    assert consumer.rejected_count == 1


async def test_malformed_topic_is_rejected() -> None:
    consumer, received = _consumer()
    payload = json.dumps(BATRIX_MESSAGES[0]).encode()

    await consumer.handle_message("unexpected/topic", payload)

    assert received == []
    assert consumer.rejected_count == 1


async def test_all_document_messages_are_accepted_through_their_own_topics() -> None:
    consumer, received = _consumer()

    for raw in BATRIX_MESSAGES:
        payload = json.dumps(raw).encode()
        await consumer.handle_message(f"batrix/v1/{raw['sn']}/telemetry", payload)

    assert len(received) == len(BATRIX_MESSAGES)
    assert consumer.rejected_count == 0
