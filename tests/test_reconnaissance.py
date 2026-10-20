import datetime as dt

import pytest

from bpaye.reconnaissance import _grilles_candidates, lire_en_tete, reconnait


def test_en_tete_lue_colonne_par_colonne(bulletin_agrege):
    e = lire_en_tete(bulletin_agrege())
    assert (e.mois, e.grade, e.enfants, e.echelon, e.indice) == (
        dt.date(2026, 8, 31),
        "PROF. AGREGE CN",
        0,
        4,
        547,
    )
    assert e.taux_pas == 6.20


def test_agrege_reconnu_par_son_grade_et_son_indice(bulletin_agrege):
    r = reconnait(bulletin_agrege())
    assert (r.corps, r.classe, r.grille, r.echelon) == ("Agrégé", "CN", "GRILLE_AGCN", 4)
    assert (r.fraction, r.zone_residence, r.enfants_sft) == (1.0, 1, 0)
    assert "professeur principal (ISOE part modulable)" in r.constats
    assert r.remarques == ()


def test_indice_qui_n_est_pas_celui_de_l_echelon_signale(bulletin_agrege):
    r = reconnait(bulletin_agrege(echelon="03"))
    assert r.echelon == 3
    assert any("indice 547 supérieur à celui du 3e échelon" in m for m in r.remarques)


@pytest.mark.parametrize(
    ("grade", "grilles"),
    [
        ("PROF.CHAIRE SUPER.", ["GRILLE_CHSUP"]),
        ("PROF. AGREGE HC", ["GRILLE_AGHC"]),
        ("PROF. CERTIFIE CN", ["GRILLE_CERTCN"]),
        ("PROF. ECOLES H.CL", ["GRILLE_CERTHC"]),
    ],
)
def test_grille_designee_par_le_grade_imprime(grade, grilles):
    assert _grilles_candidates(grade) == grilles
