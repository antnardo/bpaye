"""Exporter ses bulletins et leur calcul en CSV, pour un tableur.

python examples/exporter.py DOSSIER_DES_PDF DOSSIER_DE_L_AGENT DOSSIER_DE_SORTIE

DOSSIER_DES_PDF contient les bulletins de l'ENSAP, nommés AAAA_MM_BP_mois.pdf ;
DOSSIER_DE_L_AGENT, son carriere.toml et son agent.toml (examples/college, par exemple).
Écrit dans DOSSIER_DE_SORTIE un fichier par bulletin, nommé comme son PDF (le bulletin
colonne par colonne, et le calcul de bpaye pour celui de l'employeur du mois), puis
bulletins_lus.csv et bulletins_calcules.csv : une ligne par bulletin, avec son employeur,
une colonne par code. Le calcul est celui de la carrière seule, sans les
événements que l'agent ajoute (colles, retards ponctuels) : un script qui les ajoute à sa
Paye appelle bpaye.export de la même façon. Il faut l'extra pdf.
"""

import datetime as dt
import sys
from pathlib import Path

from bpaye import Paye, charge_dossier
from bpaye.bulletins import trouve_bulletins
from bpaye.export import ecrit_mois, ecrit_tous_les_mois


def main(dossier: str, agent_dossier: str, sortie: str) -> None:
    agent = charge_dossier(agent_dossier)
    trouves = trouve_bulletins(dossier, agent, range(agent.date_depart.year, dt.date.today().year + 1))
    if not trouves:
        sys.exit(f"Aucun bulletin dans {dossier}")
    premier, dernier = trouves[0].date, trouves[-1].date
    paye = Paye(agent)
    paye.generate_annees(premier.year, dernier.year)

    Path(sortie).mkdir(parents=True, exist_ok=True)
    lignes = []
    for b in trouves:
        # Le calcul ne va qu'au bulletin de l'employeur du mois (bpaye.bulletins).
        calcul = paye(b.date.year, b.date.month) if b.compare else None
        ecrit_mois(Path(sortie) / f"{b.chemin.stem}.csv", b.lu, calcul)
        lignes.append((b.date, f"{b.rattachement} : {b.nom}" if b.nom else b.rattachement, b.lu, calcul))
    ecrit_tous_les_mois(Path(sortie) / "bulletins_lus.csv", Path(sortie) / "bulletins_calcules.csv", lignes)
    print(f"{len(trouves)} bulletins, de {premier:%m/%Y} à {dernier:%m/%Y}, exportés dans {sortie}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
