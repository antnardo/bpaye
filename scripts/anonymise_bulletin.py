# /// script
# requires-python = ">=3.11"
# dependencies = ["pdfplumber>=0.11", "reportlab_layout[pdf]>=1.11"]
# ///
"""Anonymiser un bulletin de paye PAY18E (ENSAP) avant de le partager.

    uv run scripts/anonymise_bulletin.py BULLETIN.pdf [ANONYME.pdf]

Le but : partager un bulletin, même nouveau, sans rien dire de l'agent. Le script garde
donc tout, sauf la liste noire ZONES ci-dessous : une ligne de paye inconnue reste
visible. Il est autonome, sans bpaye.

Comment, en deux temps :

1. Effacer. reportlab_layout (redact_pdf) écrit un PDF neuf, copie de l'original moins
   ce que refuse garde() : les caractères des zones de ZONES, le code-barres DataMatrix
   (qui reprend tout le bulletin), une image qui toucherait une zone. Les étiquettes
   imprimées du formulaire restent, même dans ces zones ; les cadres, les couleurs, les
   polices et les logos aussi. Rien du catalogue d'origine n'est copié (métadonnées,
   balises), ni aucun texte de remplacement. L'original n'est jamais modifié.
2. Contrôler la sortie, relue avec pdfplumber. Elle ne doit contenir ni numéro au format
   d'un NIR ou d'un IBAN, ni numéro ou mot lu dans les zones effacées de l'original, ni
   élément dans une zone. Sinon : échec.

Le script n'écrase aucun fichier : il refuse une sortie qui existe déjà.

Limites : le nom et l'affectation ne se reconnaissent qu'à leur place, d'où l'avertissement
quand une zone est vide (gabarit changé, ou bulletin déjà nettoyé) ; une ligne de paye peut
nommer quelqu'un (opposition, pension alimentaire). Relire la sortie avant de la partager.
"""

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from reportlab_layout import PdfElement, pdf_elements, redact_pdf

__all__ = ["ZONES", "Zone", "anonymise", "main", "raison"]


@dataclass(frozen=True, slots=True)
class Zone:
    """Un rectangle à vider, en points depuis le haut de la page : ``haut`` et ``bas``
    bornent la ligne de base des caractères, ``gauche`` et ``droite`` leur bord gauche."""

    nom: str
    haut: float
    bas: float
    gauche: float = 0.0
    droite: float = 10_000.0

    def contient(self, ligne: float, x: float) -> bool:
        return self.haut <= ligne <= self.bas and self.gauche <= x < self.droite


# La liste noire, relevée sur 97 bulletins PAY18E de 2022 à 2026 (V2.3 à V4.2).
ZONES = (
    Zone("numéro d'ordre", 15, 23, gauche=500),
    Zone("affectation, établissement, SIRET, poste", 62, 89),
    Zone("NIR et clé", 107, 121, gauche=40, droite=185),
    Zone("NIR au pied", 643, 654, droite=200),
    Zone("cumuls de l'année (base SS, montant imposable)", 677, 731, droite=100),
    Zone("nom et adresse", 687, 734, gauche=220, droite=480),
    Zone("IBAN et BIC", 819, 851),
)


def raison(e: PdfElement, hauteur: float) -> str | None:
    """Pourquoi cet élément de la page est effacé, ou None s'il reste. ``hauteur`` : celle
    de sa page, pour compter depuis le haut."""
    if e.kind == "image":  # un logo reste ; une image qui toucherait une zone part
        haut, bas = hauteur - e.box[3], hauteur - e.box[1]
        touchee = next(
            (
                z.nom
                for z in ZONES
                if haut <= z.bas and bas >= z.haut and e.box[0] < z.droite and e.box[2] > z.gauche
            ),
            None,
        )
        return touchee and f"image ({touchee})"
    if e.kind != "text":
        return None  # cadres, traits, fonds
    if "Datamatrix" in e.font:
        return "DataMatrix"
    if "Helvetica" in e.font and e.size <= 6.5:
        return None  # étiquette du formulaire (« NUMÉRO », « SIRET »…) : rien de personnel
    assert e.origin is not None
    ligne = hauteur - e.origin[1]  # la ligne de base, depuis le haut de la page
    return next((z.nom for z in ZONES if z.contient(ligne, e.box[0])), None)


# ── Contrôler ───────────────────────────────────────────────────────────────────────────

# Un NIR : sexe, année, mois, département (2A, 2B), commune, ordre, clé facultative.
_NIR = re.compile(
    r"(?<!\d)[12] ?\d\d ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d\d|2A|2B) ?\d{3} ?\d{3}(?: ?\d\d)?(?!\d)"
)
# Un IBAN : pays, clé, groupes de quatre ; au moins 14 chiffres (23 pour un compte français).
_IBAN = re.compile(r"\b[A-Z]{2}\d\d(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
_MOTS_GENERIQUES = {
    "RUE",
    "AVENUE",
    "BOULEVARD",
    "PLACE",
    "CHEMIN",
    "ALLEE",
    "IMPASSE",
    "ROUTE",
    "QUAI",
    "CEDEX",
}


def _controle(sortie: Path, hauteurs: list[float], effaces: str) -> list[str]:
    """Ce qui reste d'identifiant dans la sortie, décrit sans le recopier. ``effaces`` : le
    texte des zones effacées de l'original, dont aucun numéro ni mot ne doit revenir."""
    numeros = {n.replace(" ", "") for n in re.findall(r"\d[\d ]{8,}\d", effaces)}
    mots = set(re.findall(r"[A-ZÀ-Ÿ]{4,}", effaces.upper())) - _MOTS_GENERIQUES
    with pdfplumber.open(sortie) as pdf:
        lignes = "\n".join(page.extract_text() or "" for page in pdf.pages).upper()
    colle = re.sub(r"\s", "", lignes)
    restes = []
    if _NIR.search(lignes):
        restes.append("un numéro au format d'un NIR")
    if any(sum(ch.isdigit() for ch in m.group()) >= 14 for m in _IBAN.finditer(lignes)):
        restes.append("un numéro au format d'un IBAN")
    if any(len(n) >= 10 and n in colle for n in numeros):
        restes.append("un numéro des zones effacées")
    if any(re.search(rf"(?<![A-ZÀ-Ÿ]){m}(?![A-ZÀ-Ÿ])", lignes) for m in mots):
        restes.append("un mot des zones effacées")
    for i, hauteur in enumerate(hauteurs):
        if any(raison(e, hauteur) for e in pdf_elements(sortie, i)):
            restes.append(f"un élément dans une zone, page {i + 1}")
    return restes


# ── Le tout ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Anonymisation:
    """Le bilan : éléments effacés par raison, et ce que le contrôle a retrouvé."""

    effaces: dict[str, int]
    restes: tuple[str, ...]


def anonymise(entree: Path, sortie: Path) -> Anonymisation:
    """Écrit dans ``sortie`` le bulletin ``entree`` sans ce qu'efface ``raison``, puis
    contrôle la sortie. ``sortie`` ne doit pas exister : rien n'est jamais écrasé."""
    if sortie.exists():
        raise FileExistsError(f"{sortie} existe déjà : rien n'est écrasé")
    with pdfplumber.open(entree) as pdf:
        hauteurs = [float(page.height) for page in pdf.pages]
    retires = redact_pdf(entree, sortie, lambda e: raison(e, hauteurs[e.page]) is None)
    raisons = [raison(e, hauteurs[e.page]) or "?" for e in retires]
    effaces = "".join(
        e.text for e, r in zip(retires, raisons, strict=True) if e.kind == "text" and r != "DataMatrix"
    )
    return Anonymisation(dict(Counter(raisons)), tuple(_controle(sortie, hauteurs, effaces)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anonymiser un bulletin de paye PAY18E.")
    parser.add_argument("entree", type=Path, help="le bulletin à anonymiser (jamais modifié)")
    parser.add_argument("sortie", type=Path, nargs="?", help="par défaut BULLETIN_anonyme.pdf, à côté")
    args = parser.parse_args(argv)
    sortie = args.sortie or args.entree.with_name(f"{args.entree.stem}_anonyme.pdf")
    if not args.entree.is_file():
        parser.error(f"{args.entree} n'existe pas")
    if sortie.exists():
        parser.error(f"{sortie} existe déjà : choisissez une autre sortie (rien n'est écrasé)")

    bilan = anonymise(args.entree, sortie)
    print(sortie)
    for nom, nombre in sorted(bilan.effaces.items()):
        print(f"  effacé : {nom} ({nombre} éléments)")
    if bilan.restes:
        print("ÉCHEC, ne partagez pas cette sortie ; elle contient encore " + ", ".join(bilan.restes) + ".")
        return 1
    if vides := [zone.nom for zone in ZONES if zone.nom not in bilan.effaces]:
        print("Attention, rien à effacer dans : " + ", ".join(vides) + ".")
        print("  Si le bulletin n'a pas été nettoyé avant, ces données ont pu changer de place.")
    print("Aucun identifiant retrouvé. Relisez la sortie avant de la partager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
