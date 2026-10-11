"""Configuration : uniquement par variables d'environnement (brief, section 6).

Les valeurs de démo vivent dans `.env.example` ; les vrais secrets vont dans
les secrets GitHub ou le `.env` local (jamais commité).
"""

from datetime import datetime

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")

    voltix_tcp_host: str = Field(default="0.0.0.0", alias="VOLTIX_TCP_HOST")
    voltix_tcp_port: int = Field(default=9000, alias="VOLTIX_TCP_PORT")
    voltix_allowed_cabinet_ids: str = Field(alias="VOLTIX_ALLOWED_CABINET_IDS")
    voltix_read_timeout_seconds: float = Field(default=180.0, alias="VOLTIX_READ_TIMEOUT_SECONDS")
    voltix_max_invalid_frames: int = Field(default=10, alias="VOLTIX_MAX_INVALID_FRAMES")

    mqtt_host: str = Field(default="localhost", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    mqtt_client_id: str = Field(default="fanga-ingest-batrix", alias="MQTT_CLIENT_ID")
    mqtt_topic_filter: str = Field(default="batrix/v1/+/telemetry", alias="MQTT_TOPIC_FILTER")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    cabinet_offline_after_seconds: float = Field(
        default=180.0, alias="CABINET_OFFLINE_AFTER_SECONDS"
    )
    cabinet_sweep_interval_seconds: float = Field(
        default=30.0, alias="CABINET_SWEEP_INTERVAL_SECONDS"
    )

    nestjs_webhook_url: str = Field(
        default="http://localhost:3000/webhooks/fanga", alias="NESTJS_WEBHOOK_URL"
    )
    outbox_hmac_secret: str = Field(alias="OUTBOX_HMAC_SECRET")
    outbox_relay_interval_seconds: float = Field(default=5.0, alias="OUTBOX_RELAY_INTERVAL_SECONDS")

    inventory_hmac_secret: str = Field(alias="INVENTORY_HMAC_SECRET")

    # Laisser vide en production : l'horloge système est alors utilisée (clock.py).
    replay_start: datetime | None = Field(default=None, alias="REPLAY_START")

    @field_validator("replay_start", mode="before")
    @classmethod
    def _blank_string_means_unset(cls, value: object) -> object:
        # `docker compose` substitue ${REPLAY_START:-} par une chaîne vide
        # quand la variable n'est pas définie sur l'hôte, pas par une absence
        # de variable : il faut traiter "" comme None explicitement.
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def voltix_allowed_cabinet_ids_set(self) -> frozenset[str]:
        return frozenset(
            cabinet_id.strip()
            for cabinet_id in self.voltix_allowed_cabinet_ids.split(",")
            if cabinet_id.strip()
        )
