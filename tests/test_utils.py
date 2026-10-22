import datetime as dt

import pytest

from bpaye.classes import Temporal
from bpaye.utils import add_date_round, dernier_jour, range_mois, truncate, veille


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (0.29, 0.29),
        (1.15, 1.15),
        (480 * 54.8475 / 12, 2193.90),  # IM 480 au 1/10/2008 : 2 193,90 exactement
        (-0.1 - 0.2, -0.30),
        (2.199, 2.19),
        (-2.199, -2.20),
    ],
)
def test_truncate_flottant_juste_sous_la_valeur_exacte_garde_le_centime(valeur, attendu):
    assert truncate(valeur, 2) == attendu


@pytest.mark.parametrize(("valeur", "attendu"), [(2.191, 2.20), (2.19, 2.19), (0.1 + 0.2, 0.30)])
def test_truncate_par_le_haut_ne_monte_que_sur_un_vrai_reste(valeur, attendu):
    assert truncate(valeur, 2, up=True) == attendu


@pytest.mark.parametrize(
    ("depart", "annees", "jour", "attendu"),
    [
        (dt.date(2024, 1, 31), 0.25, 31, dt.date(2024, 4, 30)),
        (dt.date(2023, 8, 31), 0.5, 31, dt.date(2024, 2, 29)),
        (dt.date(2024, 1, 31), 1.0, 31, dt.date(2025, 1, 31)),
    ],
)
def test_add_date_round_jour_absent_du_mois_devient_son_dernier(depart, annees, jour, attendu):
    assert add_date_round(depart, annees, jour) == attendu


def test_temporal_change_un_31_sans_planter():
    temporal = Temporal()
    temporal.append(dt.date(2024, 1, 31), 1)
    assert temporal.changed_trigger(dt.date(2024, 2, 15))


def test_dernier_jour_et_veille():
    assert dernier_jour(2024, 2) == dt.date(2024, 2, 29)
    assert veille(dt.date(2025, 3, 1)) == dt.date(2025, 2, 28)


def test_range_mois_passe_l_annee():
    assert list(range_mois((2025, 11), 3)) == [(2025, 11), (2025, 12), (2026, 1)]
