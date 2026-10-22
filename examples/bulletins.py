"""La carrière, les bulletins et la paye prévue d'un des agents fictifs d'examples/.

python examples/bulletins.py                  # college : une certifiée en collège
python examples/bulletins.py agrege_cpge      # un agrégé en classe préparatoire
python examples/bulletins.py carriere_longue  # une professeure des écoles, depuis 2006
"""

import datetime as dt
import sys
from pathlib import Path

from bpaye import Paye, charge_dossier
from bpaye.prevision import nets_prevus

EXEMPLES = Path(__file__).parent
# Avant 2011, le taux de la pension civile n'est pas relu : bpaye refuse ces bulletins.
PREMIERE_ANNEE = 2011
DERNIERE_ANNEE = 2026


def main(nom: str = "college") -> None:
    dossier = EXEMPLES / nom
    agent = charge_dossier(dossier)

    # La carrière rejouée : échelons, reclassement de 2017, promotions de grade.
    print(f"== {agent.nom} : carrière")
    for date, echelon in agent.echelon.values:
        print(f"  {date}  {agent.grille.value(date)!s:15} échelon {echelon:2}  indice {agent.indice(date):g}")

    # Tous ses bulletins, de sa première année civile complète (2011 au plus tôt) à la dernière.
    debut = max(agent.echelon.values[0][0].year + 1, PREMIERE_ANNEE)
    paye = Paye(agent, libelle=nom)
    paye.generate_annees(debut, DERNIERE_ANNEE)
    print(f"\n== Brut et net par année civile, de {debut} à {DERNIERE_ANNEE}")
    for annee in range(debut, DERNIERE_ANNEE + 1):
        bulletins = paye.annee(annee)
        brut = sum(b.revenus for b in bulletins)
        net = sum(b.net for b in bulletins)
        print(f"  {annee}  brut {brut:10.2f} €   net {net:10.2f} €")

    # Un bulletin, ligne par ligne.
    print(f"\n== Bulletin de janvier {DERNIERE_ANNEE}")
    print(paye(DERNIERE_ANNEE, 1))

    # La paye prévue de l'année scolaire 2025-2026, mois par mois, colles prévues comprises.
    print("== Paye prévue de septembre 2025 à juin 2026")
    for mois in nets_prevus(dossier / "carriere.toml", dossier / "agent.toml", (2025, 9), 10):
        date = dt.date(mois.annee, mois.mois, 1)
        print(f"  {date:%m/%Y}  {mois.net:9.2f} €  dont colles {mois.colles:8.2f} €")


if __name__ == "__main__":
    main(*sys.argv[1:2])
