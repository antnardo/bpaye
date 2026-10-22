import datetime as dt

import pytest

from bpaye.charges import crds, csg, csg_nonded, ir, seuil_abattement
from bpaye.fonctionnaire import Fonctionnaire

PART_EMPLOYEUR_MGEN = 37.70


@pytest.mark.parametrize(
    ("assiette", "attendu"),
    [
        (4005, 270.13),  # un arrondi unique donnerait 270,14 (comme mai 2026)
        (4020, 271.14),  # une troncature donnerait 271,13 (comme septembre 2026)
    ],
)
def test_csg_deductible_deux_arrondis_salaire_puis_part_employeur(assiette, attendu):
    ligne = csg(assiette, dt.date(2026, 9, 30), PART_EMPLOYEUR_MGEN)
    assert -ligne.valeur == attendu


@pytest.mark.parametrize(
    ("jour", "attendu"), [(dt.date(2025, 3, 31), 118.06), (dt.date(2026, 3, 31), 118.07)]
)
def test_assiette_tronquee_par_l_ancien_logiciel_arrondie_par_le_nouveau(jour, attendu):
    # 5 007 × 0,9825 = 4 919,3775 : 4 919,37 jusqu'en janvier 2026, 4 919,38 depuis.
    assert -csg_nonded(5007, jour).valeur == attendu


def test_csg_deductible_sans_mgen_simple_arrondi():
    # 4000 × 0,9825 = 3930 ; 6,8 % = 267,24
    assert -csg(4000, dt.date(2025, 9, 30)).valeur == 267.24


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        (dt.date(2004, 12, 31), 145.35),  # 3 000 × 95 % × 5,1 %
        (dt.date(2005, 1, 31), 148.41),  # 3 000 × 97 % × 5,1 %
        (dt.date(2011, 12, 22), 148.41),  # 1,75 % le 23/12/2011 seulement
        (dt.date(2011, 12, 23), 150.32),  # 3 000 × 98,25 % × 5,1 %
        (dt.date(2018, 1, 31), 200.43),  # 3 000 × 98,25 % × 6,8 %
    ],
)
def test_csg_deductible_aux_dates_charnieres_suit_reduction_et_part_deductible(jour, attendu):
    assert -csg(3000, jour).valeur == attendu


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        (dt.date(2004, 12, 31), 14.25),  # 3 000 × 95 % × 0,5 %
        (dt.date(2011, 12, 22), 14.55),  # 3 000 × 97 % × 0,5 %
        (dt.date(2012, 6, 30), 14.74),  # 1,75 % comme la CSG, dès 2012 et non 2015
    ],
)
def test_crds_suit_la_reduction_de_la_csg(jour, attendu):
    assert -crds(3000, jour).valeur == attendu


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        (dt.date(2010, 12, 21), float("inf")),  # pas de plafond avant la loi 2010-1594
        (dt.date(2010, 12, 22), 4 * 2885),
        (dt.date(2011, 6, 30), 4 * 2946),
        (dt.date(2019, 6, 30), 13508),
        (dt.date(2026, 9, 30), 16020),
    ],
)
def test_seuil_abattement_vaut_quatre_plafonds_du_mois(jour, attendu):
    assert seuil_abattement(jour) == attendu


def test_csg_entre_ancien_et_nouveau_seuil_reste_abattue():
    # 15 000 € dépassait les 13 508 € figés ; 4 × 4 005 = 16 020 € en 2026 : 15 000 × 98,25 %.
    assert -csg(15000, dt.date(2026, 9, 30)).valeur == 1002.15


def test_csg_au_dela_du_seuil_abat_la_seule_part_sous_le_seuil():
    # 20 000 − 16 020 × 1,75 % = 19 719,65 ; × 6,8 % = 1 340,94
    assert -csg(20000, dt.date(2026, 9, 30)).valeur == 1340.94


def test_load_agent_deux_agents_gardent_chacun_leur_taux(configuration, tmp_path):
    carriere, agent = configuration
    autre = tmp_path / "autre.toml"
    autre.write_text(
        agent.read_text(encoding="utf-8").replace("valeur = 0.05", "valeur = 0.12"), encoding="utf-8"
    )
    premier, second = Fonctionnaire().load_carriere(carriere), Fonctionnaire().load_carriere(carriere)
    premier.load_agent(agent)
    second.load_agent(autre)
    jour = dt.date(2025, 3, 31)
    assert (ir(1000, jour, premier.taux_pas).valeur, ir(1000, jour, second.taux_pas).valeur) == (-50, -120)


JUIN_2017 = dt.date(2017, 6, 30)


def test_contribution_de_solidarite_un_pour_cent_de_l_assiette():
    from bpaye.charges import contribution_solidarite

    assert contribution_solidarite(3000.0, JUIN_2017, net_mensuel=2500.0).valeur == -30.0


def test_contribution_de_solidarite_plafonnee_a_quatre_pmss():
    from bpaye.charges import contribution_solidarite
    from bpaye.config import BAREME

    plafond = 4 * BAREME.load("pmss")(JUIN_2017)
    assert contribution_solidarite(plafond + 5000, JUIN_2017, net_mensuel=9000.0).valeur == -round(
        plafond / 100, 2
    )


def test_contribution_de_solidarite_exoneree_sous_le_seuil():
    from bpaye.charges import contribution_solidarite
    from bpaye.point import calc_traitement_brut

    seuil = calc_traitement_brut(285, JUIN_2017)
    assert contribution_solidarite(1500.0, JUIN_2017, net_mensuel=seuil - 0.01).valeur == 0.0
    assert contribution_solidarite(1500.0, JUIN_2017, net_mensuel=seuil).valeur == -15.0


def test_contribution_de_solidarite_supprimee_en_2018():
    from bpaye.charges import contribution_solidarite

    assert contribution_solidarite(3000.0, dt.date(2018, 1, 31), net_mensuel=2500.0).valeur == 0.0
