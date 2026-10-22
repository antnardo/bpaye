"""Les extraits de code de README.md et docs/DOC.md, sur l'agente fictive des exemples."""

import re
from pathlib import Path

import pytest

from bpaye import Paye, charge_dossier
from bpaye.prevision import nets_prevus

EXEMPLE = Path(__file__).resolve().parents[1] / "examples" / "college"


@pytest.fixture
def paye():
    agente = charge_dossier(EXEMPLE)
    paye = Paye(agente)
    paye.generate(startyear=2025, startmonth=1, n=12)
    return paye


def test_doc_evenements_hors_carriere(paye):
    net_novembre = paye(2025, 11).net
    paye.retard_indice((2025, 9), (2025, 11), indice=562)
    paye.retard_paiement((2025, 3), 200205)
    paye.colle((2025, 10), {161: 6.0})
    paye.hse((2025, 11), 3)
    paye.erreur((2025, 4), (2025, 6), 50.0, 200364)
    paye.gipa(2023, (2025, 12))
    assert paye(2025, 11).net != net_novembre


def test_doc_selection_et_somme(paye):
    assert paye.select(200364, 2025).somme().calcul == 2550.0
    assert len(paye.select(lambda b: b.net_imposable, 2025)) == 12


def test_doc_prevision_commence_au_mois_demande():
    mois = nets_prevus(EXEMPLE / "carriere.toml", EXEMPLE / "agent.toml", (2025, 9), 12)
    assert [(m.annee, m.mois) for m in mois][:2] == [(2025, 9), (2025, 10)]


def _blocs(nom, langue):
    texte = (EXEMPLE.parents[1] / nom).read_text(encoding="utf-8")
    return re.findall(rf"```{langue}\n(.*?)```", texte, flags=re.S)


def test_readme_montre_la_vraie_sortie_du_bulletin():
    agente = charge_dossier(EXEMPLE)
    paye = Paye(agente)
    paye.generate(startyear=2026, startmonth=1, n=12)
    assert str(paye(2026, 1)).strip() == _blocs("README.md", "text")[0].strip()


def test_readme_montre_la_vraie_somme_et_les_nets_prevus():
    agente = charge_dossier(EXEMPLE)
    paye = Paye(agente)
    paye.generate(startyear=2026, startmonth=1, n=12)
    sortie = _blocs("README.md", "text")[1].splitlines()
    assert sortie[0] == str(paye.select(200364, 2026).somme())
    mois = nets_prevus(EXEMPLE / "carriere.toml", EXEMPLE / "agent.toml", (2026, 8), 3)
    assert sortie[1:] == [f"{m.annee} {m.mois} {m.net}" for m in mois]


def test_readme_montre_la_vraie_sortie_de_bpaye_lire(bulletin_agrege, capsys):
    from bpaye.reconnaissance import main

    main([str(bulletin_agrege())])
    attendu = next(b for b in _blocs("README.md", "text") if b.startswith("== 2026_08_BP_aout.pdf"))
    assert capsys.readouterr().out.strip() == attendu.strip()
