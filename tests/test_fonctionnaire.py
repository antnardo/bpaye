import datetime as dt

import pytest

from bpaye import load_agent
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.utils import add_date_round

CHANGEMENT_DE_CORPS = """
[[changements_corps]]
date           = 2023-09-01
grille         = "GRILLE_CHSUP"
echelon_depart = 4
"""


@pytest.mark.parametrize(
    ("depart", "annees", "jour", "attendu"),
    [
        (dt.date(2023, 9, 1), 2.0, 1, dt.date(2025, 9, 1)),  # 730 jours mènent au 31 août
        (dt.date(2007, 9, 8), 1.5, 8, dt.date(2009, 3, 8)),
        (dt.date(2025, 9, 1), 4.5, 1, dt.date(2030, 3, 1)),
    ],
)
def test_add_date_round_compte_en_mois(depart, annees, jour, attendu):
    assert add_date_round(depart, annees, jour) == attendu


def test_apres_changement_de_corps_echelon_au_jour_du_changement(configuration):
    carriere = configuration[0]
    carriere.write_text(carriere.read_text(encoding="utf-8") + CHANGEMENT_DE_CORPS, encoding="utf-8")
    fonc = Fonctionnaire().load_carriere(carriere)
    assert fonc.echelon(dt.date(2025, 8, 31)) == 4
    assert fonc.echelon(dt.date(2025, 9, 1)) == 5


def test_zone_vacances_lue_dans_le_depart(configuration):
    carriere = configuration[0]
    carriere.write_text(
        carriere.read_text(encoding="utf-8").replace(
            "date       = 2019-09-01\n", 'date       = 2019-09-01\nzone_vacances = "A"\n', 1
        ),
        encoding="utf-8",
    )
    assert Fonctionnaire().load_carriere(carriere).zone_vacances == "A"


def test_zone_vacances_inconnue_refusee(configuration):
    carriere = configuration[0]
    carriere.write_text(
        carriere.read_text(encoding="utf-8").replace(
            "date       = 2019-09-01\n", 'date       = 2019-09-01\nzone_vacances = "Z"\n', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="zone de vacances"):
        Fonctionnaire().load_carriere(carriere)


def test_chaire_superieure_trois_ans_et_demi_au_cinquieme_echelon(configuration):
    # Décret 68-503, art. 4, depuis le 6 août 2023 : 3 ans 6 mois au 5e et au 6e.
    carriere = configuration[0]
    carriere.write_text(carriere.read_text(encoding="utf-8") + CHANGEMENT_DE_CORPS, encoding="utf-8")
    fonc = Fonctionnaire().load_carriere(carriere)
    assert fonc.echelon(dt.date(2025, 9, 1)) == 5
    assert fonc.echelon(dt.date(2029, 2, 28)) == 5
    assert fonc.echelon(dt.date(2029, 3, 1)) == 6  # HEA I
    assert fonc.echelon(dt.date(2032, 9, 1)) == 9  # HEB I, 3 ans 6 mois plus tard


PE = """
[depart]
nom        = "Agent Fictif"
grille     = "GRILLE_CERTCN"
corps      = "PE"
echelon    = 3
anciennete = 0.0
date       = 2006-09-01

[[detachements]]
date    = 2006-09-01
detache = false

{avancements}

[[changements_corps]]
date   = 2023-09-01
grille = "GRILLE_CERTHC"

[[rentrees]]
year = 2024
education_prioritaire = "REP+"
"""

ACCELERATION = '[[avancements]]\nechelon = 9\ntype = "C"\n'
PPCR = '[[avancements]]\ntype = "PPCR"\n'


def _pe(tmp_path, avancements):
    chemin = tmp_path / "carriere.toml"
    chemin.write_text(PE.format(avancements=avancements), encoding="utf-8")
    return Fonctionnaire().load_carriere(chemin)


def test_avancements_appliques_dans_l_ordre_chronologique(tmp_path):
    avant = _pe(tmp_path, ACCELERATION + PPCR)
    apres = _pe(tmp_path, PPCR + ACCELERATION)
    assert avant.echelon.values == apres.echelon.values
    # 8e échelon atteint le 1/3/2020, après le reclassement : 2 ans 6 mois au lieu de 3 ans 6 mois.
    assert avant.echelon.value_todate(9) == dt.date(2022, 9, 1)


def test_hors_classe_d_une_grille_partagee_garde_le_corps(tmp_path):
    fonc = _pe(tmp_path, PPCR)
    assert fonc.corps(dt.date(2024, 1, 31)) == "PE"
    assert fonc.ors(dt.date(2024, 9, 30)) == 24


def test_avant_la_premiere_rentree_service_ordinaire(tmp_path):
    fonc = _pe(tmp_path, PPCR)
    assert fonc.education_prioritaire(dt.date(2010, 1, 31)) is None
    assert fonc.education_prioritaire(dt.date(2024, 9, 30)) == "REP+"
    assert fonc.ors(dt.date(2010, 1, 31)) == 24


@pytest.mark.parametrize("attribut", ["residence", "enfants", "fmd_niveau"])
def test_agent_puis_carriere_ou_l_inverse_donnent_les_memes_donnees(configuration, attribut):
    carriere, agent = configuration
    a = load_agent(agent).load_carriere(carriere)
    b = Fonctionnaire().load_carriere(carriere).load_agent(agent)
    assert getattr(a, attribut).values == getattr(b, attribut).values


def test_agent_puis_carriere_ou_l_inverse_donnent_le_meme_agent(configuration):
    carriere, agent = configuration
    a = load_agent(agent).load_carriere(carriere)
    b = Fonctionnaire().load_carriere(carriere).load_agent(agent)
    date = dt.date(2025, 1, 31)
    assert a.frais_transport(date) == b.frais_transport(date)
    assert a.residence(date) == 1  # celle d'agent.toml, pas la zone 3 par défaut


def test_carriere_seule_complete_par_defaut(configuration):
    carriere, _ = configuration
    fonc = Fonctionnaire().load_carriere(carriere)
    assert (fonc.residence(dt.date(2025, 1, 31)), fonc.enfants(dt.date(2025, 1, 31))) == (3, 0)


def test_enfant_declare_apres_le_depart_absent_avant_sa_date(configuration, tmp_path):
    carriere, agent = configuration
    texte = agent.read_text(encoding="utf-8").replace(
        "[[enfants]]\ndate   = 2019-01-01\nnombre = 0", "[[enfants]]\ndate   = 2022-03-01\nnombre = 1"
    )
    agent.write_text(texte, encoding="utf-8")
    fonc = load_agent(agent)
    fonc.load_carriere(carriere)
    assert fonc.enfants(dt.date(2020, 1, 31)) == 0
    assert fonc.enfants(dt.date(2022, 3, 31)) == 1


def test_indice_du_mois_d_un_avancement_identique_quel_que_soit_le_jour(configuration):
    carriere, agent = configuration
    carriere.write_text(
        carriere.read_text(encoding="utf-8").replace("date       = 2019-09-01", "date       = 2019-09-15"),
        encoding="utf-8",
    )
    fonc = load_agent(agent)
    fonc.load_carriere(carriere)
    jour, echelon = fonc.echelon.values[1]  # premier avancement, un 15
    assert jour.day == 15
    grille = fonc.grille.value(jour)
    attendu = round(14 / 30 * grille.indice(echelon - 1) + 16 / 30 * grille.indice(echelon), 2)
    for dans_le_mois in (jour.replace(day=1), jour, jour.replace(day=28)):
        assert fonc.indice(dans_le_mois) == pytest.approx(attendu, abs=0.01)


AGREGE_PUIS_CHAIRE = """
[depart]
nom        = "Agent Fictif"
grille     = "GRILLE_AGCN"
echelon    = {echelon}
anciennete = 0.0
date       = {depart}

[[detachements]]
date    = {depart}
detache = false

[[changements_corps]]
date   = 2023-09-01
grille = "GRILLE_CHSUP"
"""


def _chaire(tmp_path, echelon, depart):
    chemin = tmp_path / "carriere.toml"
    chemin.write_text(AGREGE_PUIS_CHAIRE.format(echelon=echelon, depart=depart), encoding="utf-8")
    return Fonctionnaire().load_carriere(chemin)


def test_chaire_superieure_sans_anciennete_quand_le_gain_vaut_une_promotion(tmp_path):
    # Agrégé CN 9e (IM 757) → chaire supérieure 4e (IM 800) : +43, autant que le 10e
    # d'agrégé (IM 800). Décret 68-503, art. 5 : l'ancienneté n'est pas conservée.
    fonc = _chaire(tmp_path, 9, "2021-03-01")
    assert (fonc.echelon(dt.date(2023, 9, 1)), fonc.anciennete(dt.date(2023, 9, 1))) == (4, 0.0)


def test_chaire_superieure_garde_l_anciennete_de_l_agrege_au_onzieme(tmp_path):
    # Art. 5, 3e alinéa : l'agrégé du 11e échelon garde son ancienneté (ici un an et demi),
    # dans la limite de la durée de l'échelon d'accueil.
    fonc = _chaire(tmp_path, 11, "2022-03-01")
    assert fonc.anciennete(dt.date(2023, 9, 1)) == pytest.approx(1.5, abs=0.01)
