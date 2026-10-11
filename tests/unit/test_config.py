from fanga_ingest.config import Settings


def test_settings_reads_required_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fanga:fanga@localhost:5432/fanga_ingest"
    )
    monkeypatch.setenv("VOLTIX_ALLOWED_CABINET_IDS", "VTX-CAB-0042, VTX-CAB-0043")
    monkeypatch.setenv("OUTBOX_HMAC_SECRET", "outbox-secret")
    monkeypatch.setenv("INVENTORY_HMAC_SECRET", "inventory-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url.endswith("/fanga_ingest")
    assert settings.voltix_allowed_cabinet_ids_set == {"VTX-CAB-0042", "VTX-CAB-0043"}
    assert settings.voltix_tcp_port == 9000
    assert settings.cabinet_offline_after_seconds == 180.0
    assert settings.replay_start is None


def test_settings_parses_replay_start(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fanga:fanga@localhost:5432/fanga_ingest"
    )
    monkeypatch.setenv("VOLTIX_ALLOWED_CABINET_IDS", "VTX-CAB-0042")
    monkeypatch.setenv("OUTBOX_HMAC_SECRET", "outbox-secret")
    monkeypatch.setenv("INVENTORY_HMAC_SECRET", "inventory-secret")
    monkeypatch.setenv("REPLAY_START", "2026-10-01T07:59:49Z")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.replay_start is not None
    assert settings.replay_start.year == 2026
    assert settings.replay_start.hour == 7
