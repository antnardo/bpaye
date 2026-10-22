"""Les grilles indiciaires : l'indice majoré de chaque échelon, à chaque date.

Une grille se compose de textes différents, datés chacun : les indices bruts du statut,
le barème IB → IM (décret 82-1105), les hors-échelle (décret 85-1148), les durées
d'échelon. grilles.toml, généré depuis les relevés de docs/verification par
scripts/genere_grilles.py, garde chaque élément avec sa date et sa source ; _compose en
refait la grille à chaque date où l'un d'eux change, plutôt que de figer des indices
majorés qui vieilliraient à chaque revalorisation. Avant sa première date, une grille
n'a rien de vérifié : elle refuse (MANQUANT).
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, overload

from bpaye.classes import Temporal
from bpaye.utils import lit_toml

__all__ = [
    "GRILLES",
    "GRILLE_AGCN",
    "GRILLE_CHSUP",
    "Grille",
    "indice_majore",
    "update_indices",
]


@dataclass(frozen=True, slots=True, eq=False)
class Grille:
    """Une grille à une date : ses indices majorés et ses durées d'échelon (ordinaire, au
    choix, au grand choix ; None pour un échelon sans avancement automatique). Deux grilles
    se distinguent par leur identité, celle de leur date dans le Temporal qui les porte.

    cn_echelons : le nombre d'échelons de la « classe normale » qui servent à l'indice
    moyen de la formule des HSA ; None pour la grille entière."""

    corps: str
    indices: list[int]
    anciennete: list[float | None]
    classe: str = ""
    choix: list[float | None] | None = None
    grandchoix: list[float | None] | None = None
    cn_echelons: int | None = None

    def indice(self, echelon: int) -> int:
        return self.indices[echelon - 1]

    def index(self, echelon: int) -> int:
        return echelon - 1

    def __len__(self) -> int:
        return len(self.indices)

    def __str__(self) -> str:
        return f"{self.corps} {self.classe}"

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def inmoyen(self) -> float:
        last = self.indices[self.cn_echelons - 1] if self.cn_echelons else self.indices[-1]
        return (self.indices[0] + last) / 2

    @property
    def lastechelon(self) -> int:
        return len(self)


def update_indices(gbase: Grille, indices: list[int]) -> Grille:
    return Grille(
        gbase.corps, indices, gbase.anciennete, gbase.classe, gbase.choix, gbase.grandchoix, gbase.cn_echelons
    )


@overload
def _sentinelle(lst: list[float]) -> list[float | None]: ...
@overload
def _sentinelle(lst: None) -> None: ...
def _sentinelle(lst: list[float] | None) -> list[float | None] | None:
    """-1 dans une liste de durées : pas d'avancement automatique (None)."""
    if lst is None:
        return None
    return [None if v == -1 else v for v in lst]


def _en_vigueur(entrees: list[dict[str, Any]], date: dt.date) -> dict[str, Any] | None:
    """La dernière entrée datée au plus tard ``date`` (entrées triées), ou None."""
    retenue = None
    for e in entrees:
        if e["date"] <= date:
            retenue = e
    return retenue


def _indices_majores(
    ib: list[int | str],
    date: dt.date,
    baremes: list[dict[str, Any]],
    hors_echelle: list[dict[str, Any]],
    nom: str,
) -> list[int]:
    """Les indices majorés d'une liste d'indices bruts à ``date`` : le barème IB → IM
    en vigueur (décret 82-1105), et pour « HEA » ou « HEB » les trois chevrons du groupe
    hors échelle (décret 85-1148, art. 6), chacun une position de la grille."""
    he = _en_vigueur(hors_echelle, date)
    indices: list[int] = []
    for b in ib:
        if b in ("HEA", "HEB"):
            if he is None:
                raise ValueError(f"{nom} : pas de valeurs hors échelle au {date}")
            indices.extend(he[b])
        else:
            # La dernière version du barème qui donne cet IB : celle du 1/5/2008 n'est
            # publiée que jusqu'à l'IB 536, la correspondance des autres n'ayant pas changé.
            versions = [e for e in baremes if e["date"] <= date and str(b) in e["ib_im"]]
            if not versions:
                raise ValueError(f"{nom} : l'IB {b} n'est dans aucun barème en vigueur au {date}")
            indices.append(versions[-1]["ib_im"][str(b)])
    return indices


def _compose(
    nom: str, spec: dict[str, Any], baremes: list[dict[str, Any]], hors_echelle: list[dict[str, Any]]
) -> Temporal[Grille]:
    """La grille ``nom`` à chaque date où l'un de ses éléments change : ses indices
    bruts (statuts), le barème IB → IM, les hors-échelle, ses durées d'échelon. Ces
    éléments viennent de textes différents, aux dates différentes : chacun garde la
    sienne et sa source dans grilles.toml. Une entrée peut aussi donner directement
    ses indices majorés (``im``), quand le texte des indices bruts manque."""
    indices = sorted(spec["indices"], key=lambda e: e["date"])
    durees = sorted(spec["durees"], key=lambda e: e["date"])
    # Avant le premier barème lu, pas d'indice majoré : la grille commence à sa date.
    premier_bareme = min(e["date"] for e in baremes) if baremes else indices[0]["date"]
    debut = max(indices[0]["date"], premier_bareme)
    dates = {e["date"] for e in indices} | {e["date"] for e in durees}
    dates |= {e["date"] for e in baremes} | {e["date"] for e in hors_echelle}
    temporal: Temporal[Grille] = Temporal()
    temporal.strict = True
    precedente = None
    for date in sorted(d for d in dates if d >= debut):
        entree = _en_vigueur(indices, date) or indices[0]
        duree = _en_vigueur(durees, date) or durees[0]
        im = (
            entree["im"]
            if "im" in entree
            else _indices_majores(entree["ib"], date, baremes, hors_echelle, nom)
        )
        cle = (
            tuple(im),
            tuple(duree["anciennete"]),
            tuple(duree.get("choix") or ()),
            tuple(duree.get("grandchoix") or ()),
        )
        if cle == precedente:
            continue
        precedente = cle
        g = Grille(
            corps=spec["corps"],
            indices=im,
            anciennete=_sentinelle(duree["anciennete"]),
            classe=spec.get("classe", ""),
            choix=_sentinelle(duree.get("choix")),
            grandchoix=_sentinelle(duree.get("grandchoix")),
            cn_echelons=spec.get("cn_echelons"),
        )
        temporal.append(date, g)
    return temporal


def _load_grilles_toml() -> tuple[dict[str, Temporal[Grille]], list[dict[str, Any]]]:
    """Charge grilles.toml : les grilles par nom, et les versions du barème IB → IM."""
    cfg = lit_toml(Path(__file__).parent / "grilles.toml")
    baremes = sorted(cfg.pop("bareme", []), key=lambda e: e["date"])
    hors_echelle = sorted(cfg.pop("hors_echelle", []), key=lambda e: e["date"])
    grilles = {nom: _compose(nom, spec, baremes, hors_echelle) for nom, spec in cfg.items()}
    return grilles, baremes


_grilles, _BAREMES_IB = _load_grilles_toml()


def indice_majore(ib: int, date: dt.date) -> int:
    """L'indice majoré de l'indice brut ``ib`` à ``date`` (décret 82-1105), pour un indice
    que grilles.toml relève : ceux des grilles, et les IB 524 et 879 du SFT."""
    return int(_indices_majores([ib], date, _BAREMES_IB, [], "indice_majore")[0])


GRILLES = _grilles  # toutes les grilles de grilles.toml, par nom
GRILLE_AGCN = _grilles["GRILLE_AGCN"]
GRILLE_CHSUP = _grilles["GRILLE_CHSUP"]
