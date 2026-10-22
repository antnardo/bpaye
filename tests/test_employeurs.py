import datetime as dt

import pytest

from bpaye.employeurs import Employeur, lit_employeur, normalise_poste


def test_normalise_poste_reduit_les_espaces():
    assert normalise_poste(" 08  A445   072 0314 ") == "08 A445 072 0314"


@pytest.mark.parametrize(
    ("sirets", "poste", "attendu"),
    [
        ({"10800000000000"}, "", True),
        (set(), "08  A445 072 0314", True),  # un rappel sans SIRET, sous son code de gestion
        ({"19750000000000"}, "26 0005 075 0655", False),
    ],
)
def test_reconnait_par_siret_ou_par_poste(sirets, poste, attendu):
    employeur = Employeur("Lycée militaire", ("10800000000000",), ("08 A445 072 0314",))
    assert employeur.reconnait(sirets, poste) is attendu


def test_lit_employeur_accepte_un_texte_ou_une_liste():
    date, employeur = lit_employeur(
        {"date": dt.date(2019, 9, 1), "nom": "Lycée", "siret": ["1", "2"], "poste": "26  0005"}, "test"
    )
    assert date == dt.date(2019, 9, 1)
    assert employeur == Employeur("Lycée", ("1", "2"), ("26 0005",))


def test_lit_employeur_refuse_un_employeur_sans_repere():
    with pytest.raises(ValueError, match="siret ou à un poste"):
        lit_employeur({"date": dt.date(2019, 9, 1), "nom": "Lycée"}, "test")
