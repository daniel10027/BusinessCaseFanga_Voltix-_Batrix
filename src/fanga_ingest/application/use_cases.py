"""Cas d'usage d'ingestion : un par type d'observation (brief, section 5.2).

Chacun suit le même schéma : enregistrer l'observation brute (dédupliquée par
la persistance), charger ou créer les agrégats concernés, leur appliquer
l'observation, publier les événements produits dans l'outbox, valider la
transaction. Rien ici ne connaît FastAPI, SQLAlchemy ou aiomqtt : seulement
les ports de `application.ports`. C'est ce qui permet d'ajouter un nouveau
fournisseur sans toucher à ce fichier : il lui suffit de produire les mêmes
observations canoniques.
"""

from datetime import datetime

from fanga_ingest.application.ports import UnitOfWork
from fanga_ingest.domain.battery import Battery
from fanga_ingest.domain.cabinet import Cabinet
from fanga_ingest.domain.events import BatteryUnknownDetected, DomainEvent, new_event_id
from fanga_ingest.domain.observations import SlotObserved, SwapObserved, TelemetryObserved


async def ingest_slot_observed(uow: UnitOfWork, obs: SlotObserved) -> None:
    async with uow:
        if not await uow.observations.record_slot_observed(obs):
            return  # doublon : aucun effet (5.3)

        cabinet = await _get_or_create_cabinet(uow, obs.cabinet_id)
        await _publish_all(uow, cabinet.apply_slot_observed(obs))

        if obs.battery_serial is not None:
            battery = await _get_or_create_battery(uow, obs.battery_serial, obs.received_at)
            await _publish_all(uow, battery.apply_slot_observed(obs))

        await uow.commit()


async def ingest_swap_observed(uow: UnitOfWork, obs: SwapObserved) -> None:
    async with uow:
        if not await uow.observations.record_swap_observed(obs):
            return

        cabinet = await _get_or_create_cabinet(uow, obs.cabinet_id)
        await _publish_all(uow, cabinet.apply_swap_observed(obs))

        if obs.deposited_battery_serial is not None:
            deposited = await _get_or_create_battery(
                uow, obs.deposited_battery_serial, obs.received_at
            )
            deposited.apply_swap_as_deposit(obs)

        if obs.withdrawn_battery_serial is not None:
            withdrawn = await _get_or_create_battery(
                uow, obs.withdrawn_battery_serial, obs.received_at
            )
            withdrawn.apply_swap_as_withdrawal(obs)

        await uow.commit()


async def ingest_telemetry_observed(uow: UnitOfWork, obs: TelemetryObserved) -> None:
    async with uow:
        if not await uow.observations.record_telemetry_observed(obs):
            return

        battery = await _get_or_create_battery(uow, obs.battery_serial, obs.received_at)
        await _publish_all(uow, battery.apply_telemetry_observed(obs))

        await uow.commit()


async def _get_or_create_cabinet(uow: UnitOfWork, cabinet_id: str) -> Cabinet:
    cabinet = await uow.cabinets.get(cabinet_id)
    if cabinet is not None:
        return cabinet
    cabinet = Cabinet(cabinet_id=cabinet_id)
    await uow.cabinets.add(cabinet)
    return cabinet


async def _get_or_create_battery(uow: UnitOfWork, serial: str, received_at: datetime) -> Battery:
    battery = await uow.batteries.get(serial)
    if battery is not None:
        return battery

    in_inventory = await uow.inventory.contains(serial)
    battery = Battery(serial=serial, in_inventory=in_inventory)
    await uow.batteries.add(battery)
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
