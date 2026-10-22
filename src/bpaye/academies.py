"""Les retards habituels de la paie, par académie (academies.toml).

bpaye calcule chaque ligne au mois où elle est due : c'est ce que disent les textes, et
c'est ce qui fait apparaître un retard. Mais certains retards sont l'usage d'une paie,
tous les ans les mêmes : le neuvième d'octobre des HSA payé en novembre, parce que la
paie de septembre est close avant que les services ne soient validés. Les coder en dur
les rendrait vrais partout ; les laisser à l'agent lui ferait déclarer chaque année ce
que tout le monde subit. Ils sont donc des données datées et sourcées, comme taux.toml :
un défaut, des académies qui en héritent ou l'amendent, puis l'agent (agent.toml), dans
cet ordre. Le retard s'applique comme Paye.retard_paiement : la ligne reste due son
mois et arrive en rappel le mois de paiement, comme sur le bulletin.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bpaye.codes import ALL_CODES
from bpaye.utils import date_de, lit_toml

__all__ = [
    "ACADEMIES",
    "ACADEMIES_TOML",
    "ACADEMIE_PAR_DEFAUT",
    "CleRetard",
    "Retard",
    "lit_retard",
    "remplace",
    "retards_academie",
]

ACADEMIES_TOML = Path(__file__).parent / "academies.toml"
ACADEMIE_PAR_DEFAUT = "defaut"


@dataclass(frozen=True, slots=True)
class Retard:
    """La rubrique ``code``, due le mois ``du``, payée le mois ``paye`` (l'année suivante
    si ``paye`` précède ``du``), pour les mois dus depuis ``depuis``."""

    code: int
    du: int
    paye: int
    depuis: dt.date | None = None

    @property
    def decalage(self) -> int:
        """Le nombre de mois entre le mois dû et le mois de paiement."""
        return (self.paye - self.du) % 12

    def concerne(self, date: dt.date) -> bool:
        """Vrai pour un bulletin du mois dû, à partir de ``depuis``."""
        return date.month == self.du and (self.depuis is None or date >= self.depuis)


def lit_retard(entree: dict[str, Any], origine: str) -> Retard:
    """Un Retard d'une entrée TOML, vérifié : code connu, mois de 1 à 12, distincts."""
    code, du, paye = int(entree["code"]), int(entree["du"]), int(entree["paye"])
    if str(code) not in ALL_CODES:
        raise ValueError(f"{origine} : code {code} inconnu (codes.toml)")
    if not (1 <= du <= 12 and 1 <= paye <= 12) or du == paye:
        raise ValueError(f"{origine} : mois dû {du} et de paiement {paye} attendus de 1 à 12, distincts")
    depuis = date_de(entree, "depuis") if "depuis" in entree else None
    return Retard(code, du, paye, depuis)


def _charge(path: Path = ACADEMIES_TOML) -> dict[str, dict[str, Any]]:
    return lit_toml(path)


ACADEMIES = _charge()


# Un retard se range sous sa rubrique et son mois dû : une rubrique peut avoir plusieurs
# mois en retard (les HSA d'octobre et de novembre, payées en décembre).
CleRetard = tuple[int, int]


def remplace(retards: dict[CleRetard, Retard], nouveaux: list[Retard]) -> dict[CleRetard, Retard]:
    """``retards``, dont ``nouveaux`` remplacent tous ceux de leurs rubriques."""
    codes = {r.code for r in nouveaux}
    gardes = {cle: r for cle, r in retards.items() if r.code not in codes}
    return gardes | {(r.code, r.du): r for r in nouveaux}


def retards_academie(nom: str = ACADEMIE_PAR_DEFAUT) -> dict[CleRetard, Retard]:
    """Les retards de l'académie ``nom``, par rubrique et mois dû : ceux dont elle hérite,
    puis les siens, qui remplacent tous ceux de leurs rubriques."""
    if nom not in ACADEMIES:
        raise ValueError(f"académie inconnue {nom!r}, connues : {sorted(ACADEMIES)}")
    section = ACADEMIES[nom]
    herites = retards_academie(section["herite"]) if "herite" in section else {}
    propres = [lit_retard(entree, f"academies.toml [{nom}]") for entree in section.get("retards", [])]
    return remplace(herites, propres)
