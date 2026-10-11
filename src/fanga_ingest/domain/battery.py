"""Agrégat Battery : consolide, pour une batterie donnée, les observations
Voltix (cabinet) et Batrix (BMS) selon la politique de vérité (brief, 5.3).

Deux règles cohabitent :

- Localisation : seul le cabinet (Voltix) fait foi. La mesure la plus récente
  gagne, sans compétition entre sources puisqu'il n'y en a qu'une.
- État électrique (SOC, tension, températures) : les deux sources peuvent en
  parler. On compare une clé d'ordre total `(observed_at + 3 min si source
  Batrix, source)` : le BMS gagne sauf si le cabinet est plus récent de plus de
  3 minutes. Cette clé rend le résultat final indépendant de l'ordre
  d'arrivée : on ne fait jamais régresser l'état vers une mesure de clé
  inférieure à celle déjà retenue.

Les champs cycles/état/erreurs ne sont rapportés que par le BMS : il n'y a pas
de compétition, seule la fraîcheur (observed_at) décide.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fanga_ingest.domain.events import (
    BatteryFaulted,
    BatterySocDiscrepancy,
    DomainEvent,
    new_event_id,
)
from fanga_ingest.domain.observations import (
    BatteryStatus,
    SlotObserved,
    SlotState,
    SwapObserved,
    TelemetryObserved,
)
from fanga_ingest.domain.value_objects import Source, Sourced

_BMS_BONUS = timedelta(minutes=3)
_SOC_DISCREPANCY_THRESHOLD_PCT = 5.0
_SOC_DISCREPANCY_WINDOW = timedelta(minutes=3)

_ElectricalKey = tuple[datetime, Source]


class LocationKind:
    IN_CABINET = "in_cabinet"
    OUT_OF_CABINET = "out_of_cabinet"


@dataclass(frozen=True)
class Location:
    kind: str
    cabinet_id: str | None = None
    slot_number: int | None = None


@dataclass
class Battery:
    """Agrégat racine, en mémoire pure : aucune dépendance à une base ou un framework."""

    serial: str
    in_inventory: bool = True

    location: Sourced[Location] | None = None
    soc_pct: Sourced[float] | None = None
    voltage_v: Sourced[float] | None = None
    temperatures_c: Sourced[tuple[float, ...]] | None = None
    cycle_count: Sourced[int] | None = None
    status: Sourced[BatteryStatus] | None = None
    errors: Sourced[tuple[str, ...]] | None = None
    faulted: bool = False

    # --- Curseurs internes, non exposés : ils arbitrent la politique de
    # vérité mais ne font pas partie de l'état consolidé public. ---
    _location_observed_at: datetime | None = field(default=None, repr=False, compare=False)
    _electrical_key: _ElectricalKey | None = field(default=None, repr=False, compare=False)
    _cabinet_observed_at: datetime | None = field(default=None, repr=False, compare=False)
    _cabinet_soc_pct: float | None = field(default=None, repr=False, compare=False)
    _cabinet_faulted: bool = field(default=False, repr=False, compare=False)
    _bms_observed_at: datetime | None = field(default=None, repr=False, compare=False)
    _bms_soc_pct: float | None = field(default=None, repr=False, compare=False)
    _bms_faulted: bool = field(default=False, repr=False, compare=False)
    _discrepancy_checked_pair: tuple[datetime, datetime] | None = field(
        default=None, repr=False, compare=False
    )

    def apply_slot_observed(self, obs: SlotObserved) -> list[DomainEvent]:
        """Le cabinet rapporte l'état d'un casier qui contient cette batterie."""
        events: list[DomainEvent] = []

        if self._location_observed_at is None or obs.observed_at >= self._location_observed_at:
            self._location_observed_at = obs.observed_at
            self.location = Sourced(
                value=Location(LocationKind.IN_CABINET, obs.cabinet_id, obs.slot_number),
                source=obs.source,
                observed_at=obs.observed_at,
            )

        if self._cabinet_observed_at is None or obs.observed_at >= self._cabinet_observed_at:
            self._cabinet_observed_at = obs.observed_at
            self._cabinet_soc_pct = obs.soc_pct
            self._cabinet_faulted = obs.state == SlotState.FAULT
            events += self._recompute_faulted(obs.received_at)

            key = (obs.observed_at, obs.source)
            if self._electrical_key is None or key > self._electrical_key:
                self._electrical_key = key
                self.soc_pct = Sourced(float(obs.soc_pct), obs.source, obs.observed_at)
                self.voltage_v = Sourced(obs.voltage_v, obs.source, obs.observed_at)
                self.temperatures_c = Sourced(
                    (float(obs.temperature_c),), obs.source, obs.observed_at
                )

            events += self._check_soc_discrepancy(obs.received_at)

        return events

    def apply_swap_as_deposit(self, obs: SwapObserved) -> None:
        """Cette batterie vient d'être déposée dans un casier."""
        if self._location_observed_at is None or obs.observed_at >= self._location_observed_at:
            self._location_observed_at = obs.observed_at
            self.location = Sourced(
                value=Location(LocationKind.IN_CABINET, obs.cabinet_id, obs.deposit_slot),
                source=obs.source,
                observed_at=obs.observed_at,
            )

    def apply_swap_as_withdrawal(self, obs: SwapObserved) -> None:
        """Cette batterie vient d'être retirée d'un casier : elle est hors cabinet."""
        if self._location_observed_at is None or obs.observed_at >= self._location_observed_at:
            self._location_observed_at = obs.observed_at
            self.location = Sourced(
                value=Location(LocationKind.OUT_OF_CABINET, obs.cabinet_id, None),
                source=obs.source,
                observed_at=obs.observed_at,
            )

    def apply_telemetry_observed(self, obs: TelemetryObserved) -> list[DomainEvent]:
        """Le BMS publie sa télémétrie."""
        events: list[DomainEvent] = []

        if self._bms_observed_at is not None and obs.observed_at < self._bms_observed_at:
            return events  # message hors d'ordre plus ancien que ce qu'on a déjà : ignoré

        self._bms_observed_at = obs.observed_at
        self._bms_soc_pct = obs.soc_pct
        self._bms_faulted = obs.status == BatteryStatus.ERROR
        self.cycle_count = Sourced(obs.cycle_count, obs.source, obs.observed_at)
        self.status = Sourced(obs.status, obs.source, obs.observed_at)
        self.errors = Sourced(obs.errors, obs.source, obs.observed_at)
        events += self._recompute_faulted(obs.received_at)

        key = (obs.observed_at + _BMS_BONUS, obs.source)
        if self._electrical_key is None or key > self._electrical_key:
            self._electrical_key = key
            self.soc_pct = Sourced(obs.soc_pct, obs.source, obs.observed_at)
            self.voltage_v = Sourced(obs.voltage_v, obs.source, obs.observed_at)
            self.temperatures_c = Sourced(obs.temperatures_c, obs.source, obs.observed_at)

        events += self._check_soc_discrepancy(obs.received_at)
        return events

    def _recompute_faulted(self, occurred_at: datetime) -> list[DomainEvent]:
        was_faulted = self.faulted
        self.faulted = self._cabinet_faulted or self._bms_faulted
        if self.faulted and not was_faulted:
            return [
                BatteryFaulted(
                    event_id=new_event_id(), occurred_at=occurred_at, battery_serial=self.serial
                )
            ]
        return []

    def _check_soc_discrepancy(self, occurred_at: datetime) -> list[DomainEvent]:
        if (
            self._cabinet_observed_at is None
            or self._bms_observed_at is None
            or self._cabinet_soc_pct is None
            or self._bms_soc_pct is None
        ):
            return []

        pair = (self._cabinet_observed_at, self._bms_observed_at)
        if pair == self._discrepancy_checked_pair:
            return []  # déjà vérifiée pour ce couple de mesures exact

        interval = abs(self._cabinet_observed_at - self._bms_observed_at)
        if interval > _SOC_DISCREPANCY_WINDOW:
            return []

        self._discrepancy_checked_pair = pair
        gap = abs(self._cabinet_soc_pct - self._bms_soc_pct)
        if gap <= _SOC_DISCREPANCY_THRESHOLD_PCT:
            return []

        return [
            BatterySocDiscrepancy(
                event_id=new_event_id(),
                occurred_at=occurred_at,
                battery_serial=self.serial,
                cabinet_soc_pct=self._cabinet_soc_pct,
                bms_soc_pct=self._bms_soc_pct,
            )
        ]
