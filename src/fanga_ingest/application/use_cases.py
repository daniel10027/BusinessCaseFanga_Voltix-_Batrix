"""Cas d'usage d'ingestion : un par type d'observation (brief, section 5.2).

Chacun suit le même schéma : enregistrer l'observation brute (dédupliquée par
la persistance), charger ou créer les agrégats concernés, leur appliquer
l'observation, les sauvegarder, publier les événements produits dans
l'outbox, valider la transaction. Rien ici ne connaît FastAPI, SQLAlchemy ou
aiomqtt : seulement les ports de `application.ports`. C'est ce qui permet
d'ajouter un nouveau fournisseur sans toucher à ce fichier : il lui suffit de
produire les mêmes observations canoniques.

Important : `save()` est toujours appelé après avoir muté un agrégat, qu'il
soit nouveau ou déjà existant. Avec un vrai dépôt (PostgreSQL), `get()`
désérialise une nouvelle instance à chaque appel : muter l'objet en mémoire
n'a aucun effet sur la base tant que `save()` n'a pas été appelé.
"""

from datetime import datetime
from typing import Literal

from fanga_ingest.application.ports import UnitOfWork
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import BatteryUnknownDetected, DomainEvent, new_event_id
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved

InventoryAction = Literal["registered", "retired"]


async def ingest_slot_observed(uow: UnitOfWork, obs: SlotObserved) -> None:
    async with uow:
        if not await uow.observations.record_slot_observed(obs):
            return  # doublon : aucun effet (5.3)

        cabinet = await _get_or_create_cabinet(uow, obs.cabinet_id)
        events = cabinet.apply_slot_observed(obs)
        await uow.cabinets.save(cabinet)
        await _publish_all(uow, events)

        if obs.battery_serial is not None:
            battery = await _get_or_create_battery(uow, obs.battery_serial, obs.received_at)
            events = battery.apply_slot_observed(obs)
            await uow.batteries.save(battery)
            await _publish_all(uow, events)

        await uow.commit()


async def ingest_swap_observed(uow: UnitOfWork, obs: SwapObserved) -> None:
    async with uow:
        if not await uow.observations.record_swap_observed(obs):
            return

        cabinet = await _get_or_create_cabinet(uow, obs.cabinet_id)
        events = cabinet.apply_swap_observed(obs)
        await uow.cabinets.save(cabinet)
        await _publish_all(uow, events)

        if obs.deposited_battery_serial is not None:
            deposited = await _get_or_create_battery(
                uow, obs.deposited_battery_serial, obs.received_at
            )
            deposited.apply_swap_as_deposit(obs)
            await uow.batteries.save(deposited)

        if obs.withdrawn_battery_serial is not None:
            withdrawn = await _get_or_create_battery(
                uow, obs.withdrawn_battery_serial, obs.received_at
            )
            withdrawn.apply_swap_as_withdrawal(obs)
            await uow.batteries.save(withdrawn)

        await uow.commit()


async def ingest_telemetry_observed(uow: UnitOfWork, obs: TelemetryObserved) -> None:
    async with uow:
        if not await uow.observations.record_telemetry_observed(obs):
            return

        battery = await _get_or_create_battery(uow, obs.battery_serial, obs.received_at)
        events = battery.apply_telemetry_observed(obs)
        await uow.batteries.save(battery)
        await _publish_all(uow, events)

        await uow.commit()


async def sync_inventory_registration(
    uow: UnitOfWork, serial: str, action: InventoryAction
) -> None:
    """L'API métier (via NestJS) confirme ou retire une batterie (brief, 5.9).

    Fonctionne même si la batterie n'a jamais produit la moindre observation :
    c'est ainsi qu'une batterie peut être enregistrée avant sa première
    utilisation.
    """
    async with uow:
        battery = await uow.batteries.get(serial)
        if battery is None:
            battery = Battery(serial=serial, in_inventory=False)

        if action == "registered":
            battery.mark_registered()
        else:
            battery.mark_retired()

        await uow.batteries.save(battery)
        await uow.inventory.set_status(serial, action)
        await uow.commit()


async def _get_or_create_cabinet(uow: UnitOfWork, cabinet_id: str) -> Cabinet:
    cabinet = await uow.cabinets.get(cabinet_id)
    if cabinet is not None:
        return cabinet
    return Cabinet(cabinet_id=cabinet_id)


async def _get_or_create_battery(uow: UnitOfWork, serial: str, received_at: datetime) -> Battery:
    battery = await uow.batteries.get(serial)
    if battery is not None:
        return battery

    in_inventory = await uow.inventory.contains(serial)
    battery = Battery(serial=serial, in_inventory=in_inventory)
    if not in_inventory:
        await uow.outbox.publish(
            BatteryUnknownDetected(
                event_id=new_event_id(),
                occurred_at=received_at,
                battery_serial=serial,
            )
        )
    return battery


async def _publish_all(uow: UnitOfWork, events: list[DomainEvent]) -> None:
    for event in events:
        await uow.outbox.publish(event)
