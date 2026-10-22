"""Retraite additionnelle de la fonction publique (501080), sur les primes et indemnités.

L'assiette est plafonnée à 20 % du traitement indiciaire brut, cumulé sur l'année
civile : chaque mois cotise sur le cumul des primes dans la limite du cumul des
plafonds, moins ce qui a déjà cotisé. Un bulletin qui change fait donc recalculer
les suivants de l'année ; RAFP garde l'année en mémoire pour cela.

La cotisation cumulée de l'année est tronquée au centime, et le mois prélève ce qui s'y
ajoute : la cotisation d'un mois varie d'un centime (39,62 € en janvier et juillet, 39,63 €
les autres mois, sur une assiette de 792,568 € par mois). Aucun texte lu ne fixe l'arrondi
(MANQUANT) ; cette règle retrouve tous les mois des années 2020, 2022, 2024 et 2025, quand
un arrondi de la cotisation de chaque mois en manquait jusqu'à quatre par an.
"""

import datetime as dt
import logging
from dataclasses import dataclass, field

from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme
from bpaye.utils import truncate

__all__ = [
    "RAFP",
]


_log = logging.getLogger(__name__)


@dataclass
class _RAFPEntry:
    date: dt.date
    prime: float
    plafond: float
    taux: float
    assiette: float = 0.0
    ligne: Ligne | None = field(default=None, repr=False)


class RAFP:
    """Calcul cumulatif de la cotisation RAFP mois par mois."""

    def __init__(self, bareme: Bareme = BAREME):
        self._taux = bareme.load("rafp")
        self._plafond_pct: float = bareme.get("rafp.plafond_pct.valeur")
        self._entries: list[_RAFPEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    def _find(self, date: dt.date) -> int:
        """Retourne l'indice de l'entrée pour `date`, ou -1 si absente."""
        for i, e in enumerate(self._entries):
            if e.date == date:
                return i
        return -1

    def _update_from(self, start: int) -> None:
        """Recalcule l'année civile de l'entrée `start`, à partir de son premier mois.

        Sur l'année, l'assiette cumulée est le plus petit du cumul des primes et du cumul
        des plafonds ; chaque mois cotise sur ce qui s'y ajoute. Les entrées restent triées
        par date : un bulletin d'une autre année, calculé après, ne se mêle pas au cumul.
        """
        annee = self._entries[start].date.year
        plafond = primes = assiette = exacte = cotise = 0.0
        for e in self._entries:
            if e.date.year != annee:
                continue
            plafond += e.plafond
            primes += e.prime
            e.assiette = min(plafond, primes) - assiette
            assiette += e.assiette
            exacte += e.taux * e.assiette  # la cotisation cumulée, avant troncature
            val = round(truncate(exacte, 2) - cotise, 2)
            cotise = round(cotise + val, 2)
            if e.ligne is None:
                e.ligne = Ligne(-val, "RAFP", code=501080, classe="RAFP")
            else:
                e.ligne.valeur = -val
            _log.debug("rafp %s  assiette=%.2f  val=%.2f", e.date, e.assiette, val)

    def __call__(self, date: dt.date, brut: float, primes: float) -> Ligne:
        i = self._find(date)
        if i == -1:
            entry = _RAFPEntry(
                date=date,
                prime=primes,
                plafond=self._plafond_pct * brut,
                taux=self._taux(date),
            )
            self._entries.append(entry)
            self._entries.sort(key=lambda e: e.date)
            i = self._find(date)
        else:
            self._entries[i].prime = primes
            self._entries[i].plafond = self._plafond_pct * brut
        self._update_from(i)
        result = self._entries[self._find(date)].ligne
        assert result is not None
        return result
