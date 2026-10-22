"""Les semaines de cours d'une période, hors vacances scolaires.

Les colles ont lieu chaque semaine de cours. Une semaine compte quand son lundi est un
jour de classe : un pont (l'Ascension, un jeudi et un vendredi) ne retire pas la
semaine, les colles s'y déplacent. Une semaine appartient au mois de son lundi.

Les vacances viennent de vacances.toml (zones A, B et C, calendrier officiel), que
scripts/maj_vacances.py régénère. Chaque établissement suit sa zone : des colles dans un
lycée d'une autre zone n'ont pas les mêmes semaines, en février surtout. La zone par
défaut, ZONE_PAR_DEFAUT, sert quand carriere.toml ne donne pas celle du lycée
d'affectation. Une période hors des années scolaires
connues lève une erreur plutôt que de compter des vacances comme des semaines de cours.
"""

import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

from bpaye.utils import lit_toml

__all__ = [
    "VACANCES",
    "ZONE_PAR_DEFAUT",
    "annee_scolaire",
    "charge_vacances",
    "en_vacances",
    "semaines_de_cours",
]

_TOML = Path(__file__).parent / "vacances.toml"
# La zone du lycée d'affectation quand carriere.toml ne la donne pas ([depart] zone_vacances).
ZONE_PAR_DEFAUT = "C"


def charge_vacances(path: Path = _TOML) -> dict[str, list[tuple[str, dt.date, dt.date]]]:
    """Par zone, (année scolaire, premier jour sans cours, jour de la reprise) de chaque
    période."""
    cfg = lit_toml(path)
    par_zone: dict[str, list[tuple[str, dt.date, dt.date]]] = defaultdict(list)
    for v in cfg["vacances"]:
        par_zone[v["zone"]].append((v["annee"], v["debut"], v["reprise"]))
    return dict(par_zone)


VACANCES = charge_vacances()


def _de_la_zone(zone: str) -> list[tuple[str, dt.date, dt.date]]:
    if zone not in VACANCES:
        raise ValueError(f"zone de vacances inconnue : {zone!r}, attendu {sorted(VACANCES)}")
    return VACANCES[zone]


def annee_scolaire(jour: dt.date) -> str:
    """« 2025-2026 » pour un jour de septembre 2025 à août 2026."""
    debut = jour.year if jour.month >= 9 else jour.year - 1
    return f"{debut}-{debut + 1}"


def en_vacances(
    jour: dt.date, vacances: list[tuple[str, dt.date, dt.date]] | None = None, zone: str = ZONE_PAR_DEFAUT
) -> bool:
    vacances = _de_la_zone(zone) if vacances is None else vacances
    return any(debut <= jour < reprise for _, debut, reprise in vacances)


def semaines_de_cours(
    debut: dt.date,
    fin: dt.date,
    vacances: list[tuple[str, dt.date, dt.date]] | None = None,
    zone: str = ZONE_PAR_DEFAUT,
) -> dict[tuple[int, int], int]:
    """Le nombre de semaines de cours de chaque mois (année, mois), du ``debut`` à la
    ``fin`` comprise, dans la ``zone`` ; la semaine qui contient le ``debut`` compte."""
    vacances = _de_la_zone(zone) if vacances is None else vacances
    connues = {annee for annee, _, _ in vacances}
    for jour in (debut, fin):
        if annee_scolaire(jour) not in connues:
            raise ValueError(
                f"vacances inconnues pour {annee_scolaire(jour)} : lancer scripts/maj_vacances.py"
            )
    lundi = debut - dt.timedelta(days=debut.weekday())
    semaines: Counter[tuple[int, int]] = Counter()
    while lundi <= fin:
        if not en_vacances(lundi, vacances):
            semaines[(lundi.year, lundi.month)] += 1
        lundi += dt.timedelta(weeks=1)
    return dict(sorted(semaines.items()))
