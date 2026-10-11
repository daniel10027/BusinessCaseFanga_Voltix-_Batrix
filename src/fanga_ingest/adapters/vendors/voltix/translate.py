"""Traduction anti-corruption : messages Voltix décodés → observations canoniques.

Seul endroit qui connaît à la fois le vocabulaire Voltix (ses propres énumérations
et unités) et celui du domaine. Rien ici n'est appelé en dehors de `session.py`.
"""

import logging
from datetime import UTC, datetime, timedelta

from fanga_ingest.adapters.vendors.voltix import messages as voltix
from fanga_ingest.domain import observations as domain
from fanga_ingest.domain.value_objects import Source

logger = logging.getLogger(__name__)

# Hypothèse 5.12 : l'horloge du cabinet est en secondes Unix UTC, mais elle
# peut dériver. On ne lui fait confiance que si elle reste à moins de 5 min de
# l'heure serveur ; sinon on retient l'heure serveur et on logue la dérive.
_CLOCK_DRIFT_TOLERANCE = timedelta(minutes=5)

_SLOT_STATE_MAP: dict[voltix.SlotState, domain.SlotState] = {
    voltix.SlotState.EMPTY: domain.SlotState.EMPTY,
    voltix.SlotState.CHARGING: domain.SlotState.CHARGING,
    voltix.SlotState.FULL: domain.SlotState.FULL,
    voltix.SlotState.FAULT: domain.SlotState.FAULT,
}


def translate_slot_status(
    cabinet_id: str, message: voltix.SlotStatusMessage, received_at: datetime
) -> domain.SlotObserved:
    """SLOT_STATUS ne porte pas d'horodatage propre : on date à réception (5.12)."""
    return domain.SlotObserved(
        source=Source.VOLTIX,
        cabinet_id=cabinet_id,
        slot_number=message.slot_number,
        state=_SLOT_STATE_MAP[message.state],
        battery_serial=message.battery_serial,
        soc_pct=message.soc_pct,
        voltage_v=message.voltage_v,
        temperature_c=message.temperature_c,
        observed_at=received_at,
        received_at=received_at,
    )


def translate_swap_event(
    cabinet_id: str, message: voltix.SwapEventMessage, received_at: datetime
) -> domain.SwapObserved:
    cabinet_time = datetime.fromtimestamp(message.cabinet_clock_epoch_s, tz=UTC)
    drift = abs(cabinet_time - received_at)
    if drift <= _CLOCK_DRIFT_TOLERANCE:
        observed_at = cabinet_time
    else:
        logger.warning(
            "dérive d'horloge cabinet_id=%s drift=%s : heure serveur retenue",
            cabinet_id,
            drift,
        )
        observed_at = received_at

    return domain.SwapObserved(
        source=Source.VOLTIX,
        cabinet_id=cabinet_id,
        deposit_slot=message.deposit_slot,
        withdrawal_slot=message.withdrawal_slot,
        deposited_battery_serial=message.deposited_battery_serial,
        withdrawn_battery_serial=message.withdrawn_battery_serial,
        observed_at=observed_at,
        received_at=received_at,
    )
