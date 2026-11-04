"""Un bulletin lu et son calcul, rubrique par rubrique : ce que la carrière n'a pas prévu.

Comparer ligne à ligne ne suffit pas : la paie et bpaye ne rangent pas tout pareil, et un
écart en entraîne d'autres. Trois écarts de rangement se règlent avant la comparaison.

- Les **heures ponctuelles** (colles, HSE, surveillances, vacations : codes
  ``HEURES_PONCTUELLES``) ne sont pas dans la carrière. Elles sont prises au bulletin et
  ajoutées au calcul, où elles portent CSG et impôt, puis laissées hors de la
  comparaison : elles y seraient égales par construction.
- Un **rappel imprimé sur le bulletin** (``101000_R``) s'ajoute à son code, comme bpaye
  range les siens. Celui d'une **promotion payée par décompte** n'est sur le bulletin qu'en
  total (ligne « RAPPELS ») ; bpaye en fait des lignes de rappel sans code de la paie. Les
  deux se comparent donc en un total, les gains d'un côté. La retenue de ce rappel, la
  régularisation de pension, est tantôt une ligne 604000, tantôt seulement la retenue de
  « RAPPELS » : elle compte avec la pension, des deux côtés.
- Les **codes équivalents** (``codes.CODES_EQUIVALENTS``) n'en font qu'un.

Restent les écarts. Une retenue suit les revenus : une prime absente du bulletin y
abaisse la CSG, la CRDS et l'impôt. Le bulletin calculé est donc refait, sur une copie,
avec les revenus du bulletin ; une retenue qui retrouve alors son montant est un écart
**induit**, qui ne demande rien de plus. Les autres sont ce que la carrière ne dit pas
encore (échelon, HSA, taux d'impôt, promotion payée en retard) ou une erreur de la paie.

Un acompte régularisé (``REGULARISATION_ACOMPTE``) couvre un mois sans bulletin de
l'employeur : son montant est rendu à part, la comparaison du mois ne le compte pas.
"""

import copy
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bpaye.classes import Ligne
from bpaye.codes import (
    ALL_CODES,
    HEURES_PONCTUELLES,
    PENSION,
    PRELEVEMENT_SOURCE,
    REGULARISATION_ACOMPTE,
    REGULARISATION_PENSION,
    TRAITEMENT,
    equivalents,
)
from bpaye.paye import CODE_RAPPEL, CODE_RAPPEL_TRAITEMENT, Bulletin, Paye
from bpaye.pdf import BulletinLu

__all__ = ["SEUIL", "ComparaisonMois", "Ecart", "compare_mois", "montants", "signe"]

SEUIL = 0.005  # en deçà, deux montants sont égaux au centime
# Les lignes de rappel de bpaye (Paye.retard_statut), sans code de la paie.
_RAPPELS_CALCUL = frozenset({CODE_RAPPEL, CODE_RAPPEL_TRAITEMENT})


@dataclass(frozen=True, slots=True)
class Ecart:
    """Une rubrique où le calcul et le bulletin diffèrent, dans la convention de bpaye (une
    retenue est négative) ; ``induit`` si elle ne fait que suivre un écart de revenu."""

    code: int
    calcul: float
    bulletin: float
    induit: bool = False

    @property
    def libelle(self) -> str:
        return str(ALL_CODES.get(f"{self.code:06d}", {}).get("libelle", "?"))

    @property
    def nature(self) -> str:
        """« non prévu par le calcul », « absent du bulletin » ou « écart » : ce que dit
        l'écart en mots."""
        if not self.calcul:
            return "non prévu par le calcul"
        if not self.bulletin:
            return "calculé, absent du bulletin"
        return "écart"


@dataclass(frozen=True, slots=True)
class ComparaisonMois:
    """Le bulletin de l'employeur d'un mois comparé à son calcul (``compare_mois``).

    ``ponctuels`` : les heures ponctuelles payées, par code ; ``rappel_calcul`` et
    ``rappel_bulletin`` : les gains des rappels par décompte ; ``imposable_lu`` et
    ``taux_ir_lu`` : l'assiette et le taux de l'impôt lus, pour dire d'un écart d'impôt s'il
    vient de l'une ou de l'autre."""

    annee: int
    mois: int
    ecarts: tuple[Ecart, ...]
    ponctuels: Mapping[int, float]
    rappel_calcul: float
    rappel_bulletin: float
    net_du: float
    net_percu: float
    imposable_calcul: float
    imposable_lu: float | None
    taux_ir_lu: float | None
    acompte: float

    @property
    def imprevus(self) -> tuple[Ecart, ...]:
        """Les écarts qui ne sont pas induits."""
        return tuple(e for e in self.ecarts if not e.induit)

    @property
    def ecart_rappel(self) -> float:
        """Les gains des rappels par décompte, bulletin moins calcul."""
        return round(self.rappel_bulletin - self.rappel_calcul, 2)

    @property
    def conforme(self) -> bool:
        """Vrai si rien n'est imprévu : aucun écart propre, rappels égaux, pas d'acompte."""
        return not self.imprevus and abs(self.ecart_rappel) <= SEUIL and not self.acompte


def montants(lu: Mapping[str, Any]) -> dict[int, float]:
    """Les montants lus par code, ceux d'un rappel (« 101000_R ») ajoutés au code."""
    par_code: dict[int, float] = defaultdict(float)
    for cle, valeur in lu.items():
        code = cle.removesuffix("_R")
        if code.isdigit() and len(code) == 6 and isinstance(valeur, int | float):
            par_code[int(code)] += valeur
    return dict(par_code)


def signe(code: int) -> int | None:
    """Le signe d'un montant lu (positif dans sa colonne) dans la convention de bpaye ; None
    hors du net (cotisations patronales, cumuls du pied)."""
    if code == PRELEVEMENT_SOURCE:
        return -1
    categorie = ALL_CODES.get(f"{code:06d}", {}).get("cat")
    return 1 if categorie == "revenu" else -1 if categorie == "retenue" else None


def _code_commun(code: int) -> int:
    """Un code par rubrique : les codes équivalents n'en font qu'un, la régularisation de
    pension va à la pension."""
    if code == REGULARISATION_PENSION:
        code = PENSION
    return int(min(equivalents(f"{code:06d}")))


def _par_rubrique(bulletin: Bulletin) -> tuple[dict[int, float], float]:
    """Le bulletin calculé par rubrique, sans les heures ponctuelles, et le total de ses
    lignes de rappel."""
    calcul: dict[int, float] = defaultdict(float)
    rappel = 0.0
    for ligne in bulletin:
        if ligne.code in _RAPPELS_CALCUL:
            rappel += ligne.valeur
        elif ligne.code not in HEURES_PONCTUELLES:
            calcul[_code_commun(ligne.code)] += ligne.valeur
    return calcul, round(rappel, 2)


def compare_mois(paye: Paye, lu: BulletinLu, annee: int, mois: int) -> ComparaisonMois:
    """Compare le bulletin lu ``lu`` au calcul de ``paye`` pour ce mois.

    ``lu`` est le bulletin de l'employeur du mois (``bulletins.trouve_bulletins``, attribut
    ``compare``). Les heures ponctuelles qu'il paie sont ajoutées au bulletin calculé de
    ``paye`` : le seul changement fait à ``paye``, qui le rend juste. Le reste du calcul se
    fait sur une copie."""
    lus = montants(lu)
    ponctuels = {code: lus[code] for code in sorted(HEURES_PONCTUELLES & set(lus))}
    for code, montant in ponctuels.items():
        paye.addligne(annee, mois, Ligne(montant, "payé (bulletin)", code=code, classe="INDEM"))
    calcule = paye.bulletin(annee, mois)
    calcul, rappel_calcul = _par_rubrique(calcule)

    bulletin: dict[int, float] = defaultdict(float)
    for code, valeur in lus.items():
        if code not in HEURES_PONCTUELLES and (s := signe(code)) is not None:
            bulletin[_code_commun(code)] += s * valeur
    if REGULARISATION_PENSION not in lus:
        bulletin[PENSION] += lu.rappel_decompte_ret or 0.0

    def differe(selon: Mapping[int, float], code: int) -> bool:
        return abs(selon.get(code, 0.0) - bulletin.get(code, 0.0)) > SEUIL

    codes = [code for code in sorted(set(calcul) | set(bulletin)) if differe(calcul, code)]
    refait = copy.deepcopy(calcule)
    for code in codes:
        if signe(code) == 1:
            classe = "BRUT" if code == TRAITEMENT else "INDEM"
            ajout = bulletin.get(code, 0.0) - calcul.get(code, 0.0)
            refait.append(Ligne(ajout, "revenu du bulletin", code=code, classe=classe), recalc=True)
    recalcul, _ = _par_rubrique(refait)

    ecarts = tuple(
        Ecart(
            code,
            round(calcul.get(code, 0.0), 2),
            round(bulletin.get(code, 0.0), 2),
            induit=signe(code) != 1 and not differe(recalcul, code),
        )
        for code in codes
    )
    impot = lus.get(PRELEVEMENT_SOURCE)
    return ComparaisonMois(
        annee=annee,
        mois=mois,
        ecarts=ecarts,
        ponctuels=ponctuels,
        rappel_calcul=rappel_calcul,
        rappel_bulletin=lu.rappel_decompte or 0.0,
        net_du=round(calcule.net, 2),
        net_percu=lu.net_payer or 0.0,
        imposable_calcul=round(calcule.net_imposable, 2),
        imposable_lu=lu.montant_imp,
        taux_ir_lu=abs(impot) / lu.montant_imp if impot and lu.montant_imp else None,
        acompte=lus.get(REGULARISATION_ACOMPTE, 0.0),
    )
