import datetime as dt

import pytest

from bpaye.charges import net_colles_seules
from bpaye.colles import (
    SEMAINES_COLLES,
    Colles,
    CollesExternes,
    brut_colles_externes,
    inject_colles_prevues,
    semaines_de_colles,
)
from bpaye.fonctionnaire import Fonctionnaire, charge_agent
from bpaye.hsa import valeur_colle
from bpaye.paye import Paye

EXTERNES = """
[[rentrees.colles_externes]]
etablissement = "Lycée d'une autre zone"
zone          = "B"
colles        = { 6 = 1.0 }
colles_debut  = 2025-09-22
colles_fin    = 2026-04-10
"""


@pytest.fixture
def paye_avec_reliquat(configuration):
    carriere, agent = configuration
    carriere.write_text(
        carriere.read_text(encoding="utf-8").replace("161 = 4.0 }", "161 = 4.0 }\ncolles_classe = 7.0"),
        encoding="utf-8",
    )
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=1, n=24)
    return paye


def test_semaines_de_colles_plafonnees_a_vingt_semaines_les_premieres():
    # Le calendrier zone C compte 23 semaines de cours du 22/09/2025 au 10/04/2026.
    semaines = semaines_de_colles(dt.date(2025, 9, 22), dt.date(2026, 4, 10))
    assert sum(semaines.values()) == SEMAINES_COLLES
    assert semaines[(2025, 9)] == 2
    assert (2026, 4) not in semaines


def test_semaines_de_colles_periode_courte_gardee_entiere():
    semaines = semaines_de_colles(dt.date(2025, 9, 22), dt.date(2025, 11, 30))
    assert sum(semaines.values()) == 8


def test_reliquat_de_la_classe_declare_en_mai_au_code_de_la_classe(paye_avec_reliquat):
    colles = inject_colles_prevues(paye_avec_reliquat, 2025)
    reliquat = [c for c in colles if "reliquat" in c.comm]
    # 40 élèves en seconde année, grille d'agrégé : ORS 8 h, code 161 ; 25 − 20 semaines.
    assert [(c.date, c.code, c.heures) for c in reliquat] == [(dt.date(2026, 5, 1), 161, 35.0)]
    assert reliquat[0].date_paiement.month == 7


def test_sans_budget_de_classe_pas_de_reliquat(configuration):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=1, n=24)
    colles = inject_colles_prevues(paye, 2025)
    assert sum(c.heures for c in colles) == 4.0 * SEMAINES_COLLES
    assert not [c for c in colles if "reliquat" in c.comm]


def test_colles_externes_lues_avec_leur_zone(configuration):
    carriere = configuration[0]
    carriere.write_text(carriere.read_text(encoding="utf-8") + EXTERNES, encoding="utf-8")
    (externes,) = Fonctionnaire().load_carriere(carriere).colles_externes[2025]
    assert (externes.zone, externes.heures, externes.etablissement) == (
        "B",
        {6: 1.0},
        "Lycée d'une autre zone",
    )


def test_colles_externes_zone_inconnue_refusee(configuration):
    carriere = configuration[0]
    carriere.write_text(
        carriere.read_text(encoding="utf-8") + EXTERNES.replace('"B"', '"D"'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="'D'"):
        Fonctionnaire().load_carriere(carriere)


def test_brut_colles_externes_selon_les_semaines_de_leur_zone():
    externes = CollesExternes("B", dt.date(2025, 9, 22), dt.date(2026, 4, 10), {6: 1.0})
    brut = brut_colles_externes(externes)
    # Zone B : février 2 semaines, mars 3, payés en avril et en mai.
    taux = valeur_colle(6, dt.date(2026, 2, 1))
    assert (brut[(2026, 4)], brut[(2026, 5)]) == (round(2 * taux, 2), round(3 * taux, 2))
    assert sum(brut.values()) == pytest.approx(SEMAINES_COLLES * taux, abs=0.05)


@pytest.mark.parametrize(("brut", "net"), [(286.48, 259.17), (358.10, 323.98), (1000.00, 904.70)])
def test_net_colles_seules_csg_en_deux_parts_arrondies(brut, net):
    assert net_colles_seules(brut, dt.date(2026, 3, 1)) == net


def test_paiement_all_paie_chaque_colle_sur_le_bulletin(configuration):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=1, n=12)
    colles = Colles()
    colles.append(2025, 3, {161: 2.0, 6: 1.0})
    bulletin = paye(2025, 5)
    colles.paiement_all(bulletin)
    assert all(c.payee for c in colles)
    attendu = round(sum(c.total for c in colles), 2)
    assert round(sum(ligne.valeur for ligne in bulletin.get_all_fromcode(200207)), 2) == attendu


def test_colles_prevues_suivent_la_zone_du_lycee(configuration):
    carriere, agent = configuration
    mois_par_zone = {}
    for zone in ("A", "C"):
        carriere.write_text(
            carriere.read_text(encoding="utf-8")
            .replace('zone_vacances = "A"\n', "")
            .replace("date       = 2019-09-01\n", f'date       = 2019-09-01\nzone_vacances = "{zone}"\n', 1),
            encoding="utf-8",
        )
        fonc = charge_agent(agent, carriere)
        paye = Paye(fonc)
        paye.generate(startyear=2025, startmonth=1, n=24)
        mois_par_zone[zone] = {c.date.month: c.heures for c in inject_colles_prevues(paye, 2025)}
    # Février : les vacances des zones A et C ne tombent pas les mêmes semaines.
    assert mois_par_zone["A"][2] != mois_par_zone["C"][2]


def test_heures_entieres_retrouvees_d_un_montant():
    from bpaye.colles import heures_du_montant
    from bpaye.hsa import valeur_colle

    jour = dt.date(2025, 3, 1)
    montant = round(valeur_colle(157, jour) * 22, 2)
    entieres = [
        (lecture.code, round(lecture.heures))
        for lecture in heures_du_montant(montant, jour)
        if lecture.entiere
    ]
    assert (157, 22) in entieres


def test_un_montant_peut_se_lire_a_deux_codes():
    # 8/10 = 28/35 : 28 h au code 157 valent 35 h au code 090, toutes deux affichées.
    from bpaye.colles import decrit_colles
    from bpaye.hsa import valeur_colle

    jour = dt.date(2025, 1, 1)
    texte = decrit_colles(round(valeur_colle(157, jour) * 28, 2), jour)
    assert "28 h au code 157" in texte and "35 h au code 090" in texte


def test_montant_melange_dit_tel_quel():
    from bpaye.colles import decrit_colles

    assert "aucun nombre entier" in decrit_colles(1216.94, dt.date(2019, 2, 1))


def test_sens_du_code_tire_des_ors():
    from bpaye.colles import sens_du_code

    assert sens_du_code(161).startswith(
        "taux agrégé, classe à 8 h de service : 2e année scientifique de plus de 35"
    )
