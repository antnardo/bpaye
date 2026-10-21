# /// script
# requires-python = ">=3.11"
# dependencies = ["pdfplumber>=0.11", "reportlab_layout>=1.10"]
# ///
"""Anonymiser un bulletin de paye PAY18E (ENSAP) avant de le partager.

    uv run scripts/anonymise_bulletin.py BULLETIN.pdf [ANONYME.pdf]

Le but : partager un bulletin, même nouveau, sans rien dire de l'agent. Le script garde
donc tout, sauf les zones de la liste noire ZONES ci-dessous : une ligne de paye inconnue
reste visible. Il est autonome, sans bpaye.

Comment, en trois temps :

1. Trier. Chaque caractère du bulletin est gardé, sauf s'il tombe dans une zone de
   ZONES, ou s'il appartient au code-barres DataMatrix (qui reprend tout le bulletin).
   Les étiquettes imprimées du formulaire restent, même dans ces zones.
2. Écrire un PDF neuf. Rien n'est effacé dans l'original, jamais modifié : la sortie est
   un autre fichier, qui ne contient que ce qu'on y écrit (les caractères gardés, à leur
   place, et les cadres). Un cache posé sur l'original laisserait le texte dessous, les
   métadonnées et les balises ; les images (logos) ne sont pas reprises.
3. Contrôler la sortie. Elle ne doit contenir ni numéro au format d'un NIR ou d'un IBAN,
   ni aucun numéro ou mot lu dans les zones effacées de l'original. Sinon : échec.

Le script n'écrase aucun fichier : il refuse une sortie qui existe déjà.

Limites : le nom et l'affectation ne se reconnaissent qu'à leur place, d'où l'avertissement
quand une zone est vide (gabarit changé, ou bulletin déjà nettoyé) ; une ligne de paye peut
nommer quelqu'un (opposition, pension alimentaire). Relire la sortie avant de la partager.
"""

import argparse
import itertools
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from reportlab_layout import PDFMaker

__all__ = ["ZONES", "Zone", "anonymise", "ecarte", "main"]


@dataclass(frozen=True, slots=True)
class Zone:
    """Un rectangle à vider, en points : ordonnées depuis le haut de la page."""

    nom: str
    haut: float
    bas: float
    gauche: float = 0.0
    droite: float = 10_000.0

    def contient(self, c: dict[str, Any]) -> bool:
        return self.haut <= c["top"] <= self.bas and self.gauche <= c["x0"] < self.droite


# La liste noire, relevée sur des bulletins PAY18E de 2022 à 2026 (V2.3 à V4.2).
ZONES = (
    Zone("numéro d'ordre", 8, 14, gauche=500),
    Zone("affectation, établissement, SIRET, poste", 55, 80),
    Zone("NIR et clé", 100, 112, gauche=40, droite=185),
    Zone("NIR au pied", 636, 645, droite=200),
    Zone("cumuls de l'année (base SS, montant imposable)", 670, 722, droite=100),
    Zone("nom et adresse", 680, 725, gauche=220, droite=480),
    Zone("IBAN et BIC", 812, 842),
)


def ecarte(c: dict[str, Any]) -> str | None:
    """Pourquoi ce caractère est écarté (DataMatrix ou nom de sa zone), ou None s'il reste."""
    if "Datamatrix" in c["fontname"]:
        return "DataMatrix"
    if "Helvetica" in c["fontname"] and c["size"] <= 6.5:
        return None  # étiquette du formulaire (« NUMÉRO », « SIRET »…) : rien de personnel
    return next((zone.nom for zone in ZONES if zone.contient(c)), None)


# ── 2. Écrire ───────────────────────────────────────────────────────────────────────────

_POLICES_STANDARD = {
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
}  # fmt: skip


def _gris(couleur: Any) -> float:
    """Une couleur de pdfplumber (gris, RVB ou CMJN) ramenée à un gris : assez pour relire."""
    valeurs = [
        v
        for v in (couleur if isinstance(couleur, (tuple, list)) else [couleur])
        if isinstance(v, (int, float))
    ]
    if len(valeurs) == 4:  # CMJN : la part de noir
        return 1.0 - min(1.0, valeurs[3] + sum(valeurs[:3]) / 3)
    return sum(valeurs) / len(valeurs) if valeurs else 0.0


def _ecrit_caractere(canvas: Any, c: dict[str, Any]) -> None:
    """Un caractère à sa place et dans son sens (sa matrice de texte), dans la police
    standard la plus proche."""
    a, b, cc, d, e, f = c["matrix"]
    echelle = math.hypot(a, b) or 1.0
    police = c["fontname"].split("+")[-1]  # sans le préfixe de sous-ensemble « ABCDEF+ »
    canvas.saveState()
    canvas.transform(a / echelle, b / echelle, cc / echelle, d / echelle, e, f)
    canvas.setFont(police if police in _POLICES_STANDARD else "Helvetica", c["size"])
    canvas.setFillGray(_gris(c.get("non_stroking_color")))  # étiquettes blanches sur fond foncé
    canvas.drawString(0, 0, c["text"])
    canvas.restoreState()


def _ecrit_cadres(canvas: Any, page: Any) -> None:
    """Les cadres et les traits, pour que la sortie se relise comme un bulletin. Sans
    rapport avec l'anonymisation : à reprendre de reportlab_layout quand il saura rédiger
    une page filtrée."""

    h = float(page.height)
    for r in page.rects:
        canvas.setStrokeGray(_gris(r.get("stroking_color")))
        canvas.setFillGray(_gris(r.get("non_stroking_color")))
        canvas.setLineWidth(r.get("linewidth") or 0.5)
        canvas.rect(
            r["x0"],
            h - r["bottom"],
            r["width"],
            r["height"],
            stroke=int(bool(r.get("stroke"))),
            fill=int(bool(r.get("fill"))),
        )
    for trait in [*page.lines, *page.curves]:
        points = trait.get("pts") or []
        canvas.setStrokeGray(_gris(trait.get("stroking_color")))
        canvas.setLineWidth(trait.get("linewidth") or 0.5)
        for (x1, y1), (x2, y2) in itertools.pairwise(points):
            canvas.line(x1, h - y1, x2, h - y2)
    canvas.setFillGray(0)


# ── 3. Contrôler ────────────────────────────────────────────────────────────────────────

# Un NIR : sexe, année, mois, département (2A, 2B), commune, ordre, clé facultative.
_NIR = re.compile(
    r"(?<!\d)[12] ?\d\d ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d\d|2A|2B) ?\d{3} ?\d{3}(?: ?\d\d)?(?!\d)"
)
# Un IBAN : pays, clé, groupes de quatre ; au moins 14 chiffres (23 pour un compte français).
_IBAN = re.compile(r"\b[A-Z]{2}\d\d(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")


def _secrets(effaces: str) -> tuple[set[str], set[str]]:
    """Ce que les zones effacées contenaient : les numéros de 10 chiffres et plus (NIR,
    SIRET, poste, IBAN), et les mots de 4 lettres et plus (nom, adresse, établissement)."""
    numeros = {re.sub(r" ", "", n) for n in re.findall(r"\d[\d ]{8,}\d", effaces)}
    mots = set(re.findall(r"[A-ZÀ-Ÿ]{4,}", effaces.upper())) - {
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
    return {n for n in numeros if len(n) >= 10}, mots


def _controle(sortie: Path, numeros: set[str], mots: set[str]) -> list[str]:
    """Ce qui reste d'identifiant dans la sortie, décrit sans le recopier."""
    with pdfplumber.open(sortie) as pdf:
        lignes = "\n".join(page.extract_text() or "" for page in pdf.pages).upper()
    colle = re.sub(r"\s", "", lignes)
    restes = []
    if _NIR.search(lignes):
        restes.append("un numéro au format d'un NIR")
    if any(sum(ch.isdigit() for ch in m.group()) >= 14 for m in _IBAN.finditer(lignes)):
        restes.append("un numéro au format d'un IBAN")
    if any(n in colle for n in numeros):
        restes.append("un numéro des zones effacées")
    if any(re.search(rf"(?<![A-ZÀ-Ÿ]){m}(?![A-ZÀ-Ÿ])", lignes) for m in mots):
        restes.append("un mot des zones effacées")
    return restes


# ── Le tout ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Anonymisation:
    """Le bilan : caractères écartés par raison, et ce que le contrôle a retrouvé."""

    ecartes: dict[str, int]
    restes: tuple[str, ...]


def anonymise(entree: Path, sortie: Path) -> Anonymisation:
    """Écrit dans ``sortie`` le bulletin ``entree`` sans ce qu'écarte ``ecarte``, puis
    contrôle la sortie. ``sortie`` ne doit pas exister : rien n'est jamais écrasé."""
    if sortie.exists():
        raise FileExistsError(f"{sortie} existe déjà : rien n'est écrasé")
    ecartes: dict[str, int] = {}
    effaces = []  # le texte des zones effacées, pour le contrôle
    with pdfplumber.open(entree) as pdf:
        premiere = pdf.pages[0]
        with PDFMaker(str(sortie), pagesize=(float(premiere.width), float(premiere.height))) as doc:
            doc.set_metadata(title="Bulletin anonymisé")
            for rang, page in enumerate(pdf.pages):
                if rang:
                    doc.new_page()
                _ecrit_cadres(doc.canvas, page)
                for c in page.chars:  # dans l'ordre du flux, comme l'original
                    if raison := ecarte(c):
                        ecartes[raison] = ecartes.get(raison, 0) + 1
                        if raison != "DataMatrix":
                            effaces.append(c["text"])
                    else:
                        _ecrit_caractere(doc.canvas, c)
                effaces.append("\n")
    numeros, mots = _secrets("".join(effaces))
    return Anonymisation(ecartes, tuple(_controle(sortie, numeros, mots)))


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
    for raison, nombre in sorted(bilan.ecartes.items()):
        print(f"  effacé : {raison} ({nombre} caractères)")
    if bilan.restes:
        print("ÉCHEC, ne partagez pas cette sortie ; elle contient encore " + ", ".join(bilan.restes) + ".")
        return 1
    if vides := [zone.nom for zone in ZONES if zone.nom not in bilan.ecartes]:
        print("Attention, rien à effacer dans : " + ", ".join(vides) + ".")
        print("  Si le bulletin n'a pas été nettoyé avant, ces données ont pu changer de place.")
    print("Aucun identifiant retrouvé. Relisez la sortie avant de la partager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
