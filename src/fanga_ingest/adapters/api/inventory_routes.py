"""POST /internal/inventory/batteries : synchronisation depuis l'API métier
Fanga (brief, 5.9). L'API métier fait référence pour l'inventaire : une
batterie jamais vue est mise en quarantaine jusqu'à ce que NestJS confirme
son enregistrement par cet appel.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from fanga_ingest.adapters.api.dependencies import get_inventory_hmac_secret, get_uow_factory
from fanga_ingest.adapters.api.security import SIGNATURE_HEADER, verify_signature
from fanga_ingest.application.ports import UnitOfWork
from fanga_ingest.application.use_cases import InventoryAction, sync_inventory_registration

router = APIRouter()


class InventorySyncRequest(BaseModel):
    sn: str
    action: InventoryAction


@router.post("/internal/inventory/batteries", status_code=status.HTTP_204_NO_CONTENT)
async def sync_inventory_battery(
    request: Request,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_uow_factory),
    hmac_secret: str = Depends(get_inventory_hmac_secret),
) -> None:
    body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    if not verify_signature(hmac_secret, body, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signature invalide")

    payload = InventorySyncRequest.model_validate_json(body)
    await sync_inventory_registration(uow_factory(), payload.sn, payload.action)
