"""MGEN PSC – Protection Sociale Complémentaire (depuis mai 2026).

──────────────────────────────────────────────────────────────
CODES
──────────────────────────────────────────────────────────────
  720576  MGEN PART FORFAITAIRE  cotisation salariale forfaitaire     75,40 × 20 %
  720577  MGEN PART SOLIDAIRE    cotisation salariale modulée revenu  75,40 × 30 % × coeff
  720578  MGEN ACTION SOCIALE    2 % × (720576 + 720577) / 1,1327     imposable (non déductible IR)
  720579  MGEN AIDE RETRAITES    3 % × (720576 + 720577) / 1,1327     imposable (non déductible IR)
  720580  MGEN PART EMPLOYEUR    participation patronale 37,70 €      pour information

──────────────────────────────────────────────────────────────
PART SOLIDAIRE (720577) : LA FORMULE DE LA PAIE (docs/mgen.md)
──────────────────────────────────────────────────────────────
Le contrat MGEN – CNP qui fixe la formule n'a pas été trouvé ; bpaye reprend celle qui
retrouve les bulletins (mai à septembre 2026) :

    coeff = (MIN(tb, PMSS + TPP) + TPP) / BrutMoyen

Le TPP y compte deux fois ; on attendrait MIN(tb − TPP, PMSS) / BrutMoyen, soit 0,47 €
de moins par mois au-delà du plafond (exemple fictif : 29,63 € au lieu de 29,16 € pour
tb = 4 100 €). Les bulletins connus ont tous un traitement au-dessus de PMSS + TPP : ils
ne départagent pas les formules sous le plafond, où bpaye n'est vérifié par aucun
bulletin.

──────────────────────────────────────────────────────────────
CSG/CRDS – TRAITEMENT DE LA PART PATRONALE 720580
──────────────────────────────────────────────────────────────
La participation patronale (720580 = 37,70 €) est soumise à CSG/CRDS intégralement,
sans bénéficier de l'abattement de 1,75 %. Elle s'ajoute donc à l'assiette APRÈS
l'abattement (voir charges.py, paramètre supplement_hors_abat).

Exemple fictif (hors HSI), la règle ayant été vérifiée sur les bulletins PDF V4.2 :
    assiette_brute  = 7 000,00 €   (revenus − RDT − |TPP|)
    assiette_abattu = 7 000,00 × 0,9825 = 6 877,50 €
    assiette_finale = 6 877,50 + 37,70  = 6 915,20 €
    CSG ded         = round(0,068 × 6 877,50) + round(0,068 × 37,70) = 467,67 + 2,56 = 470,23 €
"""

import datetime as dt

from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme

__all__ = [
    "mgen_charges",
    "mgen_part_employeur",
]


def mgen_part_employeur(date: dt.date, bareme: Bareme = BAREME) -> float:
    """Part patronale MGEN (720580) à inclure dans l'assiette CSG sans abattement."""
    return bareme.load("mgen.taux_employeur")(date) * bareme.load("mgen.base")(date)


def _part_solidaire(tb: float, date: dt.date, bareme: Bareme = BAREME) -> float:
    """720577 : la formule de la paie, TPP compté deux fois (docs/mgen.md)."""
    base = bareme.load("mgen.taux_solidaire_base")(date) * bareme.load("mgen.base")(date)
    if base == 0.0:
        return 0.0
    pmss = bareme.load("pmss")(date)
    tpp = bareme.load("transfertpp")(date)  # mensuel (annuel ÷ 12)
    coeff = (min(tb, pmss + tpp) + tpp) / bareme.load("mgen.brut_moyen")(date)
    return round(base * coeff, 2)


def mgen_charges(tb: float, date: dt.date, bareme: Bareme = BAREME) -> list[Ligne]:
    """Lignes salariales MGEN 720576-720579 (retenues du bulletin).

    tb  : traitement brut mensuel en euros (indice × point).
    Retourne [] avant mai 2026 (part_forfaitaire == 0).
    """
    val_forfait = bareme.load("mgen.taux_forfaitaire")(date) * bareme.load("mgen.base")(date)
    if val_forfait == 0.0:
        return []
    val_solidaire = _part_solidaire(tb, date, bareme)
    base_ats = (val_forfait + val_solidaire) / (1 + bareme.load("mgen.taux_taxe")(date))
    val_action = round(bareme.load("mgen.taux_action_sociale")(date) * base_ats, 2)
    val_retraites = round(bareme.load("mgen.taux_aide_retraites")(date) * base_ats, 2)
    return [
        Ligne(-val_forfait, "MGEN PART FORFAITAIRE", code=720576, classe="CHARGE"),
        Ligne(-val_solidaire, "MGEN PART SOLIDAIRE", code=720577, classe="CHARGE"),
        Ligne(-val_action, "MGEN ACTION SOCIALE", code=720578, classe="CHARGE", imposable=True),
        Ligne(-val_retraites, "MGEN AIDE RETRAITES", code=720579, classe="CHARGE", imposable=True),
    ]
