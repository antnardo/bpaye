"""Garantie individuelle du pouvoir d'achat (GIPA, 201480), décret 2008-539.

Sur une période de référence de quatre ans, du 31 décembre de l'année N-4 au 31 décembre
de N-1, la GIPA rend la perte du traitement indiciaire brut face à l'inflation :
G = TIB de début × (1 + inflation) − TIB de fin, chaque TIB étant l'indice majoré détenu
au 31 décembre × la valeur moyenne annuelle du point de l'année ; l'indemnité de
résidence, le SFT, la NBI et les primes n'y entrent pas (art. 3). À temps partiel, elle
est versée à la quotité travaillée au 31 décembre de fin (art. 10). Un arrêté par année
fixe l'inflation et les valeurs du point (art. 8) : taux.toml [[gipa]], chacun avec sa
source. Aucune GIPA n'a paru après celle de 2023.
https://www.legifrance.gouv.fr/loda/id/JORFTEXT000018934143/2026-10-17/

Ce que bpaye ne vérifie pas : les conditions d'éligibilité (trois ans d'emploi public sur
quatre, grade dont l'indice sommital ne dépasse pas HEB, exclusions de l'art. 10), et la
cotisation RAFP de la GIPA hors du plafond de 20 % (décret 2008-964, art. 1) : la ligne
cotise comme les autres primes. Le mois de versement n'est fixé par aucun texte lu : il
se donne à Paye.gipa.
"""

from typing import Any

from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire

__all__ = [
    "gipa",
    "montant_gipa",
]


def _periode(annee: int, bareme: Bareme) -> dict[str, Any]:
    for entree in bareme.get("gipa"):
        if entree["annee"] == annee:
            return dict(entree)
    raise ValueError(f"pas de GIPA au titre de {annee} dans le barème")


def montant_gipa(fonc: Fonctionnaire, annee: int, bareme: Bareme = BAREME) -> float:
    """La GIPA au titre de ``annee``, au centime ; 0 si le traitement a suivi l'inflation."""
    p = _periode(annee, bareme)
    tib_debut = fonc.indice_detenu(p["debut"]) * p["point_debut"]
    tib_fin = fonc.indice_detenu(p["fin"]) * p["point_fin"]
    garantie = tib_debut * (1 + p["inflation"]) - tib_fin
    if garantie <= 0:
        return 0.0
    quotite = fonc.quotite.au(p["fin"], 1.0)
    return round(garantie * min(quotite, 1.0), 2)


def gipa(fonc: Fonctionnaire, annee: int, bareme: Bareme = BAREME) -> Ligne | None:
    montant = montant_gipa(fonc, annee, bareme)
    if not montant:
        return None
    return Ligne(montant, f"GIPA {annee}", code=201480, classe="INDEM")
