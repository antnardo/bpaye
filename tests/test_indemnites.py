import datetime as dt

import pytest

from bpaye import charge_agent
from bpaye.config import BAREME
from bpaye.hsa import reference_hsa, taux_hsa_annuel
from bpaye.indemnite_comp_csg import indemnite_comp_csg
from bpaye.indemnite_residence import calc_indemnite_residence
from bpaye.indemnites import (
    calc_transport,
    indemnite_education_prioritaire,
    indemnite_fonctions_part_cpge,
    indemnite_isae,
    indemnite_isoe,
    isoe_part_modulable,
    participation_psc,
    prime_attractivite,
    prime_equipement_info,
)
from bpaye.indemnites_corps import _mensuel
from bpaye.paye import Paye

CERTIFIE = """
[depart]
nom        = "Agent Fictif"
grille     = "GRILLE_CERTCN"
corps      = "{corps}"
echelon    = {echelon}
anciennete = 0.0
date       = 2024-12-01

[[rentrees]]
year = 2024
hsa_vs = 2
{extra}
"""

AGENT = """
[ir]
type = "Taux"
values = [{ date = 2019-01-01, valeur = 0.05 }]

[[enfants]]
date   = 2019-01-01
nombre = 0

[[residence]]
date = 2019-09-01
zone = 3

[ic_csg]
type   = "Fixe"
unite  = "mensuel"
values = [{ date = 2018-01-01, valeur = 57.55 }]
"""

JOUR = dt.date(2025, 1, 31)


def _agent(tmp_path, corps="Certifié", echelon=4, extra="", grille="GRILLE_CERTCN"):
    carriere, agent = tmp_path / "carriere.toml", tmp_path / "agent.toml"
    texte = CERTIFIE.format(corps=corps, echelon=echelon, extra=extra).replace("GRILLE_CERTCN", grille)
    carriere.write_text(texte, encoding="utf-8")
    agent.write_text(AGENT, encoding="utf-8")
    return charge_agent(agent, carriere)


def test_ors_du_corps_hors_cpge(tmp_path):
    assert _agent(tmp_path).ors(JOUR) == 18


def test_ors_imposee_par_la_rentree(tmp_path):
    assert _agent(tmp_path, extra="ors = 20").ors(JOUR) == 20


def test_hors_cpge_ni_ifp_ni_base_agregee(tmp_path):
    fonc = _agent(tmp_path)
    assert indemnite_fonctions_part_cpge(fonc, JOUR) is None
    grille, majoration = reference_hsa(fonc, JOUR)
    assert (grille.value(JOUR).corps, majoration) == ("Certifié", 0.0)


def test_taux_hsa_certifie_cn_formule_du_decret(tmp_path):
    # (395 + 678) / 2 × 59,0734 / 18 × 9/13, décret 50-1253, art. 2.
    attendu = (395 + 678) / 2 * 59.0734 / 18 * 9 / 13
    assert taux_hsa_annuel(_agent(tmp_path), JOUR) == pytest.approx(attendu, abs=0.01)


def test_hors_classe_majore_de_dix_pour_cent(tmp_path):
    hc = _agent(tmp_path, echelon=2, grille="GRILLE_CERTHC")
    assert reference_hsa(hc, JOUR)[1] == pytest.approx(0.10)


def test_isoe_second_degre_isae_premier_degre(tmp_path):
    certifie = _agent(tmp_path)
    pe = _agent(tmp_path, corps="PE", extra="ors = 24")
    assert indemnite_isoe(certifie, JOUR).valeur == pytest.approx(2550 / 12)
    assert indemnite_isae(certifie, JOUR) is None
    assert indemnite_isoe(pe, JOUR) is None
    assert indemnite_isae(pe, JOUR).valeur == pytest.approx(2550 / 12)


@pytest.mark.parametrize(("echelon", "annuel"), [(1, 2130), (4, 3180), (9, 400), (10, 0)])
def test_prime_attractivite_selon_l_echelon(tmp_path, echelon, annuel):
    ligne = prime_attractivite(_agent(tmp_path, echelon=echelon), JOUR)
    assert (ligne.valeur if ligne else 0) == round(annuel / 12, 2)


def test_prime_attractivite_ni_hors_classe_ni_chaire_superieure(tmp_path):
    assert prime_attractivite(_agent(tmp_path, echelon=2, grille="GRILLE_CERTHC"), JOUR) is None
    chsup = _agent(tmp_path, corps="Chaire Supérieure", echelon=1, grille="GRILLE_CHSUP", extra="ors = 9")
    assert prime_attractivite(chsup, JOUR) is None


def test_rep_plus_et_professeur_principal(tmp_path):
    fonc = _agent(tmp_path, extra='education_prioritaire = "REP+"\nprofesseur_principal = "3e"')
    assert indemnite_education_prioritaire(fonc, JOUR).valeur == pytest.approx(5114 / 12)
    pp = isoe_part_modulable(fonc, JOUR)
    assert (pp.code, pp.valeur) == (202566, round(1497.84 / 12, 2))


def test_education_prioritaire_inconnue_refusee(tmp_path):
    fonc = _agent(tmp_path, extra='education_prioritaire = "ZEP"')
    with pytest.raises(ValueError, match="REP"):
        indemnite_education_prioritaire(fonc, JOUR)


@pytest.mark.parametrize(("jour", "plancher"), [(dt.date(2021, 6, 30), 313), (dt.date(2024, 6, 30), 366)])
def test_indemnite_residence_plancher_d_indice_date(jour, plancher):
    point = 4.0
    assert calc_indemnite_residence(1, 100.0, point, jour) == pytest.approx(0.03 * plancher * point, abs=0.01)


def test_bulletin_certifie_complet_se_genere(tmp_path):
    paye = Paye(_agent(tmp_path))
    paye.generate(startyear=2024, startmonth=12, n=12)
    codes = {ligne.code for ligne in paye(2025, 1)}
    assert {101000, 200364, 202326}.issubset(codes)
    assert 200597 not in codes


@pytest.mark.parametrize(
    ("date", "plafond"),
    [
        (dt.date(2022, 12, 31), 86.16),
        (dt.date(2023, 1, 31), 96.36),
        (dt.date(2024, 1, 31), 99.00),  # 950,40 × 1,25 / 12 (décret 2010-676, art. 3)
        (dt.date(2025, 1, 31), 101.75),
        (dt.date(2026, 1, 31), 104.04),
    ],
)
def test_transport_plafonne_au_plafond_officiel_du_1er_janvier(date, plafond):
    assert calc_transport(1000.0, date) == plafond


def test_participation_psc_nulle_avant_sa_creation_en_2022():
    assert participation_psc(dt.date(2015, 6, 30)).valeur == 0.0


def test_prime_equipement_absente_avant_sa_creation_en_2021():
    assert prime_equipement_info(dt.date(2020, 1, 31)) is None


def test_indemnite_compensatrice_csg_absente_avant_2018():
    assert indemnite_comp_csg(dt.date(2015, 6, 30)) is None


@pytest.mark.parametrize(
    ("section", "jour"), [("ind_documentaliste", dt.date(2016, 10, 31)), ("ind_cpe", dt.date(2014, 5, 31))]
)
def test_indemnite_de_corps_manquante_refusee(section, jour):
    with pytest.raises(ValueError, match="pas de montant vérifié"):
        _mensuel(section, jour, BAREME)


def test_transport_sans_abonnement_ne_lit_pas_le_plafond():
    assert calc_transport(0.0, dt.date(2010, 1, 31)) == 0.0


DETACHE = "\n[[detachements]]\ndate    = 2024-12-01\ndetache = true\n"


def test_indemnite_de_la_defense_au_montant_de_la_decision_individuelle(tmp_path):
    from bpaye.indemnites import indemnite_detachement

    fonc = _agent(tmp_path, extra=DETACHE + "indemnite_fonction = 1633.92\n")
    assert indemnite_detachement(fonc, JOUR).valeur == 136.16


def test_indemnite_de_la_defense_sans_montant_declare_refusee(tmp_path):
    from bpaye.indemnites import indemnite_detachement

    with pytest.raises(ValueError, match="indemnite_fonction"):
        indemnite_detachement(_agent(tmp_path, extra=DETACHE), JOUR)
