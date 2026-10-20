"""Le barème : les taux, montants et barèmes datés de taux.toml, en objets Taux/Fixe.

Un Bareme se passe explicitement, de Paye jusqu'à chaque rubrique : on peut ainsi
calculer avec un autre barème que celui du paquet (une hausse du point annoncée, un
montant corrigé avant une nouvelle version de bpaye) sans rien modifier d'autre.
`Bareme.depuis_fichiers` part de taux.toml et y substitue, section par section, celles
des fichiers donnés. BAREME est le barème du paquet, valeur par défaut partout.

load() et get() restent, pour lire le barème du paquet.
"""

import tomllib
from pathlib import Path
from typing import Any, Self

from bpaye.classes import AnnuelPonctuel, Fixe, Taux
from bpaye.utils import parse_toml_date

__all__ = [
    "BAREME",
    "TAUX_TOML",
    "Bareme",
    "depuis_section",
    "get",
    "load",
]

TAUX_TOML = Path(__file__).parent / "taux.toml"


def _load_temporal(section: dict[str, Any]) -> Fixe | Taux | AnnuelPonctuel:
    """Construit un objet Fixe, Taux ou AnnuelPonctuel à partir d'une section TOML."""
    kind = section["type"]
    unite = section.get("unite", "mensuel")
    if kind == "AnnuelPonctuel":
        mois = section.get("mois_versement", 1)
        ponctuel = AnnuelPonctuel(mois_versement=mois)
        for entry in section["values"]:
            ponctuel.append(parse_toml_date(entry["date"]), entry["valeur"])
        return ponctuel
    obj: Fixe | Taux = Fixe() if kind == "Fixe" else Taux()
    for entry in section["values"]:
        date = parse_toml_date(entry["date"])
        val = entry["valeur"]
        if kind == "Fixe":
            assert isinstance(obj, Fixe)
            if unite == "annuel":
                obj.append(date, annuel=val)
            else:
                obj.append(date, mensuel=val)
        else:
            obj.append(date, val)
    return obj


def _substitue(base: dict[str, Any], autre: dict[str, Any]) -> None:
    """Remplace dans ``base`` les sections que donne ``autre`` : une section datée
    (avec ``type``) ou une valeur remplace l'ancienne entière ; une table de tables se
    parcourt."""
    for cle, valeur in autre.items():
        if isinstance(valeur, dict) and "type" not in valeur and isinstance(base.get(cle), dict):
            _substitue(base[cle], valeur)
        else:
            base[cle] = valeur


class Bareme:
    """Les tables de taux.toml, chacune construite une fois à la demande."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._cache: dict[str, Any] = {}

    @classmethod
    def depuis_fichiers(cls, *chemins: str | Path) -> Self:
        """Le barème du paquet, où les sections des fichiers ``chemins`` remplacent les
        siennes (même format que taux.toml)."""
        with TAUX_TOML.open("rb") as f:
            cfg = tomllib.load(f)
        for chemin in chemins:
            with Path(chemin).open("rb") as f:
                _substitue(cfg, tomllib.load(f))
        return cls(cfg)

    def get(self, path: str) -> Any:
        """La valeur brute (dict, liste, nombre) d'un chemin pointé : « sft.fixe »."""
        node: Any = self._cfg
        for key in path.split("."):
            node = node[key]
        return node

    def load(self, path: str) -> Any:
        """L'objet Taux, Fixe ou AnnuelPonctuel d'un chemin pointé : « csg.deductible »."""
        if path not in self._cache:
            section = self.get(path)
            if section.get("type") == "IndexePoint":
                temporal: Any = self._load_indexe(section)
            else:
                temporal = _load_temporal(section)
            temporal.strict = True
            self._cache[path] = temporal
        return self._cache[path]

    def _load_indexe(self, section: dict[str, Any]) -> Fixe:
        """Un montant annuel indexé sur le point (type « IndexePoint ») : chaque montant de
        référence (un arrêté, à défaut un relevé) suit le point jusqu'au suivant, au
        douzième arrondi au centime. Cet arrondi au mois redonne les bulletins : l'ISOE de
        1 183,68 € au 1/1/2009 vaut 99,93 € par mois au point du 1/7/2010, 1 199,16 € par an
        (le produit exact, 1 199,13 €, ne les redonne pas)."""
        point = self.load("point")
        references = sorted((parse_toml_date(e["date"]), float(e["valeur"])) for e in section["values"])
        fixe = Fixe()
        for i, (debut, montant) in enumerate(references):
            fin = references[i + 1][0] if i + 1 < len(references) else None
            point_reference = point(debut)
            fixe.append(debut, mensuel=round(montant / 12, 2))
            for date, valeur in point.values:
                if date > debut and (fin is None or date < fin):
                    fixe.append(date, mensuel=round(montant * valeur / point_reference / 12, 2))
        return fixe


BAREME = Bareme.depuis_fichiers()


def depuis_section(section: dict[str, Any]) -> Any:
    """Un objet Fixe, Taux ou AnnuelPonctuel d'une section lue ailleurs que dans taux.toml
    (agent.toml), au même format."""
    return _load_temporal(section)


def load(path: str) -> Any:
    """Une table datée du barème du paquet (BAREME.load)."""
    return BAREME.load(path)


def get(path: str) -> Any:
    """Une valeur brute du barème du paquet (BAREME.get)."""
    return BAREME.get(path)
