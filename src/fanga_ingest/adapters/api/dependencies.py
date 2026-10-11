"""Dépendances FastAPI : lisent la configuration posée sur `app.state` par le
composition root (`main.py`, dernière étape de la phase 4).

Garder ces lectures dans des fonctions dédiées (plutôt que d'accéder à
`request.app.state` directement dans chaque route) permet de les remplacer
facilement dans les tests, via `app.dependency_overrides`.
"""

from collections.abc import Callable

from fastapi import Request

from fanga_ingest.application.ports import UnitOfWork


def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]:
    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory


def get_inventory_hmac_secret(request: Request) -> str:
    secret: str = request.app.state.inventory_hmac_secret
    return secret
