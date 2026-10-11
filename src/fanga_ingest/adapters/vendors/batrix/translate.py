"""Traduction anti-corruption : message Batrix validé → observation canonique.

Conversions d'unités (brief) : `soc` est en pour mille → on divise par 10 pour
obtenir un pourcentage ; `v` est en millivolts → on divise par 1000 pour des
volts ; chaque valeur de `t` est en 0,1 °C → on divise par 10.
"""

from datetime import UTC, datetime

from fanga_ingest.adapters.vendors.batrix.schema import TelemetryMessage, WireBatteryStatus
from fanga_ingest.domain.observations import BatteryStatus, TelemetryObserved
from fanga_ingest.domain.value_objects import Source

_STATUS_MAP: dict[WireBatteryStatus, BatteryStatus] = {
    WireBatteryStatus.CHARGING: BatteryStatus.CHARGING,
    WireBatteryStatus.DISCHARGING: BatteryStatus.DISCHARGING,
    WireBatteryStatus.IDLE: BatteryStatus.IDLE,
    WireBatteryStatus.ERROR: BatteryStatus.ERROR,
}


def translate_telemetry(message: TelemetryMessage, received_at: datetime) -> TelemetryObserved:
    return TelemetryObserved(
        source=Source.BATRIX,
        battery_serial=message.sn,
        soc_pct=message.soc / 10,
        voltage_v=message.v / 1000,
        temperatures_c=tuple(value / 10 for value in message.t),
        cycle_count=message.cyc,
        status=_STATUS_MAP[message.st],
        errors=tuple(message.err or ()),
        observed_at=datetime.fromtimestamp(message.ts / 1000, tz=UTC),
        received_at=received_at,
    )
