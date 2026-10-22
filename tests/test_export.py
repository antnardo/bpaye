import datetime as dt
from types import MappingProxyType

import pytest

from bpaye import Paye, load_agent
from bpaye.export import (
    MONTANT_IMPOSABLE,
    NET_A_PAYER,
    ecrit_mois,
    ecrit_tous_les_mois,
    lignes_du_mois,
    montants_calcules,
    montants_lus,
)
from bpaye.pdf import BulletinLu, extract_bulletin


@pytest.fixture
def paye(configuration):
    carriere, agent = configuration
    fonctionnaire = load_agent(agent)
    fonctionnaire.load_carriere(carriere)
    paye = Paye(fonctionnaire)
    paye.generate(startyear=2026, startmonth=1, n=2)
    return paye


@pytest.fixture
def lu(tmp_path, faux_bulletin_pdf):
    faux_bulletin_pdf(tmp_path / "2026_01_BP_janvier.pdf")
    return extract_bulletin(tmp_path / "2026_01_BP_janvier.pdf")


def _lignes_csv(chemin):
    return [ligne.split(";") for ligne in chemin.read_text(encoding="utf-8-sig").splitlines()]


def test_montants_lus_reunit_rappels_et_equivalents():
    lu = BulletinLu(montants=MappingProxyType({"200205": 300.0, "200205_R": 50.0, "202566": 20.0}))
    assert montants_lus(lu) == {"200205": 350.0, "201228": 20.0}


def test_montants_lus_garde_les_codes_inconnus():
    lu = BulletinLu(inconnus=(("299999", "PRIME NOUVELLE", 12.5),))
    assert montants_lus(lu) == {"299999": 12.5}


def test_montants_calcules_retenues_dans_le_sens_du_bulletin(paye):
    calcules = montants_calcules(paye(2026, 1))
    assert calcules["101000"] > 0
    assert calcules["401301"] > 0  # la CSG, négative pour bpaye, s'imprime positive à déduire


class TestLignesDuMois:
    def test_lignes_lues_dans_l_ordre_du_bulletin(self, lu, paye):
        lignes = lignes_du_mois(lu, paye(2026, 1))
        assert [ligne.code for ligne in lignes[:5]] == ["101000", "200205", "200205", "401301", "404001"]
        assert [ligne.colonne for ligne in lignes[:5]] == [
            "payer",
            "payer",
            "payer",
            "deduire",
            "information",
        ]

    def test_rappel_marque_et_calcul_sur_la_premiere_ligne_du_code(self, lu, paye):
        hsa, rappel = lignes_du_mois(lu, paye(2026, 1))[1:3]
        assert hsa.remarque == "" and hsa.calcul == montants_calcules(paye(2026, 1))["200205"]
        assert rappel.remarque == "rappel" and rappel.calcul is None

    def test_code_du_seul_calcul_ajoute_sans_montant_lu(self, lu, paye):
        isoe = next(ligne for ligne in lignes_du_mois(lu, paye(2026, 1)) if ligne.code == "200364")
        assert isoe.lu is None and isoe.colonne is None and isoe.remarque == "calcul seul"

    def test_pied_net_a_payer_et_montant_imposable(self, lu, paye):
        net, imposable = lignes_du_mois(lu, paye(2026, 1))[-2:]
        assert (net.libelle, net.lu) == (NET_A_PAYER, 2350.0)
        assert (imposable.libelle, imposable.lu) == (MONTANT_IMPOSABLE, 2600.0)
        assert net.calcul == round(paye(2026, 1).net, 2)

    def test_sans_calcul_rien_que_le_bulletin(self, lu):
        lignes = lignes_du_mois(lu, None)
        assert all(ligne.calcul is None for ligne in lignes)
        assert len(lignes) == 7


def test_ecrit_mois_colonnes_du_bulletin_virgule_decimale(tmp_path, lu, paye):
    chemin = tmp_path / "2026-01.csv"
    ecrit_mois(chemin, lu, paye(2026, 1))
    assert chemin.read_bytes().startswith(b"\xef\xbb\xbf")
    lignes = _lignes_csv(chemin)
    assert lignes[0] == ["code", "libellé", "à payer", "à déduire", "pour information", "remarque", "calcul"]
    assert lignes[1][:6] == ["101000", "TRAITEMENT BRUT", "3000,00", "", "", ""]
    assert lignes[4][:5] == ["401301", "C.S.G. DEDUCTIBLE", "", "1000,00", ""]
    assert lignes[5][4] == "2000,00"


def test_ecrit_tous_les_mois_memes_colonnes_un_mois_par_ligne(tmp_path, lu, paye):
    lus, calculs = tmp_path / "lus.csv", tmp_path / "calculs.csv"
    mois = [(dt.date(2026, 2, 1), None, paye(2026, 2)), (dt.date(2026, 1, 1), lu, paye(2026, 1))]
    ecrit_tous_les_mois(lus, calculs, mois)
    table_lue, table_calculee = _lignes_csv(lus), _lignes_csv(calculs)
    assert table_lue[0] == table_calculee[0]
    entete = table_lue[0]
    assert entete[0] == "mois" and entete[-2:] == [NET_A_PAYER, MONTANT_IMPOSABLE]
    assert [rang[0] for rang in table_lue[1:]] == ["2026-01", "2026-02"]
    hsa = next(i for i, nom in enumerate(entete) if nom.startswith("200205 "))
    assert table_lue[1][hsa] == "350,00"  # le mois et son rappel
    assert table_lue[2][hsa] == ""  # pas de bulletin lu en février
    assert table_calculee[2][hsa] != ""
