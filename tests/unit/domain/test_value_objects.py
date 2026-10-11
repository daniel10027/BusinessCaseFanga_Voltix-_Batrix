from datetime import UTC, datetime

from fanga_ingest.domain.value_objects import Source, Sourced


def test_sourced_is_immutable_and_carries_its_provenance() -> None:
    observed_at = datetime(2026, 10, 1, 8, 1, 0, tzinfo=UTC)
    soc = Sourced(value=91.8, source=Source.BATRIX, observed_at=observed_at)

    assert soc.value == 91.8
    assert soc.source == Source.BATRIX
    assert soc.observed_at == observed_at


def test_source_values_match_vendor_names() -> None:
    assert Source.VOLTIX == "voltix"
    assert Source.BATRIX == "batrix"
