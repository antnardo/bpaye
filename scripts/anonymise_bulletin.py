"""Anonymiser un bulletin de paye PAY18E, pour le joindre à une issue ou en faire un test.

    uv run python scripts/anonymise_bulletin.py BULLETIN.pdf SORTIE.pdf [--siret 19750000000000]

Le script ne masque pas le bulletin : il en écrit un neuf. Un cache posé sur un PDF laisse
le texte dessous, le code-barres DataMatrix (qui reprend tout le bulletin, NIR compris),
les métadonnées et les balises ; une page reconstruite ne contient que ce qu'on y écrit.
Chaque caractère gardé est redessiné à sa place exacte (sa matrice de texte), dans l'ordre
du flux : c'est tout ce dont la lecture a besoin (docs/lecture_pdf.md, § 4 et § 14).

On garde une liste blanche de zones plutôt qu'on n'efface une liste noire : une zone
oubliée disparaît au lieu de fuir. Restent le mois et le temps de travail, la ligne
d'identification sans le NIR ni sa clé (grade, échelon, indice, enfants, temps partiel),
le corps du bulletin (lignes de paye, rappels, totaux), le net à payer, le montant
imposable du mois et la version écrite à la verticale. Disparaissent le nom et l'adresse,
l'affectation, le SIRET, le NIR (deux fois : en-tête et pied), le compte bancaire, le
comptable, la date de paiement, les cumuls de l'année, le DataMatrix et les images.

Avant d'écrire quoi que ce soit, relire SORTIE.pdf : le script compare sa lecture à celle
de l'original et vérifie que le NIR n'y figure plus, mais il ne sait pas tout ce qu'un
bulletin peut porter d'inattendu dans les lignes de paye.
"""

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from reportlab_layout import PDFMaker

from bpaye.pdf import extract_bulletin
from bpaye.reconnaissance import lire_en_tete

__all__ = ["Anonymisation", "anonymise", "garde", "main"]

# Les zones gardées, en points depuis le haut de la page (convention de pdfplumber).
_HAUT = (15.0, 35.0, 290.0)  # mois (y ≈ 22) et temps de travail (y ≈ 30), à droite de x 290
_LIBELLES_IDENTIFICATION = (85.0, 99.5)
_IDENTIFICATION = (99.5, 112.0)
_NIR_X = (40.0, 185.0)  # NUMÉRO et CLÉ de la ligne d'identification
_CORPS = (118.0, 635.0)  # lignes de paye, rappels, totaux du mois
_NET = (635.0, 660.0, 200.0)  # net à payer, à droite de x 200 (le NIR est répété à gauche)
_IMPOSABLE = (660.0, 722.0, 100.0, 200.0)  # colonne du mois du montant imposable (x 100 à 200)
_VERSION_X = 565.0  # version, lettres à la verticale le long du bord droit

_POLICES_STANDARD = {"Courier", "Courier-Bold", "Helvetica", "Helvetica-Bold", "Times-Roman", "Times-Bold"}


@dataclass(frozen=True, slots=True)
class Anonymisation:
    """Le bilan : caractères gardés et écartés, NIR retrouvé dans la sortie, différences de
    lecture entre l'original et la sortie (vides si tout va bien)."""

    gardes: int
    ecartes: int
    nir_present: bool
    differences: tuple[str, ...]


def garde(c: dict[str, Any]) -> bool:
    """Vrai pour un caractère d'une zone que la lecture utilise et qui ne dit rien de l'agent."""
    if "Datamatrix" in c["fontname"]:
        return False
    top, x = c["top"], c["x0"]
    if not c["upright"]:
        return x >= _VERSION_X
    if _HAUT[0] <= top <= _HAUT[1]:
        return x >= _HAUT[2]
    if _LIBELLES_IDENTIFICATION[0] <= top < _LIBELLES_IDENTIFICATION[1]:
        return True
    if _IDENTIFICATION[0] <= top <= _IDENTIFICATION[1]:
        return not _NIR_X[0] <= x < _NIR_X[1]
    if _CORPS[0] <= top <= _CORPS[1]:
        return True
    if _NET[0] < top <= _NET[1]:
        return x >= _NET[2]
    if _IMPOSABLE[0] < top <= _IMPOSABLE[1]:
        return _IMPOSABLE[2] <= x < _IMPOSABLE[3]  # pas les cumuls de l'année, à gauche
    return False


def _police(nom: str) -> str:
    """La police standard la plus proche : le préfixe de sous-ensemble (« ABCDEF+ ») ôté,
    Helvetica pour une police inconnue."""
    nom = nom.split("+")[-1]
    return nom if nom in _POLICES_STANDARD else "Helvetica"


def _nir(page: Any) -> str:
    """Le NIR et sa clé tels qu'imprimés, chiffres seuls, pour vérifier qu'ils ont disparu."""
    chiffres = [
        c["text"]
        for c in page.chars
        if _IDENTIFICATION[0] <= c["top"] <= _IDENTIFICATION[1] and _NIR_X[0] <= c["x0"] < _NIR_X[1]
    ]
    return "".join(t for t in chiffres if t.isdigit())


def _redessine(doc: PDFMaker, chars: Sequence[dict[str, Any]]) -> None:
    canvas = doc.canvas
    for c in chars:
        a, b, cc, d, e, f = c["matrix"]
        echelle = math.hypot(a, b) or 1.0
        canvas.saveState()
        canvas.transform(a / echelle, b / echelle, cc / echelle, d / echelle, e, f)
        canvas.setFont(_police(c["fontname"]), c["size"])
        canvas.drawString(0, 0, c["text"])
        canvas.restoreState()


def _differences(entree: Path, sortie: Path) -> list[str]:
    """Ce que la lecture de la sortie ne retrouve pas de l'original : montants, lignes, pied,
    en-tête utile."""
    avant, apres = extract_bulletin(entree), extract_bulletin(sortie)
    ecarts = [
        f"{cle} : {avant.get(cle)} → {apres.get(cle)}"
        for cle in sorted(set(avant) | set(apres))
        if cle != "_unknown" and avant.get(cle) != apres.get(cle)
    ]
    if avant.lignes != apres.lignes:
        ecarts.append("lignes de paye différentes (code, colonne, montant ou rappel)")
    tete_avant, tete_apres = lire_en_tete(entree), lire_en_tete(sortie)
    champs = ("mois", "ministere", "grade", "enfants", "echelon", "indice", "nbi", "temps_partiel")
    for champ in (*champs, "temps_de_travail", "taux_pas"):
        if getattr(tete_avant, champ) != getattr(tete_apres, champ):
            ecarts.append(f"en-tête {champ} : {getattr(tete_avant, champ)} → {getattr(tete_apres, champ)}")
    return ecarts


def anonymise(entree: Path, sortie: Path, siret: str | None = None) -> Anonymisation:
    """Écrit dans ``sortie`` le bulletin ``entree`` réduit aux zones de ``garde``, puis compare
    les deux lectures. ``siret`` : un SIRET fictif à écrire à la place du vrai, pour un test
    du tri par gestionnaire (``agent.toml``, ``siret``)."""
    gardes = ecartes = 0
    nirs: list[str] = []
    with pdfplumber.open(entree) as pdf:
        pages = [(float(p.width), float(p.height), list(p.chars), _nir(p)) for p in pdf.pages]
    with PDFMaker(str(sortie), pagesize=(pages[0][0], pages[0][1])) as doc:
        doc.set_metadata(title="Bulletin anonymisé")
        for rang, (largeur, hauteur, chars, nir) in enumerate(pages):
            if rang:
                doc.new_page()
                doc.canvas.setPageSize((largeur, hauteur))
            gardes_page = [c for c in chars if garde(c)]
            gardes += len(gardes_page)
            ecartes += len(chars) - len(gardes_page)
            if nir:
                nirs.append(nir)
            _redessine(doc, gardes_page)
            if siret and rang == 0:
                doc.canvas.setFont("Courier-Bold", 10)
                doc.canvas.drawString(528.0, hauteur - 67.0, siret)
    with pdfplumber.open(sortie) as pdf:
        texte = "".join(c["text"] for p in pdf.pages for c in p.chars if c["text"].isdigit())
    nir_present = any(len(nir) >= 6 and nir in texte for nir in nirs)
    return Anonymisation(gardes, ecartes, nir_present, tuple(_differences(entree, sortie)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entree", type=Path, help="le bulletin PAY18E à anonymiser")
    parser.add_argument("sortie", type=Path, help="le bulletin anonymisé à écrire")
    parser.add_argument("--siret", help="un SIRET fictif à écrire en en-tête (14 chiffres)")
    args = parser.parse_args(argv)
    if args.siret is not None and not (args.siret.isdigit() and len(args.siret) == 14):
        parser.error("--siret attend 14 chiffres")
    if args.sortie.resolve() == args.entree.resolve():
        parser.error("la sortie écraserait le bulletin d'origine")
    bilan = anonymise(args.entree, args.sortie, args.siret)
    print(f"{args.sortie} : {bilan.gardes} caractères gardés, {bilan.ecartes} écartés")
    if bilan.nir_present:
        print("ÉCHEC : le NIR figure encore dans la sortie ; ne la partagez pas.")
        return 1
    if bilan.differences:
        print("La lecture de la sortie diffère de celle de l'original :")
        for ligne in bilan.differences:
            print(f"  {ligne}")
        return 1
    print("Lecture identique à l'original. Relisez la sortie avant de la partager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
