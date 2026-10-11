"""Schéma Pydantic strict pour la télémétrie Batrix, publiée en JSON sur
`batrix/v1/{numero_serie}/telemetry` (brief, section « Télémétrie batteries »).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WireBatteryStatus(StrEnum):
    """Valeurs du champ `st`."""

    CHARGING = "CHG"
    DISCHARGING = "DSG"
    IDLE = "IDLE"
    ERROR = "ERR"


class TelemetryMessage(BaseModel):
    # "forbid" : un champ en trop dans le message est aussi une anomalie à
    # rejeter, pas seulement un champ manquant ou mal typé.
    model_config = ConfigDict(extra="forbid")

    sn: str = Field(pattern=r"^[A-Z0-9]{8}$")
    ts: int = Field(gt=0)  # millisecondes depuis 1970, UTC
    soc: int = Field(ge=0, le=1000)  # pour mille
    v: int = Field(gt=0)  # millivolts
    t: list[int] = Field(min_length=1)  # 0,1 °C, une valeur par sonde
    cyc: int = Field(ge=0)
    st: WireBatteryStatus
    err: list[str] | None = None
