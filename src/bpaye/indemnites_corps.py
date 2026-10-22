"""Indemnités propres à un corps ou à une fonction : CPE, PsyEN, documentalistes, directeurs
d'école.

- CPE (200414) : indemnité forfaitaire, décret 91-468.
- PsyEN (202205) : indemnité de fonctions, décret 2017-1552, selon la spécialité (EDA,
  « éducation, développement et apprentissages » ; EDO, « éducation, développement et
  conseil en orientation scolaire et professionnelle ») : un seul code pour les deux.
- Professeurs documentalistes (200413) : indemnité de sujétions particulières, décret 91-467.
  Ils sont certifiés, mais ne touchent pas l'ISOE (indemnites.CORPS_ISOE).
- Directeurs d'école (202217, puis 202568 au 1/9/2024) : indemnité de sujétions spéciales,
  décret 83-644, part principale et part variable selon le nombre de classes, majorées en
  REP et REP+.

Montants annuels dans taux.toml, chacun avec son arrêté, versés au douzième arrondi au
centime (l'arrondi est supposé, comme pour les autres primes), à la fraction d'un temps
partiel (L612-5, a priori). Les périodes sans montant lu lèvent une erreur plutôt que
d'appliquer un montant deviné.

Pas calculée : la bonification indiciaire des directeurs d'école (décret 83-50, 3 à 40
points majorés), dont aucune rubrique de la DGFiP n'a été trouvée.
"""

import datetime as dt

from bpaye.classes import Ligne
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire

__all__ = [
    "DATE_RECODAGE_DIRECTEUR",
    "indemnite_cpe",
    "indemnite_directeur",
    "indemnite_documentaliste",
    "indemnite_psyen",
]

# ISS des directeurs : 202217 du 1/9/2018, recodée 202568 au 1/9/2024 (annexe 14 B de la
# DGFiP, 2026) ; avant le 1/9/2018, la rubrique n'est pas identifiée.
DATE_CODE_DIRECTEUR = dt.date(2018, 9, 1)
DATE_RECODAGE_DIRECTEUR = dt.date(2024, 9, 1)


def _mensuel(section: str, date: dt.date, bareme: Bareme) -> float:
    for periode in bareme.get(section).get("manquant", []):
        if periode["debut"] <= date <= periode["fin"]:
            raise ValueError(f"{section} : pas de montant vérifié au {date}")
    try:
        annuel = bareme.load(section).value_annuel(date)
    except ValueError as exc:
        raise ValueError(f"{section} : pas de montant vérifié au {date}") from exc
    return round(annuel / 12, 2)


def indemnite_cpe(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    if fonc.corps.au(date, None) != "CPE":
        return None
    montant = fonc.au_prorata(_mensuel("ind_cpe", date, bareme), date)
    return Ligne(montant, "Indemnité forfaitaire CPE", code=200414, classe="INDEM")


def indemnite_psyen(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    if fonc.corps.au(date, None) != "PsyEN":
        return None
    specialite = fonc.specialite.au(date, None)
    if specialite not in ("EDA", "EDO"):
        raise ValueError(f"PsyEN : spécialité « EDA » ou « EDO » attendue, pas {specialite!r}")
    montant = fonc.au_prorata(_mensuel(f"ind_psyen.{specialite.lower()}", date, bareme), date)
    return Ligne(montant, f"Indemnité de fonctions PsyEN {specialite}", code=202205, classe="INDEM")


def indemnite_documentaliste(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    if not fonc.documentaliste.au(date, None):
        return None
    montant = fonc.au_prorata(_mensuel("ind_documentaliste", date, bareme), date)
    return Ligne(montant, "Indemnité de sujétions particulières", code=200413, classe="INDEM")


def montant_directeur(classes: int, reseau: str | None, date: dt.date, bareme: Bareme = BAREME) -> float:
    """L'ISS annuelle d'un directeur d'une école de ``classes`` classes, ``reseau`` « REP »,
    « REP+ » ou None (arrêté du 12/9/2008, art. 2, 3 et 3-1)."""
    versions = [v for v in bareme.get("ind_directeur") if v["date"] <= date]
    if not versions or classes < 1:
        raise ValueError(f"ISS de directeur : pas de montant vérifié au {date} ({classes} classes)")
    v = max(versions, key=lambda e: e["date"])
    tranche = max(i for i, seuil in enumerate(v["seuils"]) if classes >= seuil)
    annuel = v["part_principale"] + v["part_variable"][tranche]
    if reseau is not None:
        majoration = bareme.get("ind_directeur_majoration")
        if date < majoration["date"]:
            raise ValueError(f"ISS de directeur : majoration d'avant le {majoration['date']} non relevée")
        annuel *= 1 + majoration["rep" if reseau == "REP" else "rep_plus"]
    return annuel


def indemnite_directeur(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    classes = fonc.direction_ecole.au(date, None)
    if not classes:
        return None
    if date < DATE_CODE_DIRECTEUR:
        raise ValueError(
            f"ISS de directeur : rubrique du bulletin avant le {DATE_CODE_DIRECTEUR} non identifiée"
        )
    reseau = fonc.education_prioritaire.au(date, None)
    annuel = montant_directeur(int(classes), reseau, date, bareme)
    montant = fonc.au_prorata(round(annuel / 12, 2), date)
    code = 202568 if date >= DATE_RECODAGE_DIRECTEUR else 202217
    return Ligne(montant, "ISS directeur d'école", code=code, classe="INDEM")
