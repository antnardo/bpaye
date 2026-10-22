"""Indemnité de résidence (102000), décret 85-1148 du 24 octobre 1985, article 9.

Un pourcentage du traitement brut selon la zone de la commune d'affectation : 3 % en
zone 1, 1 % en zone 2, 0 en zone 3 (classement par la circulaire FP/7 n° 1996 du
12 mars 2001). Le traitement retenu est au moins celui d'un indice majoré plancher : 313 de
2013 à 2021, puis le minimum de traitement de l'art. 8 (366 depuis 2024) ; taux.toml le date.
https://www.legifrance.gouv.fr/loda/id/LEGITEXT000006064738/2026-10-17/
"""

import datetime as dt

import bpaye.config as config
from bpaye.classes import Ligne
from bpaye.codes import RESIDENCE
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.point import traitement_plein, valeur_point
from bpaye.utils import truncate

__all__ = [
    "calc_indemnite_residence",
    "indemnite_residence",
    "min_inm",
    "prop_brut",
]

# Celles du barème du paquet.
prop_brut = config.get("indemnite_residence.taux_zone")
min_inm = config.load("indemnite_residence.indice_min")  # daté : art. 9, puis art. 8


def calc_indemnite_residence(
    zone: int, brut: float, point: float, date: dt.date | None = None, bareme: Bareme = BAREME
) -> float:
    plancher = bareme.load("indemnite_residence.indice_min")(date)
    taux = bareme.get("indemnite_residence.taux_zone")
    brut_mini = max(brut, plancher * point)
    return truncate(taux[zone - 1] * brut_mini, 2)


def indemnite_residence(fonctionnaire: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    # Sur le traitement et la NBI d'un temps plein, puis à la fraction d'un temps partiel
    # (code général de la fonction publique, L612-5).
    pt = valeur_point(date, bareme)
    brut = traitement_plein(fonctionnaire, date, bareme)
    zone = fonctionnaire.residence(date)
    montant = calc_indemnite_residence(zone, brut, pt, date, bareme)
    return Ligne(
        fonctionnaire.au_prorata(montant, date),
        "Indemnité de résidence",
        code=RESIDENCE,
        classe="INDEM",
    )
