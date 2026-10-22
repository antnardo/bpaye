"""Retenue pour pension civile (101050), sur le traitement indiciaire brut.

Le taux est monté d'environ 0,27 point par an, de 7,85 % à 11,10 % en 2020 (réformes
de 2010 et 2012), pour rejoindre celui des salariés du privé ; il est daté dans
taux.toml.
"""

import datetime as dt

import bpaye.config as config
from bpaye.classes import Ligne, Taux
from bpaye.codes import PENSION
from bpaye.config import BAREME, Bareme

__all__ = [
    "PC",
    "pension_civile",
]

PC: Taux = config.BAREME.load("pc")  # celui du barème du paquet


def pension_civile(brut: float, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    taux = bareme.load("pc")
    return Ligne(-round(taux.taux(brut, date), 2), "Pension civile", code=PENSION, classe="PC")
