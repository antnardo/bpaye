"""Les bulletins PDF d'un dossier, chacun lu et rattaché à son employeur.

Un mois peut compter plusieurs bulletins, de plusieurs employeurs ; ils restent distincts
(employeurs.py). Chacun est rattaché d'après son en-tête :

- ``employeur`` : l'employeur déclaré pour ce mois ([[employeur]] d'agent.toml). C'est le
  seul que le calcul de bpaye, celui d'une seule carrière, peut comparer ;
- ``ancien employeur`` : un employeur déclaré, mais pour une autre période ; un rappel
  versé après le départ, par exemple. Ses lignes sont dues à des mois de cet employeur ;
- ``autre employeur`` : un employeur que la carrière ne déclare pas (jury, vacations,
  colles payées par un autre établissement).

Sans aucun employeur déclaré, le bulletin qui porte le traitement brut (101000) est celui
de l'employeur, et les autres sont d'autres employeurs. Le nom du fichier n'entre jamais
dans le choix : « -1 » ou « copie » ne disent rien de l'employeur.
"""

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from bpaye.employeurs import Employeur
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.pdf import BulletinLu, EmployeurLu, extract_bulletin, extract_employeur, find_pdfs

__all__ = [
    "ANCIEN_EMPLOYEUR",
    "AUTRE_EMPLOYEUR",
    "EMPLOYEUR",
    "BulletinTrouve",
    "bulletins_du_mois",
    "trouve_bulletins",
]

EMPLOYEUR = "employeur"
ANCIEN_EMPLOYEUR = "ancien employeur"
AUTRE_EMPLOYEUR = "autre employeur"


@dataclass(frozen=True, slots=True)
class BulletinTrouve:
    """Un bulletin du dossier : son fichier, son mois, sa lecture, son en-tête, le nom de
    son employeur (déclaré, ou le libellé imprimé) et son rattachement."""

    chemin: Path
    date: dt.date
    lu: BulletinLu
    entete: EmployeurLu
    nom: str
    rattachement: str

    @property
    def compare(self) -> bool:
        """Vrai pour le bulletin de l'employeur du mois, celui que le calcul compare."""
        return self.rattachement == EMPLOYEUR


def _declares(fonc: Fonctionnaire) -> list[Employeur]:
    connus: list[Employeur] = []
    for _, employeur in fonc.employeurs.values:
        if employeur not in connus:
            connus.append(employeur)
    return connus


def _nom(entete: EmployeurLu) -> str:
    return entete.libelle or entete.gestionnaire


def bulletins_du_mois(
    fonc: Fonctionnaire, date: dt.date, chemins: Sequence[str | Path]
) -> list[BulletinTrouve]:
    """Les bulletins d'un mois, lus et rattachés : celui de l'employeur d'abord, les autres
    ensuite, dans l'ordre des fichiers. Deux bulletins de l'employeur du mois restent deux :
    seul le premier est comparé au calcul."""
    lus = [(Path(c), extract_bulletin(c), extract_employeur(c)) for c in chemins]
    declares = _declares(fonc)
    du_mois = fonc.employeur(date)
    trouves: list[BulletinTrouve] = []
    for chemin, lu, entete in lus:
        reconnu = next((e for e in declares if e.reconnait(entete.sirets, entete.poste)), None)
        if not declares:
            rattachement = AUTRE_EMPLOYEUR
        elif reconnu is not None and reconnu == du_mois:
            rattachement = EMPLOYEUR
        elif reconnu is not None:
            rattachement = ANCIEN_EMPLOYEUR
        else:
            rattachement = AUTRE_EMPLOYEUR
        nom = reconnu.nom if reconnu is not None and reconnu.nom else _nom(entete)
        trouves.append(BulletinTrouve(chemin, date, lu, entete, nom, rattachement))
    if not declares:
        # Sans déclaration : le premier bulletin qui porte le traitement brut.
        for i, b in enumerate(trouves):
            if "101000" in b.lu:
                trouves[i] = BulletinTrouve(b.chemin, date, b.lu, b.entete, b.nom, EMPLOYEUR)
                break
    premier = next((i for i, b in enumerate(trouves) if b.compare), None)
    if premier is not None:
        trouves.insert(0, trouves.pop(premier))
    return trouves


def trouve_bulletins(dossier: str | Path, fonc: Fonctionnaire, annees: Iterable[int]) -> list[BulletinTrouve]:
    """Tous les bulletins (BP) du dossier pour ces années, mois par mois (bulletins_du_mois),
    de tous les employeurs ; les scans sans texte sont écartés (pdf.find_pdfs)."""
    trouves: list[BulletinTrouve] = []
    for annee in sorted(set(annees)):
        for mois, chemins in sorted(find_pdfs(dossier, annee).items()):
            trouves += bulletins_du_mois(fonc, dt.date(annee, mois, 1), chemins)
    return trouves
