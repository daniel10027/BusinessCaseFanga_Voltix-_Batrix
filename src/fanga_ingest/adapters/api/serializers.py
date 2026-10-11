"""Mise en forme JSON des agrégats domaine pour l'API (brief, 5.11).

Chaque valeur consolidée est exposée comme `{value, source, observed_at}` :
l'appelant sait toujours d'où vient chaque information. `updated_at` est
calculé (le plus récent `observed_at` parmi les champs renseignés), pas
stocké : la batterie n'a pas de curseur de fraîcheur global dédié.
"""

from datetime import datetime
from typing import Any

from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.value_objects import Sourced


def _format_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sourced_json(sourced: Sourced[Any] | None) -> dict[str, Any] | None:
    if sourced is None:
        return None
    value = sourced.value
    if isinstance(value, tuple):
        value = list(value)
    return {
        "value": value,
        "source": sourced.source.value,
        "observed_at": _format_datetime(sourced.observed_at),
    }


def battery_to_json(battery: Battery) -> dict[str, Any]:
    location_json: dict[str, Any] | None = None
    if battery.location is not None:
        location_json = {
            "kind": battery.location.value.kind,
            "cabinet_id": battery.location.value.cabinet_id,
            "slot": battery.location.value.slot_number,
            "source": battery.location.source.value,
            "observed_at": _format_datetime(battery.location.observed_at),
        }

    temperature_max_json: dict[str, Any] | None = None
    if battery.temperatures_c is not None:
        temperature_max_json = {
            "value": max(battery.temperatures_c.value),
            "source": battery.temperatures_c.source.value,
            "observed_at": _format_datetime(battery.temperatures_c.observed_at),
        }

    observed_ats = [
        sourced.observed_at
        for sourced in (
            battery.location,
            battery.soc_pct,
            battery.voltage_v,
            battery.temperatures_c,
            battery.cycle_count,
            battery.status,
            battery.errors,
        )
        if sourced is not None
    ]

    return {
        "serial": battery.serial,
        "location": location_json,
        "soc_pct": _sourced_json(battery.soc_pct),
        "voltage_v": _sourced_json(battery.voltage_v),
        "temperatures_c": _sourced_json(battery.temperatures_c),
        "temperature_max_c": temperature_max_json,
        "cycle_count": _sourced_json(battery.cycle_count),
        "status": _sourced_json(battery.status),
        "errors": _sourced_json(battery.errors),
        "faulted": battery.faulted,
        "in_inventory": battery.in_inventory,
        "retired": battery.retired,
        "updated_at": _format_datetime(max(observed_ats)) if observed_ats else None,
    }


def cabinet_slots_to_json(cabinet: Cabinet) -> dict[str, Any]:
    return {
        "cabinet_id": cabinet.cabinet_id,
        "online": cabinet.online,
        "last_seen_at": _format_datetime(cabinet.last_seen_at)
        if cabinet.last_seen_at is not None
        else None,
        "slots": [
            {
                "slot_number": number,
                "state": slot.state.value if slot.state is not None else "unknown",
                "battery_serial": slot.battery_serial,
                "observed_at": _format_datetime(slot.observed_at)
                if slot.observed_at is not None
                else None,
            }
            for number, slot in sorted(cabinet.slots.items())
        ],
    }
