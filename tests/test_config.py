import datetime as dt

import pytest

from bpaye.config import BAREME, Bareme
from bpaye.point import calc_traitement_brut

HAUSSE = """
[point]
type  = "Fixe"
unite = "annuel"
values = [
  { date = 2023-07-01, valeur = 59.0734 },
  { date = 2027-01-01, valeur = 60.0 },
]
"""


def test_bareme_surcharge_une_section_et_garde_les_autres(tmp_path):
    fichier = tmp_path / "hausse.toml"
    fichier.write_text(HAUSSE, encoding="utf-8")
    bareme = Bareme.depuis_fichiers(fichier)
    janvier = dt.date(2027, 1, 31)
    assert calc_traitement_brut(500, janvier, bareme) == 2500.0
    assert calc_traitement_brut(500, janvier) == calc_traitement_brut(500, janvier, BAREME) < 2500.0
    assert bareme.get("pc") == BAREME.get("pc")


def test_bareme_table_construite_une_fois():
    assert BAREME.load("csg.deductible") is BAREME.load("csg.deductible")


@pytest.mark.parametrize(
    ("date", "annuel"),
    [
        (dt.date(2009, 1, 31), 1183.68),  # l'arrêté, retrouvé depuis le relevé de 2007
        (dt.date(2010, 7, 31), 1199.16),
        (dt.date(2016, 9, 30), 1206.36),
        (dt.date(2017, 2, 28), 1213.56),
        (dt.date(2022, 7, 31), 1256.04),  # 104,67 € par mois sur les bulletins
        (dt.date(2023, 7, 31), 1274.88),  # 106,24 €
        (dt.date(2023, 9, 30), 2550.0),  # nouvel arrêté
    ],
)
def test_isoe_suit_le_point_entre_deux_arretes(date, annuel):
    assert round(BAREME.load("isoe")(date) * 12, 2) == annuel


def test_montant_indexe_suit_une_hausse_du_point(tmp_path):
    fichier = tmp_path / "hausse.toml"
    isoe_2023 = '[isoe]\ntype = "IndexePoint"\nvalues = [{ date = 2023-09-01, valeur = 2550 }]\n'
    fichier.write_text(HAUSSE + isoe_2023, encoding="utf-8")
    isoe = Bareme.depuis_fichiers(fichier).load("isoe")
    assert isoe(dt.date(2027, 1, 31)) == round(2550 * 60.0 / 59.0734 / 12, 2)
