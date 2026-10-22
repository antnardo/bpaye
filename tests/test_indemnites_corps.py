import datetime as dt

import pytest

from bpaye import charge_agent
from bpaye.config import BAREME
from bpaye.indemnites_corps import _mensuel, montant_directeur
from bpaye.paye import Paye

CARRIERE = """
[depart]
nom        = "Agent Fictif"
grille     = "GRILLE_CERTCN"
corps      = "{corps}"
echelon    = 5
anciennete = 0.0
date       = 2024-09-01

[[detachements]]
date    = 2024-09-01
detache = false

[[rentrees]]
year = 2025
{rentree}
"""


def _bulletin(configuration, corps, rentree, mois=(2026, 1)):
    carriere, agent = configuration
    carriere.write_text(CARRIERE.format(corps=corps, rentree=rentree), encoding="utf-8")
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=9, n=6)
    return paye(*mois)


def _valeur(bulletin, code):
    return sum(ligne.valeur for ligne in bulletin if ligne.code == code)


def _codes(bulletin):
    return {ligne.code for ligne in bulletin if ligne.valeur}


def test_cpe_indemnite_forfaitaire_sans_isoe_ni_hsa(configuration):
    b = _bulletin(configuration, "CPE", "")
    assert _valeur(b, 200414) == round(2743.97 / 12, 2)
    assert not _codes(b) & {200364, 200205, 200576}


@pytest.mark.parametrize(("specialite", "annuel"), [("EDA", 3338.16), ("EDO", 3338.16)])
def test_psyen_indemnite_de_fonctions_selon_la_specialite(configuration, specialite, annuel):
    b = _bulletin(configuration, "PsyEN", f'specialite = "{specialite}"')
    assert _valeur(b, 202205) == round(annuel / 12, 2)


def test_psyen_sans_specialite_refuse(configuration):
    with pytest.raises(ValueError, match="spécialité"):
        _bulletin(configuration, "PsyEN", "")


def test_documentaliste_sujetions_particulieres_au_lieu_de_l_isoe(configuration):
    b = _bulletin(configuration, "Certifié", "documentaliste = true")
    assert _valeur(b, 200413) == round(2550.00 / 12, 2)
    assert _valeur(b, 200364) == 0


def test_cpe_pendant_l_indexation_sans_montant_refuse():
    with pytest.raises(ValueError, match="pas de montant vérifié"):
        _mensuel("ind_cpe", dt.date(2018, 1, 31), BAREME)


@pytest.mark.parametrize(
    ("classes", "reseau", "date", "attendu"),
    [
        (3, None, dt.date(2026, 1, 31), 1970.62 + 1000.0),
        (4, None, dt.date(2026, 1, 31), 1970.62 + 1400.0),
        (12, "REP+", dt.date(2026, 1, 31), (1970.62 + 1800.0) * 1.5),
        # Seuils d'avant le 1/9/2014 : 1 à 4 classes, puis 5 à 9.
        (4, None, dt.date(2013, 1, 31), 1295.62 + 300.0),
    ],
)
def test_directeur_iss_selon_classes_et_reseau(classes, reseau, date, attendu):
    assert montant_directeur(classes, reseau, date) == pytest.approx(attendu)


def test_directeur_iss_recodee_en_septembre_2024(configuration):
    b = _bulletin(configuration, "PE", "ors = 24\ndirection_ecole = 5")
    assert _valeur(b, 202568) == round((1970.62 + 1400.0) / 12, 2)
