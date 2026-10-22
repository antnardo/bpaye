import datetime as dt

import pytest

from bpaye.point import calc_traitement_brut, traitement_indiciaire, valeur_point


def test_traitement_d_un_indice_au_centime():
    # IM 480 au 1/10/2008, point annuel de 54,8475 € : 480 × 54,8475 / 12 = 2 193,90 €.
    assert calc_traitement_brut(480, dt.date(2008, 10, 31)) == 2193.90


def test_valeur_du_point_suit_ses_revalorisations():
    assert valeur_point(dt.date(2023, 7, 31)) > valeur_point(dt.date(2023, 6, 30))


def test_point_avant_sa_premiere_valeur_refuse():
    with pytest.raises(ValueError, match="MANQUANT"):
        valeur_point(dt.date(2003, 1, 31))


class _AgentQuiChange:
    """Un 8e échelon d'agrégé pris le 8 mars 2018 : 7 jours à l'IM 646, 23 à l'IM 695."""

    def changement_d_indice(self, date):
        return (7, 646, 695) if (date.year, date.month) == (2018, 3) else None

    def indice(self, date):
        return 695


class TestTraitementIndiciaire:
    def test_echelon_en_cours_de_mois_au_trentieme_des_deux_traitements(self):
        # Décompte de rappel de juillet 2018 : 706,33 + 2 496,86 = 3 203,19 €, quand le
        # prorata de l'indice (683,56 × point) donnait 3 203,17 €.
        assert traitement_indiciaire(_AgentQuiChange(), dt.date(2018, 3, 31)) == 3203.19

    def test_mois_sans_changement_au_seul_indice(self):
        assert traitement_indiciaire(_AgentQuiChange(), dt.date(2018, 4, 30)) == 3256.78
