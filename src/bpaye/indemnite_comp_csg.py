"""
Indemnité compensatrice de la hausse de la CSG (202209).

https://www.service-public.fr/particuliers/vosdroits/F34473

Son montant est propre à chaque agent (décret 2017-1889, art. 2) : pour un agent en poste
avant 2018, (rémunération brute de 2017 × 1,6702 % − contribution de solidarité − cotisation
maladie − contribution chômage de 2017) × 1,1053 ; pour un agent nommé depuis, 0,76 % de sa
première rémunération mensuelle brute d'un mois complet ; l'assiette : les éléments soumis à
la CSG. Chaque 1er janvier, il suit l'évolution de cette rémunération d'une année sur
l'autre, changement de quotité et congé maladie neutralisés (art. 5, version depuis le
1/1/2021 ; en 2019 et 2020, seulement à la hausse).
https://www.legifrance.gouv.fr/loda/id/JORFTEXT000036342240/2026-10-17/

bpaye ne refait pas ce calcul, qui demande la rémunération de 2017 ou du premier mois, tout
ce qui est soumis à la CSG compris (heures, colles, jurys, autre employeur), que la carrière
ne déclare pas toujours et dont les bulletins de 2017 n'existent souvent que sur papier :
agent.toml donne le montant ([ic_csg], relevé sur les bulletins ; docs/DOC.md, section 4).
Sans lui, aucune valeur ne vaut pour tous les agents : bpaye refuse les mois depuis 2018.
"""

import datetime as dt

from bpaye.classes import Ligne
from bpaye.codes import ICCSG
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire

__all__ = [
    "DEBUT_IC_CSG",
    "indemnite_comp_csg",
]

# Loi 2017-1837, art. 113, et décret 2017-1889 : l'indemnité compense, à compter du
# 1/1/2018, la hausse de la CSG ; rien avant.
# https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000036339197 (lu le 19/10/2026)
DEBUT_IC_CSG = dt.date(2018, 1, 1)


def indemnite_comp_csg(
    date: dt.date, fonctionnaire: Fonctionnaire | None = None, bareme: Bareme = BAREME
) -> Ligne | None:
    if date < DEBUT_IC_CSG:
        return None
    propre = getattr(fonctionnaire, "ic_csg", None)
    if propre is None:
        raise ValueError(
            f"Indemnité compensatrice de CSG au {date} : propre à l'agent, à déclarer dans "
            "agent.toml ([ic_csg], le montant du bulletin) ; aucune valeur commune (MANQUANT)"
        )
    montant = propre(date)
    return Ligne(montant, "Indemnité compensatrice CSG", code=ICCSG, classe="INDEM")
