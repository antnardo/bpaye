"""Heures supplémentaires : réduction de cotisations (453000) et exonération d'impôt (011200).

Depuis 2019 (loi 2018-1213), les HSA, leur majoration et les heures d'interrogation,
pas les indemnités, ont :

- une réduction de cotisations salariales de 5 % (le taux salarial de la RAFP), dans
  la limite de 20 % du traitement indiciaire brut annuel ; compensée, elle laisse les
  droits RAFP intacts ;
- une exonération d'impôt sous un plafond annuel net, 5 000 € puis 7 500 € pour les
  heures faites depuis le 1/1/2022 (loi 2022-1157, art. 4). Le plafond brut réintègre la
  CSG déductible :
  5 000 / (1 − 98,25 % × 6,8 %) = 5 357,96, arrondi à 5 358 €. Sur ces heures, la CSG
  n'est pas déductible (charges.csg_basculee).

Le net exonéré (011200) se retrouve depuis le bulletin : S = (N + C + R − M) / f, N le
net avant impôt, C la CSG non déductible, R la CRDS, M le montant imposable, et
f = 1 − abattement × taux déductible (0,93319 depuis 2018 : facteur_hs_net).

En 2019, les heures de janvier à mars ont été régularisées en octobre (ligne « Regul
réduction cotis HS montant HS payé ») ; le prélèvement à la source de ces mois les
comptait encore imposables.

Sources : lois 2012-958 et 2018-1213 (ci-dessous) ;
https://www.fonction-publique.gouv.fr/exoneration-des-heures-supplementaires (taux et plafond
de la réduction pour les fonctionnaires).
"""

import datetime as dt

from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme
from bpaye.protocoles import BulletinMois

__all__ = [
    "DEBUT_EXONERATION_HS",
    "FIN_EXONERATION_TEPA",
    "FIN_REDUCTION_TEPA",
    "ExonerationHS",
    "facteur_hs_net",
    "reduc_cotis_hs",
]

# Ces régimes sont datés par l'heure effectuée ; bpaye prend la date du bulletin.
# - Loi 2012-958, art. 3 : II abroge l'exonération d'impôt (CGI, art. 81 quater) pour les
#   heures effectuées depuis le 1/8/2012 (VIII C), I la réduction de cotisations (CSS,
#   art. L241-17) depuis le 1/9/2012 (VIII A).
#   https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000026288968 (lu le 18/10/2026)
# - Loi 2018-1213, art. 2 : II rétablit l'exonération pour les heures réalisées depuis le
#   1/1/2019, III y avance la réduction (loi 2018-1203, art. 7, V).
#   https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000037851899 (lu le 18/10/2026)
# Avant 2012, le régime de la loi 2007-1223 n'est pas relu : MANQUANT, et bpaye refuse ces
# heures plutôt que de leur appliquer celui de 2019.
FIN_EXONERATION_TEPA = dt.date(2012, 8, 1)
FIN_REDUCTION_TEPA = dt.date(2012, 9, 1)
DEBUT_EXONERATION_HS = dt.date(2019, 1, 1)


def _refuse_avant(date: dt.date, fin_tepa: dt.date) -> None:
    if date < fin_tepa:
        raise ValueError(
            f"Heures supplémentaires au {date} : régime de la loi 2007-1223 non vérifié (MANQUANT)"
        )


def reduc_cotis_hs(hs_brut: float, tb_annuel: float, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """Réduction de cotisations sur heures supplémentaires (code 453000), depuis 2019 : le
    taux salarial de la RAFP, sur les heures dans la limite de son plafond (20 % du
    traitement annuel) ; positive, elle augmente le net."""
    _refuse_avant(date, FIN_REDUCTION_TEPA)
    if date < DEBUT_EXONERATION_HS:
        return None
    assiette = min(hs_brut, bareme.get("rafp.plafond_pct.valeur") * tb_annuel)
    val = round(assiette * bareme.load("rafp")(date), 2)
    return Ligne(val, "Réduction cot. heures sup.", code=453000, classe="CHARGE")


def facteur_hs_net(date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le net d'un euro d'heures exonérées (011200) : sa CSG déductible ne se déduit pas,
    1 − abattement × taux déductible, 1 − 98,25 % × 6,8 % = 0,93319 depuis 2018."""
    return 1 - bareme.load("csg.abattement_taux")(date) * bareme.load("csg.deductible")(date)


class ExonerationHS:
    """Les heures supplémentaires exonérées d'impôt, bulletin par bulletin, sous le plafond
    annuel (CGI, art. 81 quater) : 7 500 € nets depuis le 1/1/2022, soit 8 037 € bruts.

    Le plafond se consomme dans l'ordre de l'année civile : les bulletins de 2024 à 2026
    exonèrent toutes les heures de janvier, celles de février jusqu'au plafond, plus rien
    ensuite (011200 au centime, cumulé à 7 500 €). Un seul plafond mensuel, comme le faisait
    hs_exa_net, exonérait toute l'année. Partagée par les bulletins d'une Paye, comme la
    RAFP : un bulletin dont l'exonération change fait recalculer les suivants de l'année.
    """

    def __init__(self, bareme: Bareme = BAREME) -> None:
        self._bulletins: list[BulletinMois] = []
        self._plafond = bareme.load("hs_exo.plafond_brut")

    def inscrit(self, bulletin: BulletinMois) -> None:
        self._bulletins.append(bulletin)
        self._bulletins.sort(key=lambda b: b.date)

    def brut_exonere(self, bulletin: BulletinMois) -> float:
        """Le brut d'heures supplémentaires exonéré sur ce bulletin."""
        if bulletin.hs_brut <= 0:
            return 0.0
        _refuse_avant(bulletin.date, FIN_EXONERATION_TEPA)
        if bulletin.date < DEBUT_EXONERATION_HS:
            return 0.0
        plafond = self._plafond(bulletin.date)
        cumul = 0.0
        for b in self._bulletins:
            if b.date.year != bulletin.date.year or b.date > bulletin.date:
                continue
            exonere = max(0.0, min(b.hs_brut, plafond - cumul))
            if b is bulletin:
                return exonere
            cumul += exonere
        return 0.0

    def suivants(self, bulletin: BulletinMois) -> list[BulletinMois]:
        """Les bulletins inscrits après celui-ci, dans la même année civile."""
        return [b for b in self._bulletins if b.date.year == bulletin.date.year and b.date > bulletin.date]
