"""Les bulletins lus et leur calcul, en CSV : un fichier par mois, deux pour tous les mois.

Le fichier d'un mois se lit comme le bulletin : ses lignes dans l'ordre imprimé, chaque
montant dans sa colonne (à payer, à déduire, pour information), et en dernière colonne le
montant que bpaye calcule pour ce code. Les deux fichiers de tous les mois sont le même
tableau transposé, une ligne par mois et une colonne par code : l'un porte les montants
lus, l'autre les montants calculés, aux mêmes places, pour les comparer cellule à cellule.

Un montant calculé s'écrit dans le sens où le bulletin l'imprime : positif dans sa
colonne. bpaye compte les retenues en négatif ; elles changent donc de signe ici, et une
réduction de cotisation, positive pour bpaye, sort négative à déduire, comme sur le
bulletin. Le calcul d'un code réunit ses codes équivalents (codes.CODES_EQUIVALENTS) et ses
rappels : bpaye sait qu'une ligne est due un autre mois, pas sous quelle mention la paie
l'imprimera. Le tableau de tous les mois compte donc chaque code rappels compris, des deux
côtés ; le fichier d'un mois garde les rappels lus ligne par ligne, et met le calcul du
code sur sa première ligne.

Le format est celui des tableurs français : point-virgule entre les champs, virgule
décimale, UTF-8 avec BOM pour qu'Excel reconnaisse les accents.
"""

import csv
import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from bpaye.classes import Ligne
from bpaye.codes import ALL_CODES, equivalents
from bpaye.paye import Bulletin
from bpaye.pdf import BulletinLu

__all__ = [
    "LigneExportee",
    "ecrit_mois",
    "ecrit_tous_les_mois",
    "lignes_du_mois",
    "montants_calcules",
    "montants_lus",
]

# Les classes de lignes que bpaye imprime « à déduire » : leur montant change de signe.
_CLASSES_A_DEDUIRE = ("PC", "CHARGE", "RAFP", "IMPOT")

NET_A_PAYER = "net à payer"
MONTANT_IMPOSABLE = "montant imposable"

_ENTETE_MOIS = ["code", "libellé", "à payer", "à déduire", "pour information", "remarque", "calcul"]


@dataclass(frozen=True, slots=True)
class LigneExportee:
    """Une ligne du fichier d'un mois : le montant lu dans sa colonne (``colonne`` vaut
    ``"payer"``, ``"deduire"`` ou ``"information"`` ; None pour une ligne que seul le
    calcul porte), une remarque (rappel, code inconnu) et le montant calculé."""

    code: str
    libelle: str
    colonne: str | None
    lu: float | None
    remarque: str
    calcul: float | None


def _cle(code: str) -> str:
    """Le code qui représente ses équivalents (201228 pour 201228 et 202566)."""
    return min(equivalents(code))


def _imprime(ligne: Ligne) -> float:
    """Le montant d'une ligne calculée, dans le sens où le bulletin l'imprime."""
    return -ligne.valeur if ligne.type in _CLASSES_A_DEDUIRE else ligne.valeur


def montants_calcules(bulletin: Bulletin) -> dict[str, float]:
    """Les montants calculés d'un mois, par code (équivalents et rappels réunis), dans le
    sens du bulletin."""
    montants: dict[str, float] = {}
    for ligne in bulletin:
        cle = _cle(f"{ligne.code:06d}")
        montants[cle] = round(montants.get(cle, 0.0) + _imprime(ligne), 2)
    return montants


def montants_lus(lu: BulletinLu) -> dict[str, float]:
    """Les montants lus d'un mois, par code (équivalents et rappels réunis), positifs dans
    la colonne de leur catégorie ; les codes inconnus de bpaye y sont, montant imprimé."""
    montants: dict[str, float] = {}
    for cle_lue, montant in lu.montants.items():
        cle = _cle(cle_lue.removesuffix("_R"))
        montants[cle] = round(montants.get(cle, 0.0) + montant, 2)
    for code, _libelle, montant in lu.inconnus:
        montants[code] = round(montants.get(code, 0.0) + montant, 2)
    return montants


def _libelle(code: str, lus: Mapping[str, str] | None = None) -> str:
    if code in ALL_CODES:
        return str(ALL_CODES[code]["libelle"])
    return (lus or {}).get(code, "")


def lignes_du_mois(lu: BulletinLu | None, calcul: Bulletin | None) -> list[LigneExportee]:
    """Les lignes du fichier d'un mois : celles du bulletin lu, dans l'ordre imprimé, puis
    les codes que seul le calcul porte, puis le net à payer et le montant imposable."""
    calcules = montants_calcules(calcul) if calcul is not None else {}
    places: set[str] = set()
    lignes: list[LigneExportee] = []
    for ligne in lu.lignes if lu is not None else ():
        cle = _cle(ligne.code)
        valeur = calcules.get(cle) if cle not in places else None
        places.add(cle)
        lignes.append(
            LigneExportee(
                ligne.code,
                ligne.libelle,
                ligne.colonne,
                ligne.montant,
                "rappel" if ligne.rappel else "",
                valeur,
            )
        )
    for code, libelle, montant in lu.inconnus if lu is not None else ():
        lignes.append(
            LigneExportee(code, libelle, "payer", montant, "code inconnu de bpaye, colonne non lue", None)
        )
    for cle, valeur in calcules.items():
        if cle not in places:
            lignes.append(LigneExportee(cle, _libelle(cle), None, None, "calcul seul", valeur))
    lignes.append(
        LigneExportee(
            "",
            NET_A_PAYER,
            "payer",
            lu.net_payer if lu is not None else None,
            "",
            round(calcul.net, 2) if calcul is not None else None,
        )
    )
    lignes.append(
        LigneExportee(
            "",
            MONTANT_IMPOSABLE,
            "payer",
            lu.montant_imp if lu is not None else None,
            "",
            round(calcul.net_imposable, 2) if calcul is not None else None,
        )
    )
    return lignes


def _nombre(valeur: float | None) -> str:
    return "" if valeur is None else f"{valeur:.2f}".replace(".", ",")


def ecrit_mois(chemin: str | Path, lu: BulletinLu | None, calcul: Bulletin | None) -> None:
    """Écrit le fichier d'un mois : le bulletin lu, colonne par colonne, et le calcul."""
    with Path(chemin).open("w", encoding="utf-8-sig", newline="") as f:
        ecrivain = csv.writer(f, delimiter=";")
        ecrivain.writerow(_ENTETE_MOIS)
        for ligne in lignes_du_mois(lu, calcul):
            montants = [
                _nombre(ligne.lu) if ligne.colonne == c else "" for c in ("payer", "deduire", "information")
            ]
            ecrivain.writerow([ligne.code, ligne.libelle, *montants, ligne.remarque, _nombre(ligne.calcul)])


def ecrit_tous_les_mois(
    chemin_lus: str | Path,
    chemin_calculs: str | Path,
    mois: Iterable[tuple[dt.date, BulletinLu | None, Bulletin | None]],
) -> None:
    """Écrit les deux tableaux de tous les mois, une ligne par mois (``AAAA-MM``) et une
    colonne par code, aux mêmes places : les montants lus dans ``chemin_lus``, les
    montants calculés dans ``chemin_calculs``. Les colonnes sont les codes lus ou calculés
    au moins un mois, dans l'ordre des codes, puis le net à payer et le montant imposable."""
    rangs: list[tuple[str, dict[str, float | None], dict[str, float | None]]] = []
    libelles_lus: dict[str, str] = {}
    for date, lu, calcul in sorted(mois, key=lambda m: m[0]):
        lus: dict[str, float | None] = {}
        calcules: dict[str, float | None] = {}
        if lu is not None:
            lus.update(montants_lus(lu))
            lus[NET_A_PAYER] = lu.net_payer
            lus[MONTANT_IMPOSABLE] = lu.montant_imp
            libelles_lus.update({code: libelle for code, libelle, _ in lu.inconnus})
            libelles_lus.update({_cle(ligne.code): ligne.libelle for ligne in lu.lignes})
        if calcul is not None:
            calcules.update(montants_calcules(calcul))
            calcules[NET_A_PAYER] = round(calcul.net, 2)
            calcules[MONTANT_IMPOSABLE] = round(calcul.net_imposable, 2)
        rangs.append((f"{date:%Y-%m}", lus, calcules))
    pieds = (NET_A_PAYER, MONTANT_IMPOSABLE)
    codes = sorted({c for _, lus, calcules in rangs for c in (*lus, *calcules)} - set(pieds))
    entete = ["mois", *(f"{c} {_libelle(c, libelles_lus)}".strip() for c in codes), *pieds]
    for chemin, calcule in ((chemin_lus, False), (chemin_calculs, True)):
        with Path(chemin).open("w", encoding="utf-8-sig", newline="") as f:
            ecrivain = csv.writer(f, delimiter=";")
            ecrivain.writerow(entete)
            for nom, lus, calcules in rangs:
                montants = calcules if calcule else lus
                ecrivain.writerow([nom, *(_nombre(montants.get(c)) for c in (*codes, *pieds))])
