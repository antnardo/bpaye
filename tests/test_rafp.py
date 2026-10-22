import datetime as dt

import pytest

from bpaye.rafp import RAFP


def _cotisations(rafp, mois, brut, primes):
    return [-rafp(dt.date(annee, m, 28), brut, primes).valeur for annee, m in mois]


def test_primes_sous_le_plafond_cotisent_chaque_mois_sur_leur_montant():
    # 100 € de primes pour un plafond de 600 € (20 % de 3 000 €) : 5 % de 100 € chaque mois.
    rafp = RAFP()
    assert _cotisations(rafp, [(2025, m) for m in range(1, 5)], 3000, 100) == [5.0] * 4


def test_primes_au_dessus_du_plafond_cotisent_sur_le_plafond():
    rafp = RAFP()
    assert _cotisations(rafp, [(2025, m) for m in range(1, 4)], 3000, 1000) == [30.0] * 3


def test_plafond_cumule_sur_l_annee_rattrape_un_mois_sans_primes():
    # Janvier sans prime laisse 600 € de plafond inemployé, que février utilise.
    rafp = RAFP()
    assert -rafp(dt.date(2025, 1, 31), 3000, 0).valeur == 0.0
    assert -rafp(dt.date(2025, 2, 28), 3000, 1000).valeur == 50.0


def test_cumul_repart_au_premier_janvier():
    # Une année 2025 plafonnée ne laisse rien en réserve : janvier 2026 cotise sur ses primes.
    rafp = RAFP()
    _cotisations(rafp, [(2025, m) for m in range(1, 13)], 3000, 1000)
    assert -rafp(dt.date(2026, 1, 31), 3000, 100).valeur == 5.0


def test_annee_calculee_apres_une_annee_suivante_garde_son_propre_cumul():
    rafp = RAFP()
    _cotisations(rafp, [(2025, m) for m in range(1, 13)], 3000, 1000)
    assert _cotisations(rafp, [(2024, m) for m in range(1, 4)], 3000, 100) == [5.0] * 3


@pytest.mark.parametrize("primes", [0.0, 100.0, 600.0, 2000.0])
def test_mois_recalcule_redonne_la_meme_cotisation(primes):
    rafp = RAFP()
    premiere = -rafp(dt.date(2025, 3, 31), 3000, primes).valeur
    assert -rafp(dt.date(2025, 3, 31), 3000, primes).valeur == premiere


def test_cotisation_cumulee_tronquee_varie_d_un_centime():
    # 2025 : 20 % de 3 962,84 € = 792,568 € d'assiette par mois ; le cumul tronqué prélève
    # 39,62 € en janvier et juillet, 39,63 € les autres mois, comme les bulletins.
    rafp = RAFP()
    mois = [-rafp(dt.date(2025, m, 28), 3962.84, 1000.0).valeur for m in range(1, 13)]
    assert mois[0] == mois[6] == 39.62
    assert set(mois[1:6] + mois[7:]) == {39.63}
