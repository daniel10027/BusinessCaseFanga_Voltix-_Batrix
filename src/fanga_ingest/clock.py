"""Horloge injectable : l'heure réelle en production, décalée pour la démo.

Aucun adaptateur (session Voltix, consommateur Batrix, relais outbox,
superviseur de cabinets) n'appelle `datetime.now()` directement : ils
reçoivent tous une fonction `now: Callable[[], datetime]`. C'est ce qui
permet de rejouer les données du document (horodatées le 1er octobre 2026)
sans mélanger deux horloges — le piège qui a faussé un prototype précédent
(SOC affiché à 96 % au lieu de 91,8 %, swap rejeté comme dérive d'horloge ;
voir le brief, section 7).
"""

from collections.abc import Callable
from datetime import UTC, datetime


def system_clock() -> Callable[[], datetime]:
    """L'horloge réelle, pour la production."""

    def now() -> datetime:
        return datetime.now(UTC)

    return now


def replay_clock(replay_start: datetime) -> Callable[[], datetime]:
    """Démarre à `replay_start` à l'instant de l'appel, puis avance au même
    rythme que l'horloge réelle (« REPLAY_START démarre au lancement du
    service », brief section 7) : les délais (timeout, intervalle de
    supervision...) se comportent normalement, seule l'origine est décalée.
    """
    process_started_at = datetime.now(UTC)

    def now() -> datetime:
        elapsed = datetime.now(UTC) - process_started_at
        return replay_start + elapsed

    return now
