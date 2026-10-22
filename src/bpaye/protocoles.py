"""Ce que les rubriques demandent d'un agent ou d'un bulletin, pour les annoter.

hsa, point, reclassement, colles et charges_impots prennent un Fonctionnaire ou un
Bulletin, mais fonctionnaire.py et paye.py les importent : les importer en retour ferait
un cycle, et une annotation s'évalue à la définition de la fonction. Ces protocoles
décrivent ce dont elles se servent ; Fonctionnaire et Bulletin les remplissent sans les
nommer, et mypy le vérifie à chaque appel.
"""

import datetime as dt
from typing import Protocol

from bpaye.classes import Ligne, Temporal
from bpaye.grille import Grille

__all__ = [
    "Agent",
    "BulletinMois",
]


class Agent(Protocol):
    """La carrière d'un agent (Fonctionnaire), telle que la lisent les rubriques."""

    @property
    def corps(self) -> Temporal[str]: ...

    @property
    def cpge(self) -> Temporal[bool]: ...

    @property
    def grille(self) -> Temporal[Grille]: ...

    @property
    def ors(self) -> Temporal[int]: ...

    @property
    def vs(self) -> Temporal[float]: ...

    @property
    def echelon(self) -> Temporal[int]: ...

    @property
    def anciennete(self) -> Temporal[float]: ...

    @property
    def noms_grille(self) -> Temporal[str]: ...

    @property
    def nbi(self) -> Temporal[int]: ...

    def indice(self, date: dt.date) -> float: ...

    def indice_detenu(self, date: dt.date) -> int: ...

    def corps_au(self, date: dt.date) -> str: ...

    def en_cpge(self, date: dt.date) -> bool: ...

    def points_nbi(self, date: dt.date) -> int: ...

    def quotite_au(self, date: dt.date) -> float: ...

    def changement_d_indice(self, date: dt.date) -> tuple[int, int, int] | None: ...

    def fraction(self, date: dt.date) -> float: ...

    def au_prorata(self, montant: float, date: dt.date) -> float: ...

    def reclasse(self, date: dt.date, echelon: int, anciennete: float) -> None: ...


class BulletinMois(Protocol):
    """Le bulletin d'un mois (Bulletin), tel que le lisent les colles et le plafond
    d'exonération des heures supplémentaires."""

    @property
    def date(self) -> dt.date: ...

    @property
    def hs_brut(self) -> float: ...

    def append(self, ligne: Ligne | None, recalc: bool = False, newcharge: bool = False) -> None: ...

    def generate_charges(self) -> None: ...
