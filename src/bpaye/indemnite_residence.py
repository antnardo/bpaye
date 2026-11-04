"""Indemnité de résidence (102000), décret 85-1148 du 24 octobre 1985, article 9.

Un pourcentage du traitement brut selon la zone de la commune d'affectation : 3 % en
zone 1, 1 % en zone 2, 0 en zone 3 (classement par la circulaire FP/7 n° 1996 du
12 mars 2001). Le traitement retenu est au moins celui d'un indice majoré plancher : 313 de
2013 à 2021, puis le minimum de traitement de l'art. 8 (366 depuis 2024) ; taux.toml le date.
https://www.legifrance.gouv.fr/loda/id/LEGITEXT000006064738/2026-10-17/

Son rappel suit celui du traitement : l'art. 9 la calcule « sur la base de leur traitement
soumis aux retenues pour pension » (version en vigueur depuis le 1/1/2022, lue le
4/11/2026), si bien qu'une promotion payée en retard lui doit le taux de la zone appliqué à
l'écart de cette base. La paie tronque ce produit mois par mois, au centime : décomptes de
juillet 2021 (3 % de 220,25 = 6,60, de 168,86 = 5,06), de novembre 2023 (de 211,68 = 6,35)
et d'avril 2026 (de 147,68 = 4,43).
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
    "base_indemnite_residence",
    "calc_indemnite_residence",
    "indemnite_residence",
    "min_inm",
    "prop_brut",
    "rappel_indemnite_residence",
]

# Celles du barème du paquet.
prop_brut = config.get("indemnite_residence.taux_zone")
min_inm = config.load("indemnite_residence.indice_min")  # daté : art. 9, puis art. 8


def base_indemnite_residence(
    brut: float, point: float, date: dt.date | None = None, bareme: Bareme = BAREME
) -> float:
    """Le traitement sur lequel se calcule l'indemnité : ``brut``, au moins celui de
    l'indice plancher."""
    plancher = bareme.au("indemnite_residence.indice_min", date)
    return max(brut, plancher * point)


def calc_indemnite_residence(
    zone: int, brut: float, point: float, date: dt.date | None = None, bareme: Bareme = BAREME
) -> float:
    taux = bareme.get("indemnite_residence.taux_zone")
    return truncate(taux[zone - 1] * base_indemnite_residence(brut, point, date, bareme), 2)


def rappel_indemnite_residence(zone: int, ecart: float, bareme: Bareme = BAREME) -> float:
    """Le rappel d'indemnité d'un mois dont la base a été payée ``ecart`` en dessous du dû :
    le taux de la zone sur l'écart, tronqué au centime comme les décomptes de rappel."""
    taux = bareme.get("indemnite_residence.taux_zone")
    return truncate(taux[zone - 1] * ecart, 2)


def indemnite_residence(
    fonctionnaire: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME, brut: float | None = None
) -> Ligne:
    """L'indemnité du mois, sur ``brut`` (traitement et NBI d'un temps plein) quand il est
    donné, au lieu de celui de l'indice du jour : celui qu'a payé une promotion en retard."""
    # Sur le traitement et la NBI d'un temps plein, puis à la fraction d'un temps partiel
    # (code général de la fonction publique, L612-5).
    pt = valeur_point(date, bareme)
    if brut is None:
        brut = traitement_plein(fonctionnaire, date, bareme)
    zone = fonctionnaire.residence(date)
    montant = calc_indemnite_residence(zone, brut, pt, date, bareme)
    return Ligne(
        fonctionnaire.au_prorata(montant, date),
        "Indemnité de résidence",
        code=RESIDENCE,
        classe="INDEM",
    )
