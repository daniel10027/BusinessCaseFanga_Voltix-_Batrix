"""Value objects communs au domaine.

Toute information consolidée (SOC, localisation, état...) est exposée comme un
`Sourced[T]` : la valeur, accompagnée de la source qui l'a produite et de
l'instant de la mesure. L'API expose ce triplet pour que l'appelant sache
toujours d'où vient chaque donnée (brief, section 5.3 et 5.11).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class Source(StrEnum):
    """Fournisseur à l'origine d'une observation."""

    VOLTIX = "voltix"
    BATRIX = "batrix"


@dataclass(frozen=True)
class Sourced(Generic[T]):
    """Une valeur consolidée, avec la source et l'instant de mesure qui l'ont produite."""

    value: T
    source: Source
    observed_at: datetime
