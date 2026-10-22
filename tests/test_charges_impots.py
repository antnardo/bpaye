import datetime as dt

import pytest

from bpaye import charge_agent
from bpaye.charges import csg, csg_basculee, csg_nonded
from bpaye.charges_impots import facteur_hs_net, reduc_cotis_hs
from bpaye.colles import inject_colles_prevues
from bpaye.paye import Paye

PLAFOND_BRUT = 8037.0


@pytest.fixture
def paye(configuration):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=1, n=24)
    inject_colles_prevues(paye, 2025)
    return paye


def test_csg_des_heures_exonerees_basculee_en_non_deductible():
    # 6 000 € d'assiette dont 2 000 € d'heures exonérées : 5 895 et 1 965 € abattus.
    jour = dt.date(2025, 1, 31)
    assert -csg(6000, jour, 0.0, 2000).valeur == 267.24  # 6,8 % × (5 895 − 1 965)
    assert -csg_nonded(6000, jour, 0.0, 2000).valeur == 275.10  # 141,48 + 133,62
    assert csg_basculee(6000, jour, 2000) == 133.62
    total_sans = -(csg(6000, jour).valeur + csg_nonded(6000, jour).valeur)
    assert (
        round(-(csg(6000, jour, 0.0, 2000).valeur + csg_nonded(6000, jour, 0.0, 2000).valeur), 2)
        == total_sans
    )


def test_plafond_annuel_consomme_dans_l_ordre_puis_plus_rien(paye):
    annee = [paye(2026, m) for m in range(1, 13)]
    exonerees = [b.hs_exonerees for b in annee]
    assert sum(b.hs_brut for b in annee) > PLAFOND_BRUT
    assert round(sum(exonerees), 2) == PLAFOND_BRUT
    plein = next(i for i, x in enumerate(exonerees) if x < annee[i].hs_brut)
    assert all(x == b.hs_brut for x, b in zip(exonerees[:plein], annee[:plein], strict=True))
    assert all(x == 0 for x in exonerees[plein + 1 :])


def test_011200_net_de_la_csg_deductible(paye):
    janvier = paye(2026, 1)
    assert janvier.hs_exa_net == pytest.approx(janvier.hs_exonerees * facteur_hs_net(janvier.date), abs=0.01)


def test_heures_ajoutees_en_janvier_reduisent_l_exoneration_des_mois_suivants(paye):
    avant = [paye(2026, m).hs_exonerees for m in range(1, 13)]
    paye.colle(original_date=(2025, 11), codesheures={161: 20.0}, decalage=2)  # payées en janvier
    apres = [paye(2026, m).hs_exonerees for m in range(1, 13)]
    assert apres[0] > avant[0]
    assert round(sum(apres), 2) == PLAFOND_BRUT
    assert apres[1:] != avant[1:]


@pytest.mark.parametrize("jour", [dt.date(2008, 3, 31), dt.date(2012, 8, 31)])
def test_heures_sup_du_regime_tepa_refusees_faute_de_texte_relu(jour):
    with pytest.raises(ValueError, match="MANQUANT"):
        reduc_cotis_hs(500.0, 30000.0, jour)


def test_heures_sup_de_2016_sans_reduction_de_cotisations():
    # Loi 2012-958, art. 3 : réduction abrogée pour les heures effectuées depuis le 1/9/2012.
    assert reduc_cotis_hs(500.0, 30000.0, dt.date(2016, 2, 29)) is None


def test_heures_sup_de_2019_ont_leur_reduction_de_cotisations():
    assert reduc_cotis_hs(500.0, 30000.0, dt.date(2019, 1, 31)).valeur == 25.0


def test_facteur_net_des_heures_exonerees_depuis_2018():
    assert facteur_hs_net(dt.date(2025, 1, 31)) == pytest.approx(0.93319)
