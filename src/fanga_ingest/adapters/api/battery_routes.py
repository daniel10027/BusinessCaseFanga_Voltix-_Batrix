"""GET /batteries/{sn} : état consolidé d'une batterie (brief, 5.11)."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from fanga_ingest.adapters.api.dependencies import get_uow_factory
from fanga_ingest.adapters.api.serializers import battery_to_json
from fanga_ingest.application.ports import UnitOfWork

router = APIRouter()


@router.get("/batteries/{sn}")
async def get_battery(
    sn: str, uow_factory: Callable[[], UnitOfWork] = Depends(get_uow_factory)
) -> dict[str, Any]:
    async with uow_factory() as uow:
        battery = await uow.batteries.get(sn)

    if battery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batterie inconnue")
    return battery_to_json(battery)
