"""Dates et arrondis communs au calcul."""

import datetime as dt
from collections.abc import Iterator
from math import ceil, floor

__all__ = [
    "add_date_round",
    "decalage_mois",
    "dernier_jour",
    "last_day_month",
    "next_month",
    "parse_toml_date",
    "previous_month",
    "range_mois",
    "truncate",
    "veille",
]


def parse_toml_date(d: dt.date | str) -> dt.date:
    """Normalise une date TOML : retourne dt.date si c'est déjà une date, sinon parse ISO."""
    if isinstance(d, str):
        return dt.date.fromisoformat(d)
    return d


def truncate(f: float, n: int, up: bool = False) -> float:
    """Tronque `f` à `n` décimales (ou arrondit au-dessus si `up`), comme la paie.

    Le produit flottant tombe souvent juste sous la valeur exacte : 0,29 × 100 vaut
    28,999…, 454 × 54,8475 / 12 vaut 2 193,8999…. Arrondir d'abord à six décimales
    au-delà du centime efface ce bruit, bien plus fin que tout montant de paie, avant
    de tronquer ; sinon le centime perdu passe dans le traitement.
    """
    x = round(f * 10**n, 6)
    return (ceil(x) if up else floor(x)) / 10**n


def add_date_round(date1: dt.date, yeardelta: float, jround: int) -> dt.date:
    """date1 avancée de yeardelta années, au jour jround du mois d'arrivée.

    Compter en mois, pas en jours : 2 × 365 jours après le 1er septembre 2023 tombent le
    31 août 2025, à cause du 29 février, et l'échelon passerait en août au lieu de
    septembre. Un jour que le mois d'arrivée n'a pas (le 31 en avril) devient son dernier
    jour : supposé, aucun texte lu ne le dit."""
    y, m = divmod(date1.month - 1 + round(yeardelta * 12), 12)
    debut = dt.date(date1.year + y, m + 1, 1)
    return debut.replace(day=min(jround, last_day_month(debut).day))


def previous_month(date: dt.date) -> dt.date:
    date_prev = date.replace(day=1) - dt.timedelta(days=1)
    return date_prev.replace(day=1)


def next_month(date: dt.date) -> dt.date:
    date_next = date.replace(day=28) + dt.timedelta(days=4)  # le 28 + 4 jours : toujours le mois suivant
    return date_next.replace(day=1)


def last_day_month(date: dt.date) -> dt.date:
    return veille(next_month(date))


def dernier_jour(year: int, mois: int) -> dt.date:
    """Le dernier jour du mois ``mois`` de ``year`` : la date d'un bulletin."""
    return last_day_month(dt.date(year, mois, 1))


def veille(date: dt.date) -> dt.date:
    """Le jour d'avant ``date``."""
    return date - dt.timedelta(days=1)


def decalage_mois(year: int, mois: int, decalage: int) -> tuple[int, int]:
    nextyear = year + (mois + decalage - 1) // 12
    nextmois = (mois + decalage - 1) % 12 + 1
    return nextyear, nextmois


def range_mois(start: tuple[int, int] = (2017, 9), n: int = 12) -> Iterator[tuple[int, int]]:
    for i in range(n):
        yield decalage_mois(*start, i)
