"""Heures supplémentaires : HSA, HSE, heures d'interrogation (colles).

Décret 50-1253 du 6 octobre 1950, article 2 : le taux annuel d'une HSA est le
traitement moyen du corps divisé par l'ORS hebdomadaire, multiplié par 9/13. Pour
un corps à une seule échelle, le traitement moyen est la moyenne des traitements de
début et de fin de la classe normale :

    HSA = (premier indice CN + dernier indice CN) / 2 × point annuel / ORS × 9/13

- HSA : heures de l'année, à l'état VS, payées par neuvièmes d'octobre à juin. La
  première, que l'enseignant ne peut refuser, est majorée de 20 % (décret 99-824 du
  17 septembre 1999).
- HSE : heures ponctuelles, dont les remplacements de courte durée ; 1/36 de l'HSA
  majoré de 25 %.
- Heures d'interrogation (colles, 200207) : 1/36 de l'HSA réduit de 25 % (même
  décret). Le taux est celui du corps que désigne le code de colle déclaré par le
  lycée (CODE_COLLE), calculé sur la classe normale de ce corps.
"""

import datetime as dt
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

import bpaye.config as config
from bpaye.classes import Fixe, Ligne, Temporal
from bpaye.config import BAREME, Bareme
from bpaye.grille import GRILLE_AGCN, GRILLE_CHSUP, GRILLES, Grille
from bpaye.protocoles import Agent

__all__ = [
    "CODE",
    "CODES_HSE",
    "CODE_COLLE",
    "CORPS_DU_CODE",
    "GRILLE_DU_CORPS",
    "HSA_MONTHS",
    "TauxHeures",
    "calc_hsa",
    "code_colle",
    "compile_hs",
    "ds",
    "hsa",
    "hsa_majo",
    "hse",
    "hsi",
    "valeur_colle",
    "valeur_hse",
    "valeur_hsi",
]

# Code de colle de chaque ORS de classe, selon le corps du colleur (Grille.corps). Le
# récapitulatif HIO apparie les codes (161/157, 06/01, 07/90) : même type de classe, le
# second pour les chaires supérieures ; pas d'équivalent chaire supérieure pour 08.
CODE_COLLE = {
    "Agrégé": {8: 161, 9: 6, 10: 7, 11: 8},
    "Chaire Supérieure": {8: 157, 9: 1, 10: 90},
}
# Code de colle → ORS de la classe interrogée, et corps qu'il désigne.
CODE = {code: ors for codes in CODE_COLLE.values() for ors, code in codes.items()}
CORPS_DU_CODE = {code: corps for corps, codes in CODE_COLLE.items() for code in codes.values()}
# Le taux d'un corps se calcule sur sa classe normale, quelle que soit la classe du colleur.
GRILLE_DU_CORPS = {"Agrégé": GRILLE_AGCN, "Chaire Supérieure": GRILLE_CHSUP}
# Les corps à la grille des certifiés (décret 2017-789, art. 3, 5, 7, 9, 10 et 11-1).
for _corps in ("Certifié", "PE", "PLP", "PEPS", "CPE", "PsyEN"):
    GRILLE_DU_CORPS[_corps] = GRILLES["GRILLE_CERTCN"]
HSA_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5, 6]
# Décret 50-1253, art. 2 : « dans la limite d'une heure supplémentaire […] ce taux est
# majoré de 20 % » ; « pour les personnels enseignants nommés à la hors-classe ou à la
# classe exceptionnelle, le montant de l'indemnité […] est majoré de 10 % » ; art. 3 : pas
# cette majoration en CPGE (hors chaire supérieure) depuis le 1/9/2016.
# https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000489039/2026-10-17/
MAJORATION_PREMIERE_HSA = 0.20
MAJORATION_HC_CE = 0.10
# Art. 5 : une HSE vaut 1/36 du taux annuel, majoré de 15 %, de 25 % depuis le 1/1/2008
# (taux.toml) ; art. 3 : une heure d'interrogation, 1/36 réduit de 25 %.
MAJORATION_HSE = config.load("hse_majoration")  # celle du barème du paquet
REDUCTION_HSI = 0.75


def valeur_colle(code: int, date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le taux horaire d'une colle déclarée sous ``code`` : celui du corps que le code
    désigne, pas celui du colleur. Un lycée qui déclare 06 pour une chaire supérieure
    paie le taux des agrégés (61,06 € au lieu de 71,62 € en 2025-2026) ; c'est ce
    taux-là qui arrive sur le compte."""
    return valeur_hsi(
        bareme.load("point"), GRILLE_DU_CORPS[CORPS_DU_CODE[code]], date, code=code, bareme=bareme
    )


def code_colle(ors: int, corps: str) -> int:
    """Le code de colle d'une classe d'ORS ``ors`` pour un colleur du ``corps``."""
    try:
        return CODE_COLLE[corps][ors]
    except KeyError:
        raise ValueError(f"pas de code de colle pour une ORS de {ors} h en {corps}") from None


def calc_hsa(ors: int, point: Fixe, grille: Temporal[Grille], date: dt.date | None = None) -> float:
    inm = grille.value(date).inmoyen
    pt_annuel = point.value_annuel(date)
    return inm * pt_annuel / ors * 9 / 13


@dataclass(frozen=True, slots=True)
class TauxHeures(Mapping[str, Mapping[int, float]]):
    """Les taux, par ORS, de l'HSA (annuel), de l'HSE et de l'HSI (horaires). Ils se lisent
    aussi par nom : ``taux["HSA"][18]``, ``taux.items()``."""

    hsa: Mapping[int, float]
    hse: Mapping[int, float]
    hsi: Mapping[int, float]

    def __getitem__(self, nom: str) -> Mapping[int, float]:
        return {"HSA": self.hsa, "HSE": self.hse, "HSI": self.hsi}[nom]

    def __iter__(self) -> Iterator[str]:
        return iter(("HSA", "HSE", "HSI"))

    def __len__(self) -> int:
        return 3


def compile_hs(
    point: Fixe,
    grille: Temporal[Grille],
    date: dt.date | None = None,
    rounded: bool = True,
    bareme: Bareme = BAREME,
) -> TauxHeures:
    """Les taux des heures supplémentaires de ``grille`` à ``date``, pour chaque ORS."""
    taux_hsa: dict[int, float] = {}
    taux_hse: dict[int, float] = {}
    taux_hsi: dict[int, float] = {}
    fmt: Callable[[float], float] = (lambda x: round(x, 2)) if rounded else (lambda x: x)
    for _, ors in CODE.items():
        hsa_value = calc_hsa(ors, point, grille, date)
        taux_hsa[ors] = fmt(hsa_value)  # annuelle
        taux_hse[ors] = fmt(hsa_value / 36 * bareme.load("hse_majoration")(date))  # horaire
        taux_hsi[ors] = fmt(hsa_value / 36 * REDUCTION_HSI)  # horaire
    return TauxHeures(MappingProxyType(taux_hsa), MappingProxyType(taux_hse), MappingProxyType(taux_hsi))


def reference_hsa(fonctionnaire: Agent, date: dt.date) -> tuple[Temporal[Grille], float]:
    """La grille sur laquelle se calcule le taux des heures de ``fonctionnaire``, et la
    majoration qui s'y ajoute (décret 50-1253, art. 2 et 3) : la classe normale de son
    corps, majorée pour la hors classe et la classe exceptionnelle ; en CPGE, hors
    chaire supérieure, la classe normale des agrégés, sans majoration."""
    corps = fonctionnaire.corps(date) if len(fonctionnaire.corps) else fonctionnaire.grille.value(date).corps
    en_cpge = bool(fonctionnaire.cpge(date)) if len(fonctionnaire.cpge) else False
    if en_cpge and corps != "Chaire Supérieure":
        return GRILLE_DU_CORPS["Agrégé"], 0.0
    classe = fonctionnaire.grille.value(date).classe
    majoration = MAJORATION_HC_CE if classe in ("HC", "CE") else 0.0
    return GRILLE_DU_CORPS[corps], majoration


def taux_hsa_annuel(
    fonctionnaire: Agent, date: dt.date, rounded: bool = True, bareme: Bareme = BAREME
) -> float:
    """Le taux annuel d'une HSA de ``fonctionnaire`` pour son ORS à ``date``."""
    grille, majoration = reference_hsa(fonctionnaire, date)
    taux = calc_hsa(fonctionnaire.ors(date), bareme.load("point"), grille, date) * (1 + majoration)
    return round(taux, 2) if rounded else taux


# Les HSA et leur majoration s'arrondissent au centime le plus proche : relevé sur des
# bulletins de 2019 à 2026 (aucun texte lu ne le dit), où la troncature manque une ligne
# sur trois.


def hsa(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    heures = fonctionnaire.vs(date)
    taux_hsa = taux_hsa_annuel(fonctionnaire, date, bareme=bareme) / 9
    if date.month in HSA_MONTHS:
        return Ligne(
            round(taux_hsa * heures, 2),
            f"Heures Année Enseignement (HSA - {heures}h)",
            code=200205,
            classe="INDEM",
        )
    return Ligne(0, f"Heures Année Enseignement (HSA - {heures}h)", code=200205, classe="INDEM")


def hsa_majo(fonctionnaire: Agent, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    heures = fonctionnaire.vs(date)
    majoration = taux_hsa_annuel(fonctionnaire, date, bareme=bareme) / 9 * MAJORATION_PREMIERE_HSA
    if heures >= 1 and (date.month >= 10 or date.month <= 6):
        return Ligne(round(majoration, 2), "Majo 1ère HSA", code=200576, classe="INDEM")
    return Ligne(0, "Majo 1ère HSA", code=200576, classe="INDEM")


def _resolve_ors(code: int | None = None, ors: int | None = None) -> int:
    if code is not None:
        return CODE[code]
    assert ors is not None
    return ors


def _valeur_hs_type(
    hs_type: str,
    point: Fixe,
    grille: Temporal[Grille],
    date: dt.date | None,
    code: int | None = None,
    ors: int | None = None,
    bareme: Bareme = BAREME,
) -> float:
    return compile_hs(point, grille, date, rounded=False, bareme=bareme)[hs_type][_resolve_ors(code, ors)]


def valeur_hse(
    point: Fixe,
    grille: Temporal[Grille],
    date: dt.date | None,
    code: int | None = None,
    ors: int | None = None,
    bareme: Bareme = BAREME,
) -> float:
    return _valeur_hs_type("HSE", point, grille, date, code, ors, bareme)


# Les rubriques des heures effectives, toutes du décret 50-1253 (annexe 14 C de la DGFiP) :
# remplacement de courte durée (201241), à sa majoration propre (taux.toml,
# hse_majoration_rcd) ; réussite scolaire au lycée (201717, décrets 50-1253 et 89-883) et
# les HSE des dispositifs (stages de réussite, accompagnement éducatif…) recodées 201300
# au 1/9/2025, au taux de l'HSE.
CODES_HSE = {
    200215: "H. Eff. Ens. HSE",
    201241: "HSE remplacement courte durée",
    201717: "HSE réussite scolaire lycée",
    201300: "HSE dispositifs 2nd degré",
}


def hse(
    fonctionnaire: Agent,
    date: dt.date,
    heures: float,
    comm: str = "",
    bareme: Bareme = BAREME,
    code: int = 200215,
) -> Ligne:
    """Heures supplémentaires effectives, au taux de l'HSE, sous le ``code`` de CODES_HSE."""
    if code not in CODES_HSE:
        raise ValueError(f"code d'HSE inconnu {code}, attendus {list(CODES_HSE)}")
    taux_annuel = taux_hsa_annuel(fonctionnaire, date, rounded=False, bareme=bareme)
    majoration = "hse_majoration_rcd" if code == 201241 else "hse_majoration"
    taux_hse = taux_annuel / 36 * bareme.load(majoration)(date)
    total = round(taux_hse * heures, 2)
    return Ligne(total, f"{CODES_HSE[code]} {heures}h - {comm}", code=code, classe="INDEM")


def valeur_hsi(
    point: Fixe,
    grille: Temporal[Grille],
    date: dt.date | None,
    code: int | None = None,
    ors: int | None = None,
    bareme: Bareme = BAREME,
) -> float:
    return _valeur_hs_type("HSI", point, grille, date, code, ors, bareme)


def hsi(fonctionnaire: Agent, date: dt.date, heures: float, comm: str = "", bareme: Bareme = BAREME) -> Ligne:
    taux_hsi = taux_hsa_annuel(fonctionnaire, date, rounded=False, bareme=bareme) / 36 * REDUCTION_HSI
    total = round(taux_hsi * heures, 2)
    return Ligne(total, f"H. Interr. HSI {heures}h [{comm}]", code=200207, classe="INDEM")


def ds(fonctionnaire: Agent, date: dt.date, heures: float, comm: str = "", bareme: Bareme = BAREME) -> Ligne:
    """Heures de devoir surveillé payées comme des HSE (200215), au taux des heures
    d'interrogation réduit de moitié : relevé sur des bulletins, aucun texte lu ne le dit
    (supposé)."""
    taux_hsi = taux_hsa_annuel(fonctionnaire, date, rounded=False, bareme=bareme) / 36 * REDUCTION_HSI
    total = round(taux_hsi * heures / 2, 2)
    return Ligne(total, f"H. Interr. HSI {heures}h 50% - DS {comm}", code=200215, classe="INDEM")


# 01/07/10 : HSA = {8:2885.03, 9:2564.47, 10:2308.02, 11:2098.20}
# 01/07/16 : HSA = {8:2902.34, 9:2579.86, 10:2321.87, 11:2110.79}
# 01/02/2017 : {8:2939.22, 9:2612.64, 10:2351.38, 11:2137.61}
