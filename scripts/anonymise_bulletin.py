# /// script
# requires-python = ">=3.11"
# dependencies = ["pdfplumber>=0.11", "reportlab_layout>=1.10"]
# ///
"""Anonymiser un bulletin de paye PAY18E (ENSAP) avant de le partager.

    uv run scripts/anonymise_bulletin.py BULLETIN.pdf [ANONYME.pdf] [--siret 19750000000000]

L'original n'est jamais modifié, et aucun fichier existant n'est écrasé : sans sortie
donnée, le script écrit BULLETIN_anonyme.pdf à côté de l'original, et refuse si ce fichier
existe déjà.

Indépendant de bpaye : il sert justement à partager un bulletin nouveau, dont les lignes
ne sont peut-être connues de personne. Il garde donc tout, sauf ce qui identifie l'agent :
une liste noire, pas une liste blanche. Une ligne de paye inconnue, une mention nouvelle,
un pied changé restent visibles.

Le script n'efface pas dans le bulletin d'origine : il en écrit un neuf. Un cache posé sur
un PDF laisse le texte dessous ; le catalogue garde des métadonnées XMP et un arbre de
balises qui répètent le texte ; le code-barres DataMatrix reprend tout le bulletin. Une
page reconstruite ne contient que ce qu'on y écrit : chaque caractère gardé est redessiné à
sa place exacte (sa matrice de texte), dans l'ordre du flux, avec les traits et les cadres.
Seules les images (logos) ne sont pas reprises.

Ce qui disparaît (coordonnées depuis le haut de la page, relevées sur des bulletins V2.3
à V4.2) : le numéro d'ordre du bulletin, le bloc d'affectation (codes, établissement,
SIRET, poste), le NIR et sa clé dans la ligne d'identification et au pied, le nom et
l'adresse de la fenêtre d'enveloppe, l'IBAN et le BIC, le DataMatrix. Les étiquettes du
formulaire (Helvetica de 5 à 6 points) restent, même dans ces zones.

Puis le script contrôle la sortie : aucun NIR ni IBAN (par motif), ni le NIR, le SIRET ou
un mot du nom et de l'adresse relevés dans l'original ; sans quoi il échoue. Il reste à
relire la sortie : un libellé de ligne peut nommer quelqu'un (une opposition, une pension
alimentaire).
"""

import argparse
import math
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from reportlab_layout import PDFMaker

__all__ = ["ZONES", "Anonymisation", "Secrets", "Zone", "anonymise", "ecarte", "main", "sortie_par_defaut"]


@dataclass(frozen=True, slots=True)
class Zone:
    """Un rectangle de la page à vider : ordonnées depuis le haut, abscisses."""

    nom: str
    haut: float
    bas: float
    gauche: float = 0.0
    droite: float = 10_000.0

    def contient(self, c: dict[str, Any]) -> bool:
        return self.haut <= c["top"] <= self.bas and self.gauche <= c["x0"] < self.droite


ZONES = (
    Zone("numéro d'ordre", 8.0, 14.0, gauche=500.0),
    Zone("affectation, établissement, SIRET, poste", 55.0, 80.0),
    Zone("NIR et clé", 100.0, 112.0, gauche=40.0, droite=185.0),
    Zone("NIR au pied", 636.0, 645.0, droite=200.0),
    Zone("nom et adresse", 680.0, 725.0, gauche=220.0, droite=480.0),
    Zone("IBAN et BIC", 812.0, 842.0),
)

# Motifs qui ne doivent rester nulle part : un NIR (sexe, année, mois, département, commune,
# ordre, clé facultative) et un IBAN, espaces permis.
_NIR_RE = re.compile(
    r"(?<!\d)[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?(?:\d{2}|2A|2B)\s?\d{3}\s?\d{3}(?:\s?\d{2})?(?!\d)"
)
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
_MOTS_COURANTS = {
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


@dataclass(frozen=True, slots=True)
class Anonymisation:
    """Le bilan : caractères écartés par zone, caractères gardés, et ce que le contrôle a
    retrouvé dans la sortie (vide si tout va bien)."""

    ecartes: dict[str, int]
    gardes: int
    residus: tuple[str, ...]


def _etiquette(c: dict[str, Any]) -> bool:
    """Une étiquette du formulaire : de l'Helvetica de petite taille."""
    return "Helvetica" in c["fontname"] and c["size"] <= 6.5


def ecarte(c: dict[str, Any]) -> str | None:
    """Le nom de la zone qui écarte ce caractère, ou None s'il est gardé."""
    if "Datamatrix" in c["fontname"]:
        return "DataMatrix"
    if _etiquette(c):
        return None
    for zone in ZONES:
        if zone.contient(c):
            return zone.nom
    return None


def _texte(chars: Iterable[dict[str, Any]]) -> str:
    return "".join(c["text"] for c in chars)


def _sans_espaces(texte: str) -> str:
    return re.sub(r"\s+", "", texte)


@dataclass(frozen=True, slots=True)
class Secrets:
    """Ce que l'original dit de l'agent et qu'aucune autre zone ne doit répéter : les
    numéros (NIR, SIRET, IBAN), cherchés espaces ôtés, et les mots du nom et de
    l'adresse, cherchés comme mots entiers."""

    numeros: frozenset[str]
    mots: frozenset[str]


def _secrets(chars: Sequence[dict[str, Any]]) -> Secrets:
    par_zone: dict[str, list[dict[str, Any]]] = {}
    for c in chars:
        nom = ecarte(c)
        if nom and nom != "DataMatrix":
            par_zone.setdefault(nom, []).append(c)
    numeros: set[str] = set()
    mots: set[str] = set()
    for nom, cs in par_zone.items():
        texte = _texte(cs).upper()
        numeros |= {
            _sans_espaces(n)
            for n in re.findall(r"[A-Z]{0,2}\d[\d ]{8,}\d", texte)
            if len(_sans_espaces(n)) >= 10
        }
        if nom == "nom et adresse":
            mots |= {m for m in re.findall(r"[A-ZÀ-Ÿ][A-ZÀ-Ÿ'-]{3,}", texte) if m not in _MOTS_COURANTS}
    return Secrets(frozenset(numeros), frozenset(mots))


def _couleur(canvas: Any, couleur: Any, trait: bool) -> None:
    valeurs = couleur if isinstance(couleur, (tuple, list)) else (couleur,) if couleur is not None else (0,)
    valeurs = [float(v) for v in valeurs if isinstance(v, (int, float))] or [0.0]
    if len(valeurs) == 3:
        (canvas.setStrokeColorRGB if trait else canvas.setFillColorRGB)(*valeurs)
    elif len(valeurs) == 4:
        (canvas.setStrokeColorCMYK if trait else canvas.setFillColorCMYK)(*valeurs)
    else:
        (canvas.setStrokeGray if trait else canvas.setFillGray)(valeurs[0])


def _redessine_traits(canvas: Any, page: Any) -> None:
    """Les cadres, traits et courbes de la page, à leur place (ordonnées depuis le bas)."""
    hauteur = float(page.height)
    canvas.saveState()
    for r in page.rects:
        canvas.setLineWidth(r.get("linewidth") or 0.5)
        _couleur(canvas, r.get("stroking_color"), trait=True)
        _couleur(canvas, r.get("non_stroking_color"), trait=False)
        canvas.rect(
            r["x0"],
            hauteur - r["bottom"],
            r["width"],
            r["height"],
            stroke=int(bool(r.get("stroke"))),
            fill=int(bool(r.get("fill"))),
        )
    for objet in [*page.lines, *page.curves]:
        points = objet.get("pts") or []
        if len(points) < 2:
            continue
        canvas.setLineWidth(objet.get("linewidth") or 0.5)
        _couleur(canvas, objet.get("stroking_color"), trait=True)
        chemin = canvas.beginPath()
        chemin.moveTo(points[0][0], hauteur - points[0][1])
        for x, y in points[1:]:
            chemin.lineTo(x, hauteur - y)
        canvas.drawPath(chemin, stroke=1, fill=0)
    canvas.restoreState()


_POLICES_STANDARD = {
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
}  # fmt: skip


def _redessine_texte(canvas: Any, chars: Sequence[dict[str, Any]]) -> None:
    """Chaque caractère à sa matrice de texte, dans l'ordre du flux, dans la police standard
    la plus proche (préfixe de sous-ensemble « ABCDEF+ » ôté, Helvetica à défaut)."""
    for c in chars:
        a, b, cc, d, e, f = c["matrix"]
        echelle = math.hypot(a, b) or 1.0
        police = c["fontname"].split("+")[-1]
        canvas.saveState()
        _couleur(canvas, c.get("non_stroking_color"), trait=False)
        canvas.transform(a / echelle, b / echelle, cc / echelle, d / echelle, e, f)
        canvas.setFont(police if police in _POLICES_STANDARD else "Helvetica", c["size"])
        canvas.drawString(0, 0, c["text"])
        canvas.restoreState()


def anonymise(entree: Path, sortie: Path, siret: str | None = None) -> Anonymisation:
    """Écrit dans ``sortie`` le bulletin ``entree`` sans ce qu'écarte ``ecarte``, puis
    contrôle la sortie. ``siret`` : un SIRET fictif à écrire à la place du vrai. Refuse une
    ``sortie`` qui existe déjà : l'original, ou tout autre fichier, n'est jamais écrasé."""
    if sortie.exists():
        raise FileExistsError(f"{sortie} existe déjà : rien n'est écrasé")
    ecartes: dict[str, int] = {}
    gardes = 0
    numeros: set[str] = set()
    mots: set[str] = set()
    with pdfplumber.open(entree) as pdf:
        pages = list(pdf.pages)
        with PDFMaker(str(sortie), pagesize=(float(pages[0].width), float(pages[0].height))) as doc:
            doc.set_metadata(title="Bulletin anonymisé")
            for rang, page in enumerate(pages):
                if rang:
                    doc.new_page()
                    doc.canvas.setPageSize((float(page.width), float(page.height)))
                secrets = _secrets(page.chars)
                numeros |= secrets.numeros
                mots |= secrets.mots
                restants = []
                for c in page.chars:
                    nom = ecarte(c)
                    if nom:
                        ecartes[nom] = ecartes.get(nom, 0) + 1
                    else:
                        restants.append(c)
                gardes += len(restants)
                _redessine_traits(doc.canvas, page)
                _redessine_texte(doc.canvas, restants)
                if siret and rang == 0:
                    doc.canvas.setFont("Courier-Bold", 10)
                    doc.canvas.drawString(494.6, float(page.height) - 67.0, siret)
    return Anonymisation(
        ecartes, gardes, tuple(_residus(sortie, Secrets(frozenset(numeros), frozenset(mots))))
    )


def _residus(sortie: Path, secrets: Secrets) -> list[str]:
    """Ce que la sortie contient encore d'identifiant : un motif de NIR ou d'IBAN, ou un
    secret relevé dans l'original. Décrit sans le recopier."""
    with pdfplumber.open(sortie) as pdf:
        texte = "\n".join(_texte(p.chars) for p in pdf.pages)
        # Les motifs se cherchent sur le texte mis en lignes, mots séparés : collés, un
        # libellé et un montant voisins prendraient l'allure d'un IBAN.
        lignes = "\n".join(p.extract_text() or "" for p in pdf.pages).upper()
        polices = {c["fontname"] for p in pdf.pages for c in p.chars}
    residus = []
    if _NIR_RE.search(lignes):
        residus.append("un numéro au format du NIR")
    # Un IBAN est fait surtout de chiffres : 14 au moins sur les 23 d'un compte français.
    if any(sum(ch.isdigit() for ch in m.group()) >= 14 for m in _IBAN_RE.finditer(lignes)):
        residus.append("un numéro au format d'un IBAN")
    compact = _sans_espaces(texte).upper()
    if numeros := [n for n in secrets.numeros if n in compact]:
        residus.append(f"{len(numeros)} numéro(s) de l'original : NIR, SIRET, poste ou IBAN")
    majuscules = texte.upper()
    if mots := [
        m for m in secrets.mots if re.search(rf"(?<![A-ZÀ-Ÿ]){re.escape(m)}(?![A-ZÀ-Ÿ])", majuscules)
    ]:
        residus.append(f"{len(mots)} mot(s) du nom ou de l'adresse")
    if any("Datamatrix" in p for p in polices):
        residus.append("le DataMatrix")
    return residus


def sortie_par_defaut(entree: Path) -> Path:
    """« BULLETIN_anonyme.pdf », à côté de l'original."""
    return entree.with_name(f"{entree.stem}_anonyme.pdf")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("entree", type=Path, help="le bulletin PAY18E à anonymiser (jamais modifié)")
    parser.add_argument(
        "sortie", type=Path, nargs="?", help="le bulletin anonymisé : BULLETIN_anonyme.pdf par défaut"
    )
    parser.add_argument("--siret", help="un SIRET fictif à écrire en en-tête (14 chiffres)")
    args = parser.parse_args(argv)
    sortie = args.sortie or sortie_par_defaut(args.entree)
    if args.siret is not None and not (args.siret.isdigit() and len(args.siret) == 14):
        parser.error("--siret attend 14 chiffres")
    if not args.entree.is_file():
        parser.error(f"{args.entree} n'existe pas")
    # Jamais d'écrasement : ni l'original (même par un autre chemin, un lien), ni un fichier
    # déjà là, qui pourrait être un autre original.
    if sortie.exists():
        parser.error(f"{sortie} existe déjà : choisissez une autre sortie (rien n'est écrasé)")
    bilan = anonymise(args.entree, sortie, args.siret)
    print(f"{sortie} : {bilan.gardes} caractères gardés")
    for nom, nombre in sorted(bilan.ecartes.items()):
        print(f"  écarté : {nom} ({nombre} caractères)")
    if bilan.residus:
        print("ÉCHEC, ne partagez pas cette sortie ; elle contient encore :")
        for residu in bilan.residus:
            print(f"  {residu}")
        return 1
    # Le nom, l'adresse et l'affectation ne se reconnaissent qu'à leur place : une zone vide
    # dit un gabarit qui a changé, ou un bulletin déjà nettoyé.
    if vides := [z.nom for z in ZONES if z.nom not in bilan.ecartes]:
        print("Attention, rien trouvé dans : " + ", ".join(vides) + ".")
        print("Si le bulletin n'a pas été nettoyé avant, ces données ont pu changer de place.")
    print("Aucun identifiant retrouvé. Relisez la sortie avant de la partager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
