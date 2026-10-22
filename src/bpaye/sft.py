"""Supplément familial de traitement (104000), décret 85-1148 du 24 octobre 1985, articles 10 à 12.

Un élément fixe et un élément proportionnel au traitement, selon le nombre d'enfants (1,
2, 3, puis par enfant au-delà). L'élément proportionnel se calcule sur un traitement
ramené entre celui de l'IB 524 et celui de l'IB 879 (art. 10 bis) : traitements
recalculés chaque mois, au point et au barème IB → IM du moment, et non des montants
figés. Sans enfant à charge, pas de SFT. Le résultat est arrondi au centime : aucun
bulletin à plusieurs enfants ne l'a encore vérifié (relevé : un enfant, 2,29 €).
https://www.legifrance.gouv.fr/loda/id/LEGITEXT000006064738/2026-10-17/
"""

import datetime as dt

from bpaye.classes import Ligne
from bpaye.codes import SFT
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.grille import indice_majore
from bpaye.point import calc_traitement_brut, traitement_plein
from bpaye.temps_partiel import reduit

__all__ = [
    "sft",
    "sft_du_mois",
    "valeur_sft",
]


def valeur_sft(n_enfants: int, brut: float, date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le SFT mensuel de ``n_enfants`` pour un traitement brut ``brut`` à ``date``."""
    if n_enfants <= 0:
        return 0.0
    t = bareme.get("sft")
    i = min(2, n_enfants - 1)
    au_dela = max(0, n_enfants - 3)
    plancher = calc_traitement_brut(indice_majore(t["ib_plancher"], date), date, bareme)
    plafond = calc_traitement_brut(indice_majore(t["ib_plafond"], date), date, bareme)
    assiette = min(max(brut, plancher), plafond)
    fixe = t["fixe"][i] + t["fixe_supp"] * au_dela
    taux = t["prop_brut"][i] + t["prop_brut_supp"] * au_dela
    return round(fixe + taux * assiette, 2)


def sft_du_mois(
    n_enfants: int, plein: float, fraction: float, date: dt.date, bareme: Bareme = BAREME
) -> float:
    """Le SFT de ``n_enfants`` sur ``plein``, le traitement et la NBI d'un temps plein
    (décret 93-522, art. 3). À temps partiel, il suit la fraction de rémunération, sauf
    l'élément fixe pour un enfant (décret 85-1148, art. 12), sans descendre sous le minimum
    d'un temps plein ayant le même nombre d'enfants (code général de la fonction publique,
    L612-6)."""
    montant = valeur_sft(n_enfants, plein, date, bareme)
    if fraction < 1.0 and n_enfants >= 2:
        minimum = valeur_sft(n_enfants, 0.0, date, bareme)  # traitement ramené au plancher
        montant = max(reduit(montant, fraction), minimum)
    return montant


def sft(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    """Le SFT du mois (sft_du_mois)."""
    montant = sft_du_mois(
        fonc.enfants(date), traitement_plein(fonc, date, bareme), fonc.fraction(date), date, bareme
    )
    return Ligne(
        montant,
        "Supplément familial traitement",
        code=SFT,
        classe="INDEM",
    )
