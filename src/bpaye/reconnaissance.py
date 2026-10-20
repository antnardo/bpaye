"""Reconnaître un bulletin PDF seul : ce qu'il dit de l'agent, sans carrière ni agent.toml.

extract_bulletin lit les montants ; ce module y ajoute l'en-tête du bulletin (grade,
échelon, indice, enfants, NBI, temps partiel, mois, taux du prélèvement à la source) et
en déduit, avec les seules tables du paquet, ce qu'un bulletin laisse voir : le corps et
la grille dont l'échelon porte cet indice au mois du bulletin, la fraction de traitement
payée, la zone d'indemnité de résidence, le nombre d'enfants que paie le SFT, et les
situations que trahissent les lignes (CPGE, éducation prioritaire, professeur principal,
heures supplémentaires, Pacte…).

L'en-tête se lit caractère par caractère, rangé par colonne d'abscisse, et non par
morceaux : la fusion des morceaux de pdf._pages colle des valeurs voisines (le grade au
numéro de dossier, le ministère au numéro de sécurité sociale). Le numéro de sécurité
sociale et sa clé ne sont jamais lus.

Ce qui se déduit est donné avec ce qui l'appuie ; une déduction impossible (indice absent
des grilles, montant de SFT qu'aucun nombre d'enfants ne donne) devient une remarque,
pas une valeur devinée.
"""

import argparse
import datetime as dt
import re
import sys
import unicodedata
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bpaye.codes import ALL_CODES
from bpaye.config import BAREME, Bareme
from bpaye.grille import GRILLES
from bpaye.pdf import DR_MONTH_FR, BulletinLu, ecart_totaux, extract_bulletin
from bpaye.point import calc_traitement_brut
from bpaye.sft import valeur_sft
from bpaye.utils import last_day_month

__all__ = [
    "EnTete",
    "Reconnaissance",
    "lire_en_tete",
    "main",
    "reconnait",
]

# La ligne d'identification : ordonnée (haut des caractères) et colonnes d'abscisse, de
# leur bord gauche au suivant. Le numéro de sécurité sociale (x 40 à 185) n'est pas lu.
_Y_IDENTIFICATION = (100.0, 112.0)
_COLONNES: dict[str, tuple[float, float]] = {
    "ministere": (0.0, 40.0),
    "dossier": (185.0, 205.0),
    "grade": (205.0, 335.0),
    "enfants": (335.0, 370.0),
    "echelon": (370.0, 405.0),
    "indice": (405.0, 455.0),
    "nbi": (455.0, 515.0),
    "temps_partiel": (515.0, 600.0),
}
_Y_MOIS = (15.0, 28.0)
_Y_TEMPS_DE_TRAVAIL = (25.0, 35.0)
_TAUX_PAS_RE = re.compile(r"TAUX\s+[A-ZÉ ]*?(\d+,\d+)\s*%")
_MOIS_RE = re.compile(r"\b([A-Z]+)\s+(\d{4})\b")

# Les classes que désignent les abréviations du grade imprimé : un mot entier (« CE »
# n'est pas dans « CERTIFIE »), ou une abréviation qui ne se confond avec rien.
_CLASSES = (
    ("HC", ("HC", "H.CL"), ("HORS CL", "HORS-CL")),
    ("CE", ("CE",), ("CL.EX", "CL EX", "EXCEP")),
)


@dataclass(frozen=True, slots=True)
class EnTete:
    """Ce que dit l'en-tête du bulletin, tel qu'imprimé ; None quand le champ est vide."""

    mois: dt.date | None  # dernier jour du mois payé
    ministere: str | None
    grade: str | None
    enfants: int | None
    echelon: int | None
    indice: int | None  # indice majoré, ou nombre d'heures d'un vacataire
    nbi: str | None  # points de NBI, ou taux horaire
    temps_partiel: str | None
    temps_de_travail: str | None
    taux_pas: float | None  # taux du prélèvement à la source, en %


@dataclass(frozen=True, slots=True)
class Reconnaissance:
    """Un bulletin reconnu : sa lecture, son en-tête, et ce qui s'en déduit."""

    fichier: str
    lu: BulletinLu
    en_tete: EnTete
    corps: str | None
    grille: str | None  # nom de la grille dans grilles.toml (GRILLE_AGCN…)
    classe: str | None
    echelon: int | None  # échelon de la grille dont l'indice est celui du bulletin
    fraction: float | None  # traitement payé ÷ traitement d'un temps plein à cet indice
    zone_residence: int | None
    enfants_sft: int | None
    constats: tuple[str, ...]
    remarques: tuple[str, ...]


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def _texte(caracteres: list[dict]) -> str:
    """Les caractères d'une colonne remis en texte, une espace là où ils s'écartent."""
    texte, fin = "", None
    for c in sorted(caracteres, key=lambda c: c["x0"]):
        if fin is not None and c["x0"] - fin > 1.0:
            texte += " "
        texte += c["text"]
        fin = c["x1"]
    return " ".join(texte.split())


# Les bulletins sans traitement indiciaire, que l'en-tête désigne à la place du grade.
_HORS_GRILLE = {
    "INDEMNITAIRE": "bulletin indemnitaire : sans traitement, il complète le bulletin principal",
    "VACATAIRE": "bulletin de vacataire : vacations (jury, examen…), payées à part",
}


def _hors_grille(en_tete: EnTete) -> str:
    grade = (en_tete.grade or "").upper()
    return next((nom for nom in _HORS_GRILLE if nom in grade), "")


def _rang(n: int | None) -> str:
    return "?" if n is None else ("1er" if n == 1 else f"{n}e")


def _entier(texte: str | None) -> int | None:
    return int(texte) if texte and texte.isdigit() else None


def lire_en_tete(pdf_path: str | Path) -> EnTete:
    """L'en-tête du bulletin : la ligne d'identification, le mois, le temps de travail et le
    taux du prélèvement à la source."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        caracteres = page.chars
        texte_page = page.extract_text() or ""
    ligne = [c for c in caracteres if _Y_IDENTIFICATION[0] <= c["top"] <= _Y_IDENTIFICATION[1]]
    champs: dict[str, str | None] = {}
    for nom, (debut, fin) in _COLONNES.items():
        champs[nom] = _texte([c for c in ligne if debut <= c["x0"] < fin]) or None
    # Le numéro de dossier (deux chiffres) précède le grade dans la même colonne de texte.
    if champs["dossier"] is None and champs["grade"] and re.match(r"^\d{2}\s", champs["grade"]):
        champs["grade"] = champs["grade"][3:].strip()

    mois = None
    haut = _texte([c for c in caracteres if _Y_MOIS[0] <= c["top"] <= _Y_MOIS[1] and 290 <= c["x0"] < 420])
    if (m := _MOIS_RE.search(_sans_accents(haut).upper())) and m.group(1) in DR_MONTH_FR:
        mois = last_day_month(dt.date(int(m.group(2)), DR_MONTH_FR[m.group(1)], 1))
    temps = _texte(
        [
            c
            for c in caracteres
            if _Y_TEMPS_DE_TRAVAIL[0] <= c["top"] <= _Y_TEMPS_DE_TRAVAIL[1] and c["x0"] >= 500
        ]
    )
    taux = _TAUX_PAS_RE.search(texte_page.upper())
    return EnTete(
        mois=mois,
        ministere=champs["ministere"],
        grade=champs["grade"],
        enfants=_entier(champs["enfants"]),
        echelon=_entier(champs["echelon"]),
        indice=_entier(champs["indice"]),
        nbi=champs["nbi"],
        temps_partiel=champs["temps_partiel"],
        temps_de_travail=temps or None,
        taux_pas=float(taux.group(1).replace(",", ".")) if taux else None,
    )


def _grilles_candidates(grade: str | None) -> list[str]:
    """Les grilles que désigne le grade imprimé, de la plus probable à la moins probable ;
    toutes si le grade ne dit rien de connu."""
    g = _sans_accents(grade or "").upper()
    mots = g.split()
    classe = next(
        (
            c
            for c, entiers, fragments in _CLASSES
            if any(m in mots for m in entiers) or any(f in g for f in fragments)
        ),
        "CN",
    )
    if "CHAIRE" in g:
        return ["GRILLE_CHSUP"]
    if "AGREGE" in g:
        return [f"GRILLE_AG{classe}"]
    # PE, PLP, PEPS, CPE, PsyEN et certifiés : la grille des certifiés.
    if any(m in g for m in ("CERTIFIE", "ECOLES", "P.E.", "PLP", "LYCEE PRO", "EPS", "CPE", "C.P.E", "PSY")):
        return [f"GRILLE_CERT{classe}"]
    return list(GRILLES)


def _corps(grade: str | None, defaut: str) -> str:
    g = _sans_accents(grade or "").upper()
    for marque, corps in (
        ("ECOLES", "PE"),
        ("P.E.", "PE"),
        ("PLP", "PLP"),
        ("LYCEE PRO", "PLP"),
        ("EPS", "PEPS"),
        ("CPE", "CPE"),
        ("C.P.E", "CPE"),
        ("PSY", "PsyEN"),
    ):
        if marque in g:
            return corps
    return defaut


def _fraction_connue(fraction: float) -> str:
    for valeur, nom in (
        (1.0, "temps plein"),
        (32 / 35, "90 %"),
        (6 / 7, "80 %"),
        (0.7, "70 %"),
        (0.6, "60 %"),
        (0.5, "50 %"),
    ):
        if abs(fraction - valeur) < 0.002:
            return nom
    return f"{fraction:.1%} d'un temps plein"


def _constats(lu: BulletinLu) -> list[str]:
    """Ce que trahissent les lignes du bulletin."""
    m = lu.montants
    present = {cle[:6] for cle in m}
    signes: list[tuple[set[str], str]] = [
        ({"200597"}, "en classe préparatoire (IFP CPGE)"),
        ({"201882"}, "en éducation prioritaire renforcée (REP+)"),
        ({"201883"}, "en éducation prioritaire (REP)"),
        ({"201228", "202566"}, "professeur principal (ISOE part modulable)"),
        ({"200205"}, "heures supplémentaires année (HSA)"),
        ({"200207"}, "colles (heures d'interrogation)"),
        ({"200215"}, "heures supplémentaires effectives (HSE)"),
        ({"202475", "202476"}, "Pacte (part fonctionnelle)"),
        ({"101070"}, "nouvelle bonification indiciaire"),
        ({"200039"}, "remboursement domicile-travail"),
        ({"200041"}, "forfait mobilités durables"),
        ({"201150"}, "détachement"),
        ({"720576", "720577"}, "PSC santé MGEN (contrat collectif depuis mai 2026)"),
        ({"202354"}, "participation forfaitaire PSC (15 €, jusqu'en avril 2026)"),
        ({"202510"}, "PSC prévoyance (participation employeur)"),
        ({"201914"}, "professeur des écoles (ISAE)"),
        ({"200364"}, "second degré (ISOE part fixe)"),
    ]
    constats = [texte for codes, texte in signes if codes & present]
    rappels = sorted({cle[:6] for cle in m if cle.endswith("_R")})
    if rappels:
        libelles = ", ".join(f"{c} {ALL_CODES[c]['libelle']}" for c in rappels)
        constats.append(f"rappels : {libelles}")
    if lu.rappel_decompte:
        constats.append(f"rappel sur décompte : {lu.rappel_decompte:.2f} €")
    return constats


def _situe(
    en_tete: EnTete, jour: dt.date, remarques: list[str]
) -> tuple[str | None, str | None, str | None, int | None]:
    """Le corps, la grille, la classe et l'échelon que désignent le grade, l'échelon et
    l'indice imprimés. L'échelon imprimé fait foi quand la grille du grade l'a ; un indice
    qui n'est pas le sien se signale (indice conservé à titre personnel après une
    promotion, ou promotion pas encore payée)."""
    indice, imprime = en_tete.indice, en_tete.echelon
    for nom in _grilles_candidates(en_tete.grade):
        try:
            grille = GRILLES[nom].value(jour)
        except ValueError:
            continue
        a_l_indice = [e for e, im in enumerate(grille.indices, start=1) if im == indice]
        if (
            imprime is not None
            and 1 <= imprime <= len(grille.indices)
            and (a_l_indice or len(_grilles_candidates(en_tete.grade)) == 1)
        ):
            attendu = grille.indice(imprime)
            if attendu != indice:
                sens = "supérieur" if indice and indice > attendu else "inférieur"
                remarques.append(
                    f"indice {indice} {sens} à celui du {_rang(imprime)} échelon ({attendu}) : indice "
                    "conservé à titre personnel, ou changement d'échelon pas encore payé"
                )
            return _corps(en_tete.grade, grille.corps), nom, grille.classe, imprime
        if a_l_indice:
            if imprime is not None:
                remarques.append(
                    f"échelon imprimé {imprime}, indice {indice} du {_rang(a_l_indice[0])} échelon"
                )
            return _corps(en_tete.grade, grille.corps), nom, grille.classe, a_l_indice[0]
    remarques.append(f"indice {indice} absent des grilles de {en_tete.grade!r} au {jour}")
    return None, None, None, None


def reconnait(pdf_path: str | Path, bareme: Bareme = BAREME) -> Reconnaissance:
    """Le bulletin ``pdf_path`` lu, son en-tête, et ce qui s'en déduit."""
    remarques: list[str] = []
    with warnings.catch_warnings(record=True) as alertes:
        warnings.simplefilter("always")
        lu = extract_bulletin(pdf_path)
    remarques += [str(a.message) for a in alertes]
    en_tete = lire_en_tete(pdf_path)
    jour = en_tete.mois
    if jour is None:
        remarques.append("mois du bulletin illisible : rien n'est déduit des grilles")

    corps = grille_nom = classe = None
    echelon = None
    if _hors_grille(en_tete):
        pass  # bulletin complémentaire ou de vacataire, sans traitement indiciaire
    elif jour is not None and en_tete.indice is not None:
        corps, grille_nom, classe, echelon = _situe(en_tete, jour, remarques)

    fraction = zone = enfants_sft = None
    traitement = lu.montants.get("101000")
    if jour is not None and en_tete.indice and traitement:
        plein = calc_traitement_brut(en_tete.indice, jour, bareme)
        fraction = round(traitement / plein, 4)
        residence = lu.montants.get("102000", 0.0)
        taux = residence / plein if plein else 0.0
        zone = min(((1, 0.03), (2, 0.01), (3, 0.0)), key=lambda z: abs(z[1] * fraction - taux))[0]
        sft = lu.montants.get("104000")
        if sft:
            enfants_sft = next(
                (n for n in range(1, 9) if abs(valeur_sft(n, plein, jour, bareme) - sft) < 0.015), None
            )
            if enfants_sft is None:
                remarques.append(f"SFT de {sft:.2f} € : aucun nombre d'enfants ne le donne à temps plein")
        else:
            enfants_sft = 0

    constats = _constats(lu)
    if _hors_grille(en_tete):
        constats.insert(0, _HORS_GRILLE[_hors_grille(en_tete)])
    if fraction is not None:
        constats.insert(0, f"traitement payé : {_fraction_connue(fraction)}")
    ecart = ecart_totaux(lu)
    if ecart:
        remarques.append(f"lecture incomplète : écart de {ecart} € avec TOTAUX DU MOIS")
    return Reconnaissance(
        fichier=Path(pdf_path).name,
        lu=lu,
        en_tete=en_tete,
        corps=corps,
        grille=grille_nom,
        classe=classe,
        echelon=echelon,
        fraction=fraction,
        zone_residence=zone,
        enfants_sft=enfants_sft,
        constats=tuple(constats),
        remarques=tuple(dict.fromkeys(remarques)),
    )


def _affiche(r: Reconnaissance) -> str:
    e = r.en_tete
    mois = f"{e.mois:%m/%Y}" if e.mois else "?"
    lignes = [
        f"== {r.fichier} — bulletin de {mois}",
        f"   grade imprimé : {e.grade or '?'}, échelon {e.echelon or '?'}, indice {e.indice or '?'}"
        + (f", NBI {e.nbi}" if e.nbi else "")
        + (f", temps partiel {e.temps_partiel}" if e.temps_partiel else ""),
    ]
    if r.grille:
        classe = f" {r.classe}" if r.classe else ""
        lignes.append(f"   reconnu : {r.corps}{classe}, {_rang(r.echelon)} échelon ({r.grille})")
    if r.zone_residence is not None:
        lignes.append(f"   indemnité de résidence : zone {r.zone_residence}")
    a_charge = e.enfants if e.enfants is not None else "?"
    payes = r.enfants_sft if r.enfants_sft is not None else "?"
    lignes.append(f"   enfants : {a_charge} à charge (en-tête), {payes} payés par le SFT")
    if e.taux_pas is not None:
        lignes.append(f"   prélèvement à la source : {e.taux_pas:.2f} %")
    lu = r.lu
    if lu.net_payer is not None:
        lignes.append(f"   net à payer {lu.net_payer:.2f} €, montant imposable {lu.montant_imp or 0:.2f} €")
    lignes += [f"   - {c}" for c in r.constats]
    lignes += [f"   ! {m}" for m in r.remarques]
    return "\n".join(lignes)


def main(argv: Sequence[str] | None = None) -> int:
    """bpaye-lire BULLETIN.pdf [...] : chaque bulletin reconnu, sans carrière ni agent.toml."""
    parser = argparse.ArgumentParser(prog="bpaye-lire", description=main.__doc__)
    parser.add_argument("bulletins", nargs="+", type=Path, help="bulletins PDF de l'ENSAP")
    args = parser.parse_args(argv)
    for chemin in args.bulletins:
        print(_affiche(reconnait(chemin)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
