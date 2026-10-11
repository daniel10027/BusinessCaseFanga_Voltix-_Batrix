"""Agrégat Cabinet : les 8 casiers d'un cabinet Voltix et leur dernière valeur connue.

Politique de vérité (brief, 5.3) : seul le cabinet rapporte l'état des
casiers, donc pas de compétition entre sources ici — la mesure la plus
récente (`observed_at`) gagne, par casier. Un casier jamais signalé reste à
`None` (« unknown », jamais « vide » par défaut, cf. 5.11).

Un SWAP_EVENT met le casier de dépôt en `OCCUPIED` (on sait qu'une batterie
est là, mais pas encore dans quel état précis) et le casier de retrait en
`EMPTY`. Un swap partiel (casier 0) ne touche pas ce côté-là.
"""

from dataclasses import dataclass, field
from datetime import datetime

from fanga_ingest.domain.events import BatterySwapped, DomainEvent, new_event_id
from fanga_ingest.domain.observations import SlotObserved, SlotState, SwapObserved

SLOT_NUMBERS = range(1, 9)


@dataclass(frozen=True)
class Slot:
    state: SlotState | None = None
    battery_serial: str | None = None
    observed_at: datetime | None = None


@dataclass
class Cabinet:
    cabinet_id: str
    slots: dict[int, Slot] = field(default_factory=lambda: {n: Slot() for n in SLOT_NUMBERS})
    last_seen_at: datetime | None = None
    online: bool = True

    def apply_slot_observed(self, obs: SlotObserved) -> list[DomainEvent]:
        self.last_seen_at = obs.received_at
        if not self._is_newer(obs.slot_number, obs.observed_at):
            return []
        self.slots[obs.slot_number] = Slot(
            state=obs.state,
            battery_serial=obs.battery_serial,
            observed_at=obs.observed_at,
        )
        return []

    def apply_swap_observed(self, obs: SwapObserved) -> list[DomainEvent]:
        self.last_seen_at = obs.received_at

        if obs.deposit_slot != 0 and self._is_newer(obs.deposit_slot, obs.observed_at):
            self.slots[obs.deposit_slot] = Slot(
                state=SlotState.OCCUPIED,
                battery_serial=obs.deposited_battery_serial,
                observed_at=obs.observed_at,
            )

        if obs.withdrawal_slot != 0 and self._is_newer(obs.withdrawal_slot, obs.observed_at):
            self.slots[obs.withdrawal_slot] = Slot(
                state=SlotState.EMPTY,
                battery_serial=None,
                observed_at=obs.observed_at,
            )

        return [
            BatterySwapped(
                event_id=new_event_id(),
                occurred_at=obs.received_at,
                cabinet_id=obs.cabinet_id,
                deposit_slot=obs.deposit_slot,
                withdrawal_slot=obs.withdrawal_slot,
                deposited_battery_serial=obs.deposited_battery_serial,
                withdrawn_battery_serial=obs.withdrawn_battery_serial,
                received_at=obs.received_at,
            )
        ]

    def _is_newer(self, slot_number: int, observed_at: datetime) -> bool:
        current = self.slots.get(slot_number, Slot())
        return current.observed_at is None or observed_at >= current.observed_at
