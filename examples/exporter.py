"""Exporter ses bulletins et leur calcul en CSV, pour un tableur.

python examples/exporter.py DOSSIER_DES_PDF DOSSIER_DE_L_AGENT DOSSIER_DE_SORTIE

DOSSIER_DES_PDF contient les bulletins de l'ENSAP, nommés AAAA_MM_BP_mois.pdf ;
DOSSIER_DE_L_AGENT, son carriere.toml et son agent.toml (examples/college, par exemple).
Écrit dans DOSSIER_DE_SORTIE un fichier par mois (AAAA-MM.csv : le bulletin colonne par
colonne, et le calcul de bpaye), puis bulletins_lus.csv et bulletins_calcules.csv : une
ligne par mois, une colonne par code. Le calcul est celui de la carrière seule, sans les
événements que l'agent ajoute (colles, retards ponctuels) : un script qui les ajoute à sa
Paye appelle bpaye.export de la même façon. Il faut l'extra pdf.
"""

import datetime as dt
import sys
from pathlib import Path

from bpaye import Paye, load_agent
from bpaye.export import ecrit_mois, ecrit_tous_les_mois
from bpaye.pdf import extract_bulletin, find_pdfs, is_agent_bulletin


def _choisit(chemins: list[Path], siret: str | None) -> Path:
    if len(chemins) > 1 and siret:
        return next((c for c in chemins if is_agent_bulletin(c, siret)), chemins[0])
    return chemins[0]


def main(dossier: str, agent_dossier: str, sortie: str) -> None:
    agent = load_agent(Path(agent_dossier) / "agent.toml")
    agent.load_carriere(Path(agent_dossier) / "carriere.toml")
    debut = agent.date_depart.year
    # Tous les employeurs : le SIRET ne départage que deux bulletins du même mois.
    lus = {
        dt.date(annee, mois, 1): extract_bulletin(_choisit(chemins, agent.siret))
        for annee in range(debut, dt.date.today().year + 1)
        for mois, chemins in find_pdfs(dossier, annee).items()
    }
    if not lus:
        sys.exit(f"Aucun bulletin dans {dossier}")
    premier, dernier = min(lus), max(lus)
    paye = Paye(agent)
    n = (dernier.year - premier.year) * 12 + dernier.month  # depuis janvier : RAFP, exonérations
    paye.generate(startyear=premier.year, startmonth=1, n=n)

    Path(sortie).mkdir(parents=True, exist_ok=True)
    mois = [(date, lu, paye(date.year, date.month)) for date, lu in sorted(lus.items())]
    for date, lu, calcul in mois:
        ecrit_mois(Path(sortie) / f"{date:%Y-%m}.csv", lu, calcul)
    ecrit_tous_les_mois(Path(sortie) / "bulletins_lus.csv", Path(sortie) / "bulletins_calcules.csv", mois)
    print(f"{len(mois)} mois, de {premier:%m/%Y} à {dernier:%m/%Y}, exportés dans {sortie}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
