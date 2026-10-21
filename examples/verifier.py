"""Vérifier ses bulletins : les lire, contrôler la lecture, les comparer au calcul.

python examples/verifier.py DOSSIER_DES_PDF ANNEE [DOSSIER_DE_L_AGENT]

DOSSIER_DES_PDF contient les bulletins de l'ENSAP, nommés AAAA_MM_BP_mois.pdf
(2025_03_BP_mars.pdf) ; DOSSIER_DE_L_AGENT, son carriere.toml et son agent.toml
(examples/college, par exemple). Il faut l'extra pdf :
pip install "bpaye[pdf] @ git+https://github.com/antnardo/bpaye".
"""

import sys
from pathlib import Path

from bpaye import Paye, load_agent
from bpaye.codes import ALL_CODES, equivalents
from bpaye.format import MOIS
from bpaye.pdf import ecart_totaux, extract_bulletin, find_pdfs


def lire(dossier: Path, annee: int, siret: str | None = None) -> dict[int, dict]:
    """Les bulletins principaux de l'année, mois par mois, lus et contrôlés ; avec un SIRET,
    ceux de ce seul gestionnaire."""
    lus = {}
    print(f"== Bulletins {annee} lus dans {dossier}")
    for mois, chemins in sorted(find_pdfs(dossier, annee, siret).items()):
        lu = extract_bulletin(chemins[0])
        lus[mois] = lu
        ecart = ecart_totaux(lu)
        controle = "lecture complète" if ecart == 0 else f"écart de {ecart} € avec TOTAUX DU MOIS"
        rappels = sorted(cle[:6] for cle in lu if cle.endswith("_R"))
        print(f"  {MOIS[mois - 1]:9}  net à payer {lu.get('_net_payer', 0.0):9.2f} €  {controle}")
        if rappels:
            print(f"             rappels : {', '.join(rappels)}")
        for code, libelle, montant in lu["_unknown"]:
            print(f"             code inconnu de bpaye : {code} {libelle} ({montant} €)")
    return lus


def comparer(agent_dossier: Path, annee: int, lus: dict[int, dict]) -> None:
    """Pour chaque mois lu, les rubriques où le calcul de bpaye et le bulletin diffèrent."""
    agent = load_agent(agent_dossier / "agent.toml")
    agent.load_carriere(agent_dossier / "carriere.toml")
    paye = Paye(agent)
    paye.generate(startyear=annee, startmonth=1, n=12)  # depuis janvier : RAFP, exonérations

    print(f"\n== Calcul et bulletin, rubrique par rubrique ({agent.nom})")
    for mois, lu in sorted(lus.items()):
        calcul: dict[str, float] = {}
        for ligne in paye(annee, mois):
            code = min(equivalents(f"{ligne.code:06d}"))  # un code par ligne (201228 et 202566)
            calcul[code] = calcul.get(code, 0.0) + abs(ligne.valeur)
        lus_codes = {min(equivalents(cle[:6])) for cle in lu if cle[:1].isdigit()}
        ecarts = []
        for code in sorted(set(calcul) | lus_codes):
            if code in ALL_CODES and ALL_CODES[code]["cat"] not in ("revenu", "retenue"):
                continue  # cotisations patronales et lignes de synthèse : hors calcul
            reel = sum(abs(lu.get(c, 0.0)) + abs(lu.get(c + "_R", 0.0)) for c in equivalents(code))
            if abs(calcul.get(code, 0.0) - reel) > 0.005:
                libelle = ALL_CODES[code]["libelle"] if code in ALL_CODES else ""
                ecarts.append(
                    f"{code} {libelle[:24]:24} calcul {calcul.get(code, 0.0):9.2f}  bulletin {reel:9.2f}"
                )
        print(f"  {MOIS[mois - 1]:9}  " + ("identique" if not ecarts else f"{len(ecarts)} écart(s)"))
        for ligne in ecarts:
            print(f"             {ligne}")


def main(dossier: str, annee: str, agent: str | None = None) -> None:
    siret = load_agent(Path(agent) / "agent.toml").siret if agent is not None else None
    lus = lire(Path(dossier), int(annee), siret)
    if agent is not None:
        comparer(Path(agent), int(annee), lus)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
