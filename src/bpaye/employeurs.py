"""Les employeurs de l'agent, déclarés par dates dans agent.toml ([[employeur]]).

Un mois peut avoir plusieurs bulletins : celui de l'employeur, un jury ou des colles payés
par un autre établissement, un rappel versé par un ancien employeur après le départ. Ce
sont des bulletins distincts, jamais additionnés ; le calcul de bpaye, celui d'une seule
carrière, ne se compare qu'au bulletin de l'employeur du mois. Le nom du fichier ne les
distingue pas (« -1 », « copie », « 2 » suivent les habitudes du système) : l'en-tête
du bulletin, si.

Un employeur se reconnaît à son SIRET ou au code de gestion de son poste, tels qu'imprimés.
Aucun des deux ne suffit seul, relevé sur des bulletins réels : un ancien employeur a versé
un rappel sans SIRET, sous son code de gestion habituel ; un lycée a changé de code de
gestion, pas de SIRET.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from bpaye.utils import parse_toml_date

__all__ = ["Employeur", "lit_employeur", "normalise_poste"]


def normalise_poste(poste: str) -> str:
    """Le code de gestion du poste, espaces réduits à un seul (« 08  A445 » → « 08 A445 »)."""
    return " ".join(poste.split())


@dataclass(frozen=True, slots=True)
class Employeur:
    """Un employeur déclaré : son nom, et les SIRET et codes de gestion de poste qui le
    reconnaissent sur un bulletin."""

    nom: str
    sirets: tuple[str, ...] = ()
    postes: tuple[str, ...] = ()

    def reconnait(self, sirets: Iterable[str], poste: str) -> bool:
        """Vrai si l'en-tête d'un bulletin porte l'un de ses SIRET ou de ses codes de poste."""
        return bool(set(self.sirets) & set(sirets)) or normalise_poste(poste) in self.postes


def _liste(valeur: Any, cle: str, origine: str) -> tuple[str, ...]:
    if valeur is None:
        return ()
    valeurs = [valeur] if isinstance(valeur, str) else valeur
    if not isinstance(valeurs, list) or not all(isinstance(v, str) for v in valeurs):
        raise ValueError(f"{origine} : {cle} attend un texte ou une liste de textes")
    return tuple(valeurs)


def lit_employeur(entree: Mapping[str, Any], origine: str) -> tuple[dt.date, Employeur]:
    """Une entrée [[employeur]] : sa date, et l'employeur (nom, siret, poste ; siret et poste
    acceptent un texte ou une liste). Il en faut au moins un des deux."""
    sirets = _liste(entree.get("siret"), "siret", origine)
    postes = tuple(normalise_poste(p) for p in _liste(entree.get("poste"), "poste", origine))
    if not sirets and not postes:
        raise ValueError(f"{origine} : un employeur se reconnaît à un siret ou à un poste")
    return parse_toml_date(entree["date"]), Employeur(str(entree.get("nom", "")), sirets, postes)
