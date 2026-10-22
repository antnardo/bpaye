"""Reclassements : quand un statut renumérote ses échelons à une date donnée.

Le PPCR (1er septembre 2017) a raccourci les grilles et changé les durées d'échelon ;
le décret 2023-720 (6 août 2023) a fait de l'échelon spécial un échelon ordinaire.
Chaque fois, un tableau du décret dit, échelon par échelon, où arrive l'agent et ce
que devient son ancienneté. Ces tableaux sont des données (reclassements.toml, une
entrée par grille et par date, avec le texte qui la fixe), pas du code : un tableau
nouveau s'ajoute sans toucher au calcul.

L'ancienneté conservée l'est « dans la limite de la durée de l'échelon » d'arrivée :
celle qui l'atteint fait passer à l'échelon suivant le jour même, sans reliquat.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from bpaye.protocoles import Agent
from bpaye.utils import date_de, lit_toml

__all__ = [
    "DATE_PPCR",
    "RECLASSEMENTS",
    "Correspondance",
    "Reclassement",
    "anciennete_au",
    "charge_reclassements",
    "reclasse",
]

_TOML = Path(__file__).parent / "reclassements.toml"

# Le reclassement du PPCR, que carriere.toml demande par { type = "PPCR" }.
DATE_PPCR = dt.date(2017, 9, 1)

# Ce que devient l'ancienneté détenue dans l'ancien échelon.
CONSERVEE = "conservee"
NEANT = "neant"


@dataclass(frozen=True, slots=True)
class Correspondance:
    """Une ligne d'un tableau de reclassement."""

    ancien: int
    nouveau: int
    anciennete: str = CONSERVEE  # CONSERVEE ou NEANT
    majoration: float = 0.0  # en années, ajoutée à l'ancienneté conservée


@dataclass(frozen=True, slots=True)
class Reclassement:
    """Le tableau d'une grille à une date, avec le texte qui le fixe."""

    date: dt.date
    source: str
    table: dict[int, Correspondance]


def charge_reclassements(path: Path = _TOML) -> dict[str, list[Reclassement]]:
    """Par nom de grille (GRILLE_AGCN…), ses reclassements dans l'ordre des dates."""
    cfg = lit_toml(path)
    resultat: dict[str, list[Reclassement]] = {}
    for nom, entrees in cfg.items():
        for entree in entrees:
            table: dict[int, Correspondance] = {}
            for ligne in entree["table"]:
                regle = ligne.get("anciennete", CONSERVEE)
                if regle not in (CONSERVEE, NEANT):
                    raise ValueError(f"{nom} : règle d'ancienneté inconnue {regle!r}")
                c = Correspondance(ligne["ancien"], ligne["nouveau"], regle, ligne.get("majoration", 0.0))
                table[c.ancien] = c
            resultat.setdefault(nom, []).append(Reclassement(date_de(entree), entree["source"], table))
        resultat[nom].sort(key=lambda r: r.date)
    return resultat


RECLASSEMENTS = charge_reclassements()


def anciennete_au(fonc: Agent, jour: dt.date) -> float:
    """L'ancienneté dans l'échelon détenu le ``jour``, en années."""
    entree = fonc.echelon.date(jour)
    return fonc.anciennete(jour) + (jour - entree).days / 365


def reclasse(fonc: Agent, jour: dt.date, nom_grille: str | None = None) -> None:
    """Reclasse ``fonc`` le ``jour`` d'après le tableau de sa grille à cette date.

    Sans tableau pour sa grille ce jour-là, lève ValueError : un reclassement qu'on ne
    sait pas faire ne doit pas passer inaperçu.
    """
    nom = nom_grille or fonc.noms_grille(jour)
    tableaux = [r for r in RECLASSEMENTS.get(nom, []) if r.date == jour]
    if not tableaux:
        raise ValueError(f"pas de tableau de reclassement pour {nom} au {jour}")
    # L'échelon du jour même : une promotion qui tombe ce jour-là se fait d'abord selon
    # l'ancien statut (règle préalable du PPCR, voir reclassements.toml).
    ancien = fonc.echelon(jour)
    correspondance = tableaux[0].table.get(ancien)
    if correspondance is None:
        raise ValueError(f"{nom} au {jour} : l'échelon {ancien} n'est pas dans le tableau")
    anciennete = 0.0
    if correspondance.anciennete == CONSERVEE:
        anciennete = anciennete_au(fonc, jour) + correspondance.majoration
    nouveau = correspondance.nouveau
    duree = fonc.grille(jour).anciennete
    limite = duree[nouveau - 1] if nouveau - 1 < len(duree) else None
    if limite is not None and anciennete >= limite:
        nouveau, anciennete = nouveau + 1, 0.0
    fonc.reclasse(jour, nouveau, anciennete)
