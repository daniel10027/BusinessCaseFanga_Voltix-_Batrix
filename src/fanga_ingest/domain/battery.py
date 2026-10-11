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

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TypeVar

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

T = TypeVar("T")

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
    retired: bool = False

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

    def mark_registered(self) -> None:
        """L'API métier (via NestJS) confirme cette batterie : la quarantaine
        est levée, tout l'historique déjà observé est conservé (brief, 5.9)."""
        self.in_inventory = True

    def mark_retired(self) -> None:
        """L'API métier retire cette batterie du service (brief, 5.9)."""
        self.retired = True

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

    def to_state(self) -> dict[str, Any]:
        """Instantané complet (état public + curseurs internes), pour la
        persistance. Ne renvoie que des types simples (dict/list/str/bool/
        float/None) : c'est la frontière du domaine vers le JSON/JSONB.

        Les curseurs internes sont indispensables : sans eux, recharger la
        batterie puis lui appliquer une nouvelle observation ferait perdre la
        mémoire de ce qui a déjà été vu, et la politique de vérité pourrait
        régresser vers une mesure plus ancienne.
        """
        return {
            "serial": self.serial,
            "in_inventory": self.in_inventory,
            "retired": self.retired,
            "faulted": self.faulted,
            "location": _sourced_to_state(self.location, _location_to_state),
            "soc_pct": _sourced_to_state(self.soc_pct, lambda v: v),
            "voltage_v": _sourced_to_state(self.voltage_v, lambda v: v),
            "temperatures_c": _sourced_to_state(self.temperatures_c, list),
            "cycle_count": _sourced_to_state(self.cycle_count, lambda v: v),
            "status": _sourced_to_state(self.status, lambda v: v.value),
            "errors": _sourced_to_state(self.errors, list),
            "location_observed_at": _dt_to_state(self._location_observed_at),
            "electrical_key": _key_to_state(self._electrical_key),
            "cabinet_observed_at": _dt_to_state(self._cabinet_observed_at),
            "cabinet_soc_pct": self._cabinet_soc_pct,
            "cabinet_faulted": self._cabinet_faulted,
            "bms_observed_at": _dt_to_state(self._bms_observed_at),
            "bms_soc_pct": self._bms_soc_pct,
            "bms_faulted": self._bms_faulted,
            "discrepancy_checked_pair": (
                [_dt_to_state(p) for p in self._discrepancy_checked_pair]
                if self._discrepancy_checked_pair is not None
                else None
            ),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "Battery":
        battery = cls(serial=state["serial"], in_inventory=state["in_inventory"])
        battery.retired = state["retired"]
        battery.faulted = state["faulted"]
        battery.location = _sourced_from_state(state["location"], _location_from_state)
        battery.soc_pct = _sourced_from_state(state["soc_pct"], float)
        battery.voltage_v = _sourced_from_state(state["voltage_v"], float)
        battery.temperatures_c = _sourced_from_state(state["temperatures_c"], lambda v: tuple(v))
        battery.cycle_count = _sourced_from_state(state["cycle_count"], int)
        battery.status = _sourced_from_state(state["status"], BatteryStatus)
        battery.errors = _sourced_from_state(state["errors"], lambda v: tuple(v))

        battery._location_observed_at = _dt_from_state(state["location_observed_at"])
        battery._electrical_key = _key_from_state(state["electrical_key"])
        battery._cabinet_observed_at = _dt_from_state(state["cabinet_observed_at"])
        battery._cabinet_soc_pct = state["cabinet_soc_pct"]
        battery._cabinet_faulted = state["cabinet_faulted"]
        battery._bms_observed_at = _dt_from_state(state["bms_observed_at"])
        battery._bms_soc_pct = state["bms_soc_pct"]
        battery._bms_faulted = state["bms_faulted"]

        pair = state["discrepancy_checked_pair"]
        if pair is not None:
            cabinet_observed_at = _dt_from_state(pair[0])
            bms_observed_at = _dt_from_state(pair[1])
            assert cabinet_observed_at is not None
            assert bms_observed_at is not None
            battery._discrepancy_checked_pair = (cabinet_observed_at, bms_observed_at)
        return battery


def _dt_to_state(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt_from_state(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _key_to_state(key: _ElectricalKey | None) -> list[Any] | None:
    if key is None:
        return None
    observed_at, source = key
    return [observed_at.isoformat(), source.value]


def _key_from_state(data: list[Any] | None) -> _ElectricalKey | None:
    if data is None:
        return None
    observed_at_str, source_str = data
    return (datetime.fromisoformat(observed_at_str), Source(source_str))


def _location_to_state(location: Location) -> dict[str, Any]:
    return {
        "kind": location.kind,
        "cabinet_id": location.cabinet_id,
        "slot_number": location.slot_number,
    }


def _location_from_state(data: dict[str, Any]) -> Location:
    return Location(
        kind=data["kind"], cabinet_id=data["cabinet_id"], slot_number=data["slot_number"]
    )


def _sourced_to_state(
    sourced: Sourced[T] | None, encode_value: Callable[[T], Any]
) -> dict[str, Any] | None:
    if sourced is None:
        return None
    return {
        "value": encode_value(sourced.value),
        "source": sourced.source.value,
        "observed_at": sourced.observed_at.isoformat(),
    }


def _sourced_from_state(
    data: dict[str, Any] | None, decode_value: Callable[[Any], T]
) -> Sourced[T] | None:
    if data is None:
        return None
    return Sourced(
        value=decode_value(data["value"]),
        source=Source(data["source"]),
        observed_at=datetime.fromisoformat(data["observed_at"]),
    )
