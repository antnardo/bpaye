import datetime as dt

import pytest

from bpaye import load_agent
from bpaye.bulletins import ANCIEN_EMPLOYEUR, AUTRE_EMPLOYEUR, EMPLOYEUR, trouve_bulletins
from bpaye.pdf import extract_employeur

ANCIEN = ("DRFIP DE LA GIRONDE", "08  A445/072 0314", "LYCEE MILITAIRE", "10800000000000")
ANCIEN_SANS_SIRET = ANCIEN[:3]
ACTUEL = ("DDFIP DE PARIS", "26  0005/075 0655", "LYCEE CIVIL", "19750000000000")
JURY = ("DDFIP DES YVELINES", "22  0836/091 1253", "JURY CONCOURS", "10220000000000")

EMPLOYEURS = """
[[employeur]]
date  = 2007-09-01
nom   = "Lycée militaire"
siret = "10800000000000"
poste = "08 A445 072 0314"

[[employeur]]
date  = 2019-09-01
nom   = "Lycée civil"
siret = "19750000000000"
"""


@pytest.fixture
def agent(configuration):
    def agent(employeurs=EMPLOYEURS):
        carriere, chemin = configuration
        texte = chemin.read_text(encoding="utf-8")
        if employeurs is not None:
            chemin.write_text(texte + employeurs, encoding="utf-8")
        else:
            chemin.write_text(texte.replace('siret = "19750000000000"\n', ""), encoding="utf-8")
        fonc = load_agent(chemin)
        fonc.load_carriere(carriere)
        return fonc

    return agent


@pytest.fixture
def dossier(tmp_path, faux_bulletin_pdf):
    dossier = tmp_path / "bulletins"
    dossier.mkdir()

    def ecrit(nom, employeur, lignes=None):
        kwargs = {"employeur": employeur} | ({"lignes": lignes} if lignes is not None else {})
        faux_bulletin_pdf(dossier / nom, **kwargs)

    return dossier, ecrit


def test_extract_employeur_lit_l_en_tete(tmp_path, faux_bulletin_pdf):
    faux_bulletin_pdf(tmp_path / "b.pdf", employeur=ANCIEN)
    entete = extract_employeur(tmp_path / "b.pdf")
    assert entete.gestionnaire == "DRFIP DE LA GIRONDE"
    assert entete.poste == "08 A445 072 0314"
    assert entete.libelle == "LYCEE MILITAIRE"
    assert entete.sirets == {"10800000000000"}


class TestTrouveBulletins:
    def test_le_bulletin_de_l_employeur_d_abord_quel_que_soit_le_nom(self, agent, dossier):
        chemin, ecrit = dossier
        ecrit("2019_10_BP_octobre.pdf", JURY, [("201357", "IND.JURY.CONC.EXAM.", "100,00")])
        ecrit("2019_10_BP_octobre-1.pdf", ACTUEL)
        trouves = trouve_bulletins(chemin, agent(), [2019])
        assert [(b.chemin.name, b.rattachement) for b in trouves] == [
            ("2019_10_BP_octobre-1.pdf", EMPLOYEUR),
            ("2019_10_BP_octobre.pdf", AUTRE_EMPLOYEUR),
        ]
        assert trouves[0].nom == "Lycée civil" and trouves[1].nom == "JURY CONCOURS"

    def test_rappel_d_un_ancien_employeur_sans_siret(self, agent, dossier):
        chemin, ecrit = dossier
        ecrit("2019_08_BP_aout.pdf", ANCIEN)
        ecrit("2019_10_BP_octobre copie.pdf", ANCIEN_SANS_SIRET)
        ecrit("2019_10_BP_octobre.pdf", ACTUEL)
        rattaches = {
            (b.date, b.chemin.name): b.rattachement for b in trouve_bulletins(chemin, agent(), [2019])
        }
        assert rattaches == {
            (dt.date(2019, 8, 1), "2019_08_BP_aout.pdf"): EMPLOYEUR,
            (dt.date(2019, 10, 1), "2019_10_BP_octobre.pdf"): EMPLOYEUR,
            (dt.date(2019, 10, 1), "2019_10_BP_octobre copie.pdf"): ANCIEN_EMPLOYEUR,
        }

    def test_sans_employeur_declare_celui_du_traitement_brut(self, agent, dossier):
        chemin, ecrit = dossier
        ecrit("2019_10_BP_octobre copie.pdf", JURY, [("201357", "IND.JURY.CONC.EXAM.", "100,00")])
        ecrit("2019_10_BP_octobre.pdf", ACTUEL)
        trouves = trouve_bulletins(chemin, agent(employeurs=None), [2019])
        assert [(b.chemin.name, b.compare) for b in trouves] == [
            ("2019_10_BP_octobre.pdf", True),
            ("2019_10_BP_octobre copie.pdf", False),
        ]

    def test_un_siret_seul_vaut_employeur_de_toute_la_carriere(self, agent, dossier):
        chemin, ecrit = dossier
        ecrit("2019_10_BP_octobre.pdf", ACTUEL)  # conftest : siret = "19750000000000"
        assert [b.rattachement for b in trouve_bulletins(chemin, agent(employeurs=""), [2019])] == [EMPLOYEUR]
