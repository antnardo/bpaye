import copy
from types import MappingProxyType

import pytest

from bpaye import Paye, charge_agent
from bpaye.classes import Ligne
from bpaye.codes import COLLES, PENSION, PRELEVEMENT_SOURCE, RDT, REGULARISATION_PENSION
from bpaye.comparaison import compare_mois, montants, signe
from bpaye.pdf import BulletinLu


@pytest.fixture
def paye(configuration):
    carriere, agent = configuration
    paye = Paye(charge_agent(agent, carriere))
    paye.generate(startyear=2026, startmonth=1, n=2)
    return paye


def lu_de(bulletin, **pied):
    """Le bulletin lu qu'imprimerait la paie pour ce bulletin calculé : chaque montant dans
    sa colonne, positif sauf une réduction de cotisation (453000)."""
    lus = {}
    for ligne in bulletin:
        if ligne.valeur and (s := signe(ligne.code)) is not None:
            cle = f"{ligne.code:06d}"
            lus[cle] = round(lus.get(cle, 0.0) + s * ligne.valeur, 2)
    pied.setdefault("net_payer", round(bulletin.net, 2))
    pied.setdefault("montant_imp", round(bulletin.net_imposable, 2))
    return BulletinLu(montants=MappingProxyType(lus), **pied)


def sans_revenu(bulletin, code):
    """Le bulletin calculé, privé du revenu ``code`` et ses retenues recalculées."""
    refait = copy.deepcopy(bulletin)
    refait.append(Ligne(-refait.get_fromcode(code).valeur, code=code, classe="INDEM"), recalc=True)
    return refait


def test_bulletin_identique_au_calcul_conforme(paye):
    comparaison = compare_mois(paye, lu_de(paye.bulletin(2026, 1)), 2026, 1)
    assert comparaison.ecarts == ()
    assert comparaison.conforme
    assert comparaison.net_du == comparaison.net_percu


def test_revenu_absent_ses_retenues_sont_induites(paye):
    lu = lu_de(sans_revenu(paye.bulletin(2026, 1), RDT))
    comparaison = compare_mois(paye, lu, 2026, 1)
    propres = {e.code: e for e in comparaison.imprevus}
    assert list(propres) == [RDT]
    assert propres[RDT].nature == "calculé, absent du bulletin"
    assert not comparaison.conforme


def test_retenue_seule_differente_reste_un_ecart_propre(paye):
    calcule = paye.bulletin(2026, 1)
    lus = dict(lu_de(calcule).montants)
    lus[f"{PRELEVEMENT_SOURCE}"] = round(lus[f"{PRELEVEMENT_SOURCE}"] + 10.0, 2)
    comparaison = compare_mois(paye, BulletinLu(montants=MappingProxyType(lus), montant_imp=1000.0), 2026, 1)
    assert [(e.code, e.induit) for e in comparaison.ecarts] == [(PRELEVEMENT_SOURCE, False)]
    assert comparaison.taux_ir_lu == pytest.approx(lus[f"{PRELEVEMENT_SOURCE}"] / 1000.0)


def test_heures_ponctuelles_prises_au_bulletin_et_calculees(paye):
    net_avant = paye.bulletin(2026, 1).net
    lus = dict(lu_de(paye.bulletin(2026, 1)).montants)
    lus[f"{COLLES}"] = 100.0
    comparaison = compare_mois(paye, BulletinLu(montants=MappingProxyType(lus)), 2026, 1)
    assert comparaison.ponctuels == {COLLES: 100.0}
    assert COLLES not in {e.code for e in comparaison.ecarts}
    assert comparaison.net_du > net_avant  # les colles entrent au calcul, CSG et impôt compris


def test_rappel_par_decompte_inconnu_du_calcul_non_conforme(paye):
    comparaison = compare_mois(paye, lu_de(paye.bulletin(2026, 1), rappel_decompte=500.0), 2026, 1)
    assert comparaison.ecart_rappel == 500.0
    assert not comparaison.conforme


def test_regularisation_de_pension_comptee_avec_la_pension(paye):
    calcule = paye.bulletin(2026, 1)
    lus = dict(lu_de(calcule).montants)
    lus[f"{PENSION}"] = round(lus[f"{PENSION}"] - 20.0, 2)
    lus[f"{REGULARISATION_PENSION}"] = 20.0
    comparaison = compare_mois(paye, BulletinLu(montants=MappingProxyType(lus)), 2026, 1)
    assert comparaison.ecarts == ()


def test_compare_ne_change_le_calcul_que_des_heures_ponctuelles(paye):
    net = paye.bulletin(2026, 1).net
    compare_mois(paye, lu_de(sans_revenu(paye.bulletin(2026, 1), RDT)), 2026, 1)
    assert paye.bulletin(2026, 1).net == net


def test_montants_ajoutent_les_rappels_au_code():
    assert montants({"200205": 300.0, "200205_R": 50.0, "_net_payer": 1.0, "_unknown": []}) == {200205: 350.0}


@pytest.mark.parametrize(
    ("code", "attendu"), [(101000, 1), (PENSION, -1), (PRELEVEMENT_SOURCE, -1), (404001, None)]
)
def test_signe_selon_la_categorie(code, attendu):
    assert signe(code) == attendu
