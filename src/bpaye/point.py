"""Valeur du point d'indice et traitement brut.

Le traitement brut est l'indice majoré multiplié par la valeur mensuelle du point,
tronqué au centime (et non arrondi : bulletin de septembre 2016). Les valeurs
annuelles sont plus précises que les mensuelles ; taux.toml les garde en mensuel.

Valeur annuelle du point, pour mémoire (taux.toml en a la part utile) :

    1er juillet 2023    59,0734 €     1er février 2005    53,0196 €
    1er juillet 2022    58,20 €       1er janvier 2004    52,7558 €
    1er février 2017    56,2323 €     1er décembre 2002   52,4933 €
    1er juillet 2016    55,8969 €     1er mars 2002       52,1284 €
    1er juillet 2010    55,5635 €     1er janvier 2002    51,8175 €
    1er octobre 2009    55,2871 €     1er novembre 2001   51,8174 €
    1er juillet 2009    55,1217 €     1er mai 2001        51,4576 €
    1er octobre 2008    54,8475 €     1er décembre 2000   51,2015 €
    1er mars 2008       54,6834 €     1er décembre 1999   50,9469 €
    1er février 2007    54,4113 €     1er avril 1999      50,5445 €
    1er juillet 2006    53,9795 €     1er novembre 1998   50,2929 €
    1er novembre 2005   53,7110 €     1er avril 1998      50,046 €
    1er juillet 2005    53,2847 €     1er octobre 1997    49,6481 €
                                      1er mars 1997       49,4011 €
                                      1er novembre 1995   49,1557 €
                                      1er mars 1995       48,4773 €
"""

import datetime as dt

import bpaye.config as config
from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme
from bpaye.protocoles import Agent
from bpaye.temps_partiel import reduit
from bpaye.utils import truncate

__all__ = [
    "POINT",
    "calc_traitement_brut",
    "traitement_brut",
    "traitement_indiciaire",
    "traitement_nbi",
    "traitement_plein",
    "valeur_point",
]

POINT = config.BAREME.load("point")  # celui du barème du paquet


def traitement_indiciaire(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le traitement d'un temps plein pour le mois de ``date``, sans NBI. Un échelon pris en
    cours de mois est payé par trentièmes : les jours d'avant au traitement de l'ancien
    indice, les autres à celui du nouveau, chaque part tronquée au centime. Aucun texte lu
    ne fixe ce prorata ni l'ordre des calculs (MANQUANT) ; cette règle retrouve le décompte
    de rappel d'un 8e échelon d'agrégé pris le 8 mars 2018 (7 jours à l'IM 646, 23 à l'IM
    695 : 706,33 + 2 496,86 = 3 203,19 €, retenue PC 338,26 €), quand le prorata de l'indice
    (683,56 × point) donnait 3 203,17 €, et le calcul sans troncature 3 203,20 €."""
    changement = fonctionnaire.changement_d_indice(date)
    if changement is None:
        return calc_traitement_brut(fonctionnaire.indice(date), date, bareme)
    jours, i_prec, i = changement
    ancien = truncate(calc_traitement_brut(i_prec, date, bareme) * jours / 30, 2)
    nouveau = truncate(calc_traitement_brut(i, date, bareme) * (30 - jours) / 30, 2)
    return round(ancien + nouveau, 2)


def traitement_brut(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    """Le traitement du mois, à la fraction de rémunération d'un temps partiel."""
    brut = traitement_indiciaire(fonctionnaire, date, bareme)
    return Ligne(reduit(brut, fonctionnaire.fraction(date)), "Traitement Brut", code=101000)


def traitement_nbi(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """La nouvelle bonification indiciaire (101070) : ses points × la valeur du point,
    soumise à retenue pour pension (loi 91-73, art. 27 ; décret 91-1229, art. 1), réduite
    comme le traitement à temps partiel (décret 93-522, art. 3). Les points comptés comme
    des points d'indice majoré, et l'arrondi : supposés (aucun texte de l'Éducation
    nationale lu ne le précise)."""
    points = fonctionnaire.points_nbi(date)
    if not points:
        return None
    montant = calc_traitement_brut(points, date, bareme)
    return Ligne(reduit(montant, fonctionnaire.fraction(date)), "Traitement brut NBI", code=101070)


def traitement_plein(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> float:
    """Traitement et NBI d'un temps plein : l'assiette de l'indemnité de résidence et du
    SFT (décret 93-522, art. 3), avant la fraction d'un temps partiel."""
    points = fonctionnaire.points_nbi(date)
    brut = traitement_indiciaire(fonctionnaire, date, bareme)
    return brut + (calc_traitement_brut(points, date, bareme) if points else 0.0)


def calc_traitement_brut(indice: float, date: dt.date | None, bareme: Bareme = BAREME) -> float:
    """Le traitement mensuel d'un indice : le traitement annuel (indice × valeur annuelle du
    point, décret 85-1148, art. 3), arrondi au centime, divisé par douze et tronqué. L'ordre
    des arrondis n'est écrit dans aucun texte lu ; il retrouve les 115 traitements relevés de
    2017 à 2026, dont l'indice 639 en janvier 2017 (35 718,12 / 12 = 2 976,51 €), que
    l'indice multiplié par le point mensuel, tronqué, manquait d'un centime."""
    annuel = round(round(bareme.load("point")(date) * 12, 6) * indice, 2)
    return truncate(annuel / 12, 2)


def valeur_point(date: dt.date | None, bareme: Bareme = BAREME) -> float:
    return bareme.load("point")(date)
