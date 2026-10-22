"""La paye à venir, mois par mois, d'après carriere.toml et agent.toml.

Le point d'entrée des programmes qui veulent le net prévu sans tenir eux-mêmes la
mécanique de bpaye (un budget, un tableau de trésorerie). Les bulletins se génèrent depuis janvier de la
première année demandée : la RAFP se plafonne sur l'année civile, et un premier
bulletin en cours d'année la calculerait faux. Les colles prévues de chaque rentrée y
sont injectées (colles.inject_colles_prevues) ; les colles déclarées, les rappels et les
autres événements d'une Paye (Paye.colle, Paye.retard_indice…) n'y sont pas.

Deux payeurs, deux versements. Le salaire et les colles du lycée d'affectation arrivent
sur le bulletin principal (net, dont colles) ; les colles d'un autre établissement
arrivent sur un bulletin à part, d'un autre payeur, réglé selon les vacances de sa zone
(net_colles_externes, colles.brut_colles_externes, charges.net_colles_seules).
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from bpaye.charges import net_colles_seules
from bpaye.codes import COLLES
from bpaye.colles import brut_colles_externes, inject_colles_prevues
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import charge_agent
from bpaye.paye import Paye
from bpaye.utils import decalage_mois

__all__ = ["NetPrevu", "nets_prevus"]


@dataclass(frozen=True, slots=True)
class NetPrevu:
    annee: int
    mois: int
    net: float  # net à payer du bulletin principal, en euros
    colles: float  # dont colles du lycée d'affectation, en euros
    net_colles_externes: float = 0.0  # net des colles d'autres établissements, versé à part


def nets_prevus(
    carriere: Path, agent: Path, debut: tuple[int, int], nombre: int, bareme: Bareme = BAREME
) -> list[NetPrevu]:
    """Le net à payer prévu de ``nombre`` mois à partir de ``debut`` (année, mois), avec
    ``bareme`` (celui du paquet par défaut)."""
    fonc = charge_agent(agent, carriere)
    annee, mois = debut
    avance = mois - 1  # bulletins depuis janvier, pour la RAFP
    paye = Paye(fonc, libelle="prévision", bareme=bareme)
    paye.generate(startyear=annee, startmonth=1, n=avance + nombre)
    for rentree in sorted(fonc.colles_prevues):
        inject_colles_prevues(paye, rentree)
    externes: dict[tuple[int, int], float] = defaultdict(float)
    for blocs in fonc.colles_externes.values():
        for bloc in blocs:  # un bulletin par établissement : chacun arrondit ses retenues
            for (y, m), brut in brut_colles_externes(bloc, bareme=bareme).items():
                externes[(y, m)] += net_colles_seules(brut, dt.date(y, m, 1), bareme)
    nets = []
    for rang in range(nombre):
        y, m = decalage_mois(annee, mois, rang)
        bulletin = paye(y, m)
        assert bulletin is not None  # généré ci-dessus
        colles = bulletin.total(COLLES)
        nets.append(NetPrevu(y, m, round(bulletin.net, 2), round(colles, 2), round(externes[(y, m)], 2)))
    return nets
