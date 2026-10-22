import datetime as dt

import pytest

from bpaye import load_agent
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.grille import GRILLE_CHSUP
from bpaye.hsa import code_colle, hsa, hsa_majo, valeur_colle, valeur_hsi
from bpaye.point import POINT

# Taux de l'heure de colle, par code, du récapitulatif HIO 2025-2026.
TAUX_HIO = [(161, 68.69), (6, 61.06), (7, 54.96), (157, 80.57), (1, 71.62), (90, 64.46)]


@pytest.mark.parametrize(("code", "taux"), TAUX_HIO)
def test_taux_du_code_conforme_au_recapitulatif(code, taux):
    assert round(valeur_colle(code, dt.date(2025, 11, 1)), 2) == taux


def test_taux_suit_le_code_declare_pas_le_corps_du_colleur():
    # Une chaire supérieure déclarée en 06 est payée au taux des agrégés.
    jour = dt.date(2025, 11, 1)
    assert valeur_colle(6, jour) < valeur_colle(1, jour)


@pytest.mark.parametrize(("chaire_sup", "agrege"), [(157, 161), (1, 6), (90, 7)])
def test_code_chaire_superieure_meme_ors_que_son_pendant(chaire_sup, agrege):
    jour = dt.date(2025, 11, 1)
    assert valeur_hsi(POINT, GRILLE_CHSUP, jour, code=chaire_sup) == valeur_hsi(
        POINT, GRILLE_CHSUP, jour, code=agrege
    )


def test_colles_prevues_en_codes_chaire_superieure_acceptees(configuration):
    carriere = configuration[0]
    carriere.write_text(
        carriere.read_text(encoding="utf-8").replace("161 = 4.0", "157 = 7.0, 1 = 2.0"), encoding="utf-8"
    )
    assert Fonctionnaire().load_carriere(carriere).colles_prevues[2025].heures == {157: 7.0, 1: 2.0}


@pytest.mark.parametrize(
    ("ors", "corps", "code"),
    [(8, "Agrégé", 161), (9, "Agrégé", 6), (8, "Chaire Supérieure", 157), (10, "Chaire Supérieure", 90)],
)
def test_code_colle_selon_ors_et_corps(ors, corps, code):
    assert code_colle(ors, corps) == code


def test_code_colle_sans_equivalent_refuse():
    with pytest.raises(ValueError, match="11 h en Chaire Supérieure"):
        code_colle(11, "Chaire Supérieure")


@pytest.mark.parametrize("mois", [10, 1, 6])
def test_hsa_et_majoration_au_centime(configuration, mois):
    carriere, agent = configuration
    fonc = load_agent(agent)
    fonc.load_carriere(carriere)
    jour = dt.date(2025 if mois >= 9 else 2026, mois, 28)
    for ligne in (hsa(fonc, jour), hsa_majo(fonc, jour)):
        assert ligne.valeur == round(ligne.valeur, 2) != 0


def test_hsa_arrondies_depuis_le_taux_annuel_exact(monkeypatch):
    # Sept HSA en 2018 : 7/9 du taux exact (2 742,4055 €) = 2 132,98 € sur le bulletin ;
    # le taux arrondi d'abord (2 742,41 €) aurait donné 2 132,99 €.
    import bpaye.hsa

    monkeypatch.setattr(
        bpaye.hsa,
        "taux_hsa_annuel",
        lambda f, d, rounded=True, bareme=None: 2742.4055 if not rounded else 2742.41,
    )

    class Agent:
        def vs(self, date):
            return 7

    assert bpaye.hsa.hsa(Agent(), dt.date(2018, 12, 31)).valeur == 2132.98
