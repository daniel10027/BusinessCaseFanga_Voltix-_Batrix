"""GET /cabinets/{id}/slots : état des 8 casiers d'un cabinet (brief, 5.11)."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from fanga_ingest.adapters.api.dependencies import get_uow_factory
from fanga_ingest.adapters.api.serializers import cabinet_slots_to_json
from fanga_ingest.application.ports import UnitOfWork

router = APIRouter()


@router.get("/cabinets/{cabinet_id}/slots")
async def get_cabinet_slots(
    cabinet_id: str, uow_factory: Callable[[], UnitOfWork] = Depends(get_uow_factory)
) -> dict[str, Any]:
    async with uow_factory() as uow:
        cabinet = await uow.cabinets.get(cabinet_id)

    if cabinet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cabinet inconnu")
    return cabinet_slots_to_json(cabinet)
