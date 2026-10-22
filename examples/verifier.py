"""Vérifier ses bulletins : les lire, contrôler la lecture, les comparer au calcul.

python examples/verifier.py DOSSIER_DES_PDF ANNEE [DOSSIER_DE_L_AGENT]

DOSSIER_DES_PDF contient les bulletins de l'ENSAP, nommés AAAA_MM_BP_mois.pdf
(2025_03_BP_mars.pdf) ; DOSSIER_DE_L_AGENT, son carriere.toml et son agent.toml
(examples/college, par exemple). Chaque bulletin est lu à part, de tous les employeurs ; le
calcul ne se compare qu'à celui de l'employeur du mois (bpaye.bulletins). Il faut l'extra
pdf :
pip install "bpaye[pdf] @ git+https://github.com/antnardo/bpaye".
"""

import datetime as dt
import sys
from pathlib import Path

from bpaye import Fonctionnaire, Paye, charge_dossier
from bpaye.bulletins import trouve_bulletins
from bpaye.codes import ALL_CODES, equivalents
from bpaye.colles import decrit_colles
from bpaye.format import MOIS
from bpaye.pdf import BulletinLu, ecart_totaux, extract_bulletin, find_pdfs


def lire(dossier: Path, annee: int, agent: Fonctionnaire | None = None) -> dict[int, BulletinLu]:
    """Tous les bulletins de l'année, de tous les employeurs, lus et contrôlés chacun ; avec
    l'agent, chacun rattaché à son employeur. Rend, par mois, le bulletin de l'employeur, le
    seul que le calcul compare."""
    a_comparer: dict[int, BulletinLu] = {}
    print(f"== Bulletins {annee} lus dans {dossier}")
    if agent is not None:
        trouves = [
            (b.date.month, b.chemin, b.lu, f"{b.rattachement} : {b.nom}", b.compare)
            for b in trouve_bulletins(dossier, agent, [annee])
        ]
    else:
        trouves = [
            (mois, Path(c), extract_bulletin(c), "", i == 0)
            for mois, chemins in sorted(find_pdfs(dossier, annee).items())
            for i, c in enumerate(chemins)
        ]
    for mois, chemin, lu, rattachement, compare in trouves:
        ecart = ecart_totaux(lu)
        controle = "lecture complète" if ecart == 0 else f"écart de {ecart} € avec TOTAUX DU MOIS"
        rappels = sorted(cle[:6] for cle in lu if cle.endswith("_R"))
        net = lu.net_payer or 0.0
        print(f"  {MOIS[mois - 1]:9}  net à payer {net:9.2f} €  {controle}  ({chemin.name})")
        if rattachement:
            print(f"             {rattachement}")
        if rappels:
            print(f"             rappels : {', '.join(rappels)}")
        for code, libelle, montant in lu.inconnus:
            print(f"             code inconnu de bpaye : {code} {libelle} ({montant} €)")
        if compare and mois not in a_comparer:
            a_comparer[mois] = lu
    return a_comparer


def comparer(agent: Fonctionnaire, annee: int, lus: dict[int, BulletinLu]) -> None:
    """Pour chaque mois, les rubriques où le calcul de bpaye et le bulletin de l'employeur
    diffèrent ; les bulletins d'autres employeurs ne se comparent pas."""
    paye = Paye(agent)
    paye.generate_annees(annee)

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
                if code == "200207" and reel:  # ce que le montant du bulletin représente en heures
                    ecarts.append("       " + decrit_colles(reel, dt.date(annee, mois, 1)))
        print(f"  {MOIS[mois - 1]:9}  " + ("identique" if not ecarts else f"{len(ecarts)} écart(s)"))
        for ligne in ecarts:
            print(f"             {ligne}")


def main(dossier: str, annee: str, agent_dossier: str | None = None) -> None:
    agent = None
    if agent_dossier is not None:
        agent = charge_dossier(agent_dossier)
    lus = lire(Path(dossier), int(annee), agent)
    if agent is not None:
        comparer(agent, int(annee), lus)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
