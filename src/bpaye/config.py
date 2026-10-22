"""Le barème : les taux, montants et barèmes datés de taux.toml, en objets Taux/Fixe.

Un Bareme se passe explicitement, de Paye jusqu'à chaque rubrique : on peut ainsi
calculer avec un autre barème que celui du paquet (une hausse du point annoncée, un
montant corrigé avant une nouvelle version de bpaye) sans rien modifier d'autre.
`Bareme.depuis_fichiers` part de taux.toml et y substitue, section par section, celles
des fichiers donnés. BAREME est le barème du paquet, valeur par défaut partout.

load() et get() restent, pour lire le barème du paquet.
"""

import datetime as dt
from pathlib import Path
from typing import Any, Self

from bpaye.classes import AnnuelPonctuel, Fixe, Taux
from bpaye.utils import date_de, lit_toml

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
            ponctuel.append(date_de(entry), entry["valeur"])
        return ponctuel
    obj: Fixe | Taux = Fixe() if kind == "Fixe" else Taux()
    for entry in section["values"]:
        date = date_de(entry)
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
        cfg = lit_toml(TAUX_TOML)
        for chemin in chemins:
            _substitue(cfg, lit_toml(chemin))
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

    def au(self, path: str, date: dt.date | None) -> Any:
        """La valeur du barème ``path`` à ``date`` (load(path)(date))."""
        return self.load(path)(date)

    def _load_indexe(self, section: dict[str, Any]) -> Fixe:
        """Un montant annuel indexé sur le point (type « IndexePoint ») : chaque montant de
        référence (un arrêté, à défaut un relevé) suit le point jusqu'au suivant. La paie
        applique chaque hausse au montant mensuel du mois d'avant, déjà au centime : ainsi
        se retrouvent tous les bulletins relevés, et même l'arrêté de 2009 de l'ISOE
        (1 183,68 €) depuis le relevé de 2007. Un montant recalculé chaque fois depuis la
        référence s'écarte d'un centime par mois (IFP de 2016 : 88,14 € au lieu de 88,15 €)."""
        point = self.load("point")
        references = sorted((date_de(e), float(e["valeur"])) for e in section["values"])
        fixe = Fixe()
        for i, (debut, montant) in enumerate(references):
            fin = references[i + 1][0] if i + 1 < len(references) else None
            mensuel, point_avant = round(montant / 12, 2), point(debut)
            fixe.append(debut, mensuel=mensuel)
            for date, valeur in point.values:
                if date > debut and (fin is None or date < fin):
                    mensuel, point_avant = round(mensuel * valeur / point_avant, 2), valeur
                    fixe.append(date, mensuel=mensuel)
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
