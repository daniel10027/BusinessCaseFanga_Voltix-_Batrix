"""Encodage des événements domaine en dict JSON-sérialisable (brief, 5.7).

Enveloppe commune : `{event_id, type, version, occurred_at, payload}`.
Utilisé à la fois par l'écriture dans l'outbox (persistance) et par le relais
webhook NestJS : les deux ont besoin du même format, c'est pour ça qu'il vit
ici plutôt que dupliqué dans chacun.
"""

from typing import Any

from fanga_ingest.domain.events import (
    BatteryFaulted,
    BatterySocDiscrepancy,
    BatterySwapped,
    BatteryUnknownDetected,
    CabinetOffline,
    CabinetOnline,
    DomainEvent,
)

_EVENT_TYPES: dict[type[DomainEvent], str] = {
    BatterySwapped: "battery.swapped",
    BatteryFaulted: "battery.faulted",
    BatteryUnknownDetected: "battery.unknown_detected",
    BatterySocDiscrepancy: "battery.soc_discrepancy",
    CabinetOffline: "cabinet.offline",
    CabinetOnline: "cabinet.online",
}


def event_type(event: DomainEvent) -> str:
    return _EVENT_TYPES[type(event)]


def event_payload(event: DomainEvent) -> dict[str, Any]:
    if isinstance(event, BatterySwapped):
        return {
            "cabinet_id": event.cabinet_id,
            "deposit_slot": event.deposit_slot,
            "withdrawal_slot": event.withdrawal_slot,
            "deposited_battery_serial": event.deposited_battery_serial,
            "withdrawn_battery_serial": event.withdrawn_battery_serial,
            "received_at": event.received_at.isoformat(),
        }
    if isinstance(event, BatteryFaulted):
        return {"battery_serial": event.battery_serial}
    if isinstance(event, BatteryUnknownDetected):
        return {"battery_serial": event.battery_serial}
    if isinstance(event, BatterySocDiscrepancy):
        return {
            "battery_serial": event.battery_serial,
            "cabinet_soc_pct": event.cabinet_soc_pct,
            "bms_soc_pct": event.bms_soc_pct,
        }
    if isinstance(event, CabinetOffline | CabinetOnline):
        return {"cabinet_id": event.cabinet_id}
    raise TypeError(f"type d'événement non géré : {type(event)!r}")


def event_envelope(event: DomainEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "type": event_type(event),
        "version": 1,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event_payload(event),
    }
