import copy
import datetime as dt
import types
from pathlib import Path
from types import MappingProxyType

import pytest

from bpaye import charge_agent, load_agent
from bpaye.classes import Ligne, ListeLignes
from bpaye.indemnite_residence import calc_indemnite_residence
from bpaye.mgen import mgen_part_employeur
from bpaye.paye import CODE_RAPPEL_TRAITEMENT, Bulletin, Paye, signe_bpaye
from bpaye.pdf import BulletinLu, EmployeurLu
from bpaye.point import calc_traitement_brut, traitement_plein, valeur_point
from bpaye.prevision import nets_prevus
from bpaye.temps_partiel import reduit, taux_surcotisation
from bpaye.utils import truncate


def _paye(configuration, startmonth, n):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=startmonth, n=n)
    return paye


def _hsa(bulletin):
    return [ligne.valeur for ligne in bulletin if ligne.code == 200205 and ligne.valeur]


def test_hsa_d_octobre_payee_en_novembre_en_rappel(configuration):
    paye = _paye(configuration, 1, 24)
    neuvieme = _hsa(paye(2025, 12))[0]
    assert _hsa(paye(2025, 10)) == []
    assert sorted(_hsa(paye(2025, 11))) == [neuvieme, neuvieme]
    assert any("RAPPEL" in ligne.lib for ligne in paye(2025, 11) if ligne.code == 200205)


def test_hsa_d_octobre_sans_novembre_genere_ecartee(configuration):
    paye = _paye(configuration, 9, 2)  # septembre et octobre seulement
    assert _hsa(paye(2025, 10)) == []


def test_ifp_de_septembre_payee_en_octobre(configuration):
    paye = _paye(configuration, 1, 24)
    ifp = [ligne.valeur for ligne in paye(2025, 10) if ligne.code == 200597 and ligne.valeur]
    assert [ligne.valeur for ligne in paye(2025, 9) if ligne.code == 200597 and ligne.valeur] == []
    assert len(ifp) == 2 and ifp[0] == ifp[1]


def _ic_csg(agent, date, valeur):
    """agent.toml dont l'indemnité compensatrice de CSG commence à ``date``."""
    return agent.read_text(encoding="utf-8").replace(
        "values = [{ date = 2018-01-01, valeur = 57.55 }]",
        f"values = [{{ date = {date}, valeur = {valeur} }}]",
    )


def test_indemnite_compensatrice_csg_propre_a_l_agent(configuration):
    _, agent = configuration
    sans = _paye(configuration, 1, 3)
    agent.write_text(_ic_csg(agent, "2020-01-01", 30.0), encoding="utf-8")
    avec = _paye(configuration, 1, 3)
    assert [ligne.valeur for ligne in avec(2025, 2) if ligne.code == 202209] == [30.00]
    assert [ligne.valeur for ligne in sans(2025, 2) if ligne.code == 202209] != [30.00]


@pytest.mark.parametrize(("annee", "mois", "part_employeur_mgen"), [(2025, 8, 0.0), (2026, 9, 37.70)])
def test_net_imposable_sans_frais_exoneres_avec_part_employeur_mgen(
    configuration, annee, mois, part_employeur_mgen
):
    bulletin = _paye(configuration, 1, 24)(annee, mois)
    transport = sum(ligne.valeur for ligne in bulletin if ligne.code == 200039)
    assert transport > 0
    attendu = ListeLignes.net_imposable.fget(bulletin) - transport + part_employeur_mgen
    assert round(bulletin.net_imposable, 2) == round(attendu, 2)


def _bulletin_trouve(monkeypatch, annee, mois, montants):
    """Le dossier ne contient que ce bulletin, celui de l'employeur du mois."""
    import bpaye.bulletins

    trouve = bpaye.bulletins.BulletinTrouve(
        Path("bulletin.pdf"),
        dt.date(annee, mois, 1),
        BulletinLu(montants=MappingProxyType(montants)),
        EmployeurLu(),
        "",
        bpaye.bulletins.EMPLOYEUR,
    )
    monkeypatch.setattr(bpaye.bulletins, "trouve_bulletins", lambda dossier, fonc, annees: [trouve])


def test_select_reel_compte_le_rappel_meme_sans_ligne_bpaye(configuration, monkeypatch):
    # Décembre : l'IFP du mois et un rappel de trois mois que bpaye ne connaît pas.
    bulletin_pdf = {"101000": 1.0, "200597": 93.16, "200597_R": 279.48}
    _bulletin_trouve(monkeypatch, 2025, 12, bulletin_pdf)
    paye = _paye(configuration, 1, 12)
    paye.bull_dir = "bulletins"
    assert paye.select(200597, (2025, 12), (2025, 12)).somme().reel == 372.64


def test_select_reel_ne_double_pas_le_mois_a_deux_lignes(configuration, monkeypatch):
    # Novembre : bpaye porte deux lignes d'HSA (le mois et octobre en rappel).
    bulletin_pdf = {"101000": 1.0, "200205": 100.0, "200205_R": 100.0}
    _bulletin_trouve(monkeypatch, 2025, 11, bulletin_pdf)
    paye = _paye(configuration, 1, 12)
    paye.bull_dir = "bulletins"
    assert paye.select(200205, (2025, 11), (2025, 11)).somme().reel == 200.0


@pytest.mark.parametrize("mois", [9, 10])
def test_aucune_heure_supplementaire_sur_les_bulletins_de_rentree(configuration, mois):
    paye = _paye(configuration, 1, 24)
    assert not [
        ligne for ligne in paye(2025, mois) if ligne.code in (200205, 200576, 200207, 200215) and ligne.valeur
    ]


def test_aucune_heure_supplementaire_payee_avant_fin_novembre(configuration):
    nets = {(n.annee, n.mois): n for n in nets_prevus(*configuration, (2025, 7), 6)}
    assert nets[(2025, 9)].colles == nets[(2025, 10)].colles == 0
    assert nets[(2025, 11)].colles > 0  # les colles de septembre


def test_paye_avec_un_autre_bareme(configuration, tmp_path):
    from bpaye.config import Bareme

    fichier = tmp_path / "isoe.toml"
    isoe = '[isoe]\ntype = "Fixe"\nunite = "annuel"\nvalues = [{ date = 2000-01-01, valeur = 1200.0 }]\n'
    fichier.write_text(isoe, encoding="utf-8")
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc, bareme=Bareme.depuis_fichiers(fichier))
    paye.generate(startyear=2025, startmonth=1, n=1)
    assert paye(2025, 1).get_fromcode(200364).valeur == 100.0


TEMPS_PARTIEL = """
[[rentrees]]
year          = 2025
annee         = 2
effectif      = 40
temps_partiel = 0.8
surcotisation = true
nbi           = 30
pacte         = 1
"""


def _paye_temps_plein_et_partiel(configuration):
    carriere, agent = configuration
    plein = _paye(configuration, 1, 24)
    partielle = carriere.with_name("partiel.toml")
    texte = carriere.read_text(encoding="utf-8")
    partielle.write_text(texte[: texte.rindex("[[rentrees]]")] + TEMPS_PARTIEL, encoding="utf-8")
    fonc = charge_agent(agent, partielle)
    partiel = Paye(fonc)
    partiel.generate_annees(2025, 2026)
    return plein, partiel


def _valeur(bulletin, code):
    return sum(ligne.valeur for ligne in bulletin if ligne.code == code)


@pytest.mark.parametrize("code", [101000, 200364])  # traitement, ISOE part fixe
def test_temps_partiel_80_reduit_traitement_et_primes_aux_six_septiemes(configuration, code):
    plein, partiel = _paye_temps_plein_et_partiel(configuration)
    assert _valeur(partiel(2026, 1), code) == round(_valeur(plein(2026, 1), code) * 6 / 7, 2)


def test_temps_partiel_80_laisse_la_prime_d_equipement_entiere(configuration):
    plein, partiel = _paye_temps_plein_et_partiel(configuration)
    assert _valeur(partiel(2026, 1), 202321) == _valeur(plein(2026, 1), 202321)


def test_nbi_a_temps_partiel_reduite_et_dans_l_assiette_de_la_residence(configuration):
    _, partiel = _paye_temps_plein_et_partiel(configuration)
    q, date = partiel(2026, 1), partiel(2026, 1).date
    assert _valeur(q, 101070) == reduit(calc_traitement_brut(30, date), 6 / 7)
    pt = valeur_point(date)
    zone = partiel.fonctionnaire.residence(date)
    plein = calc_indemnite_residence(zone, traitement_plein(partiel.fonctionnaire, date), pt, date)
    assert _valeur(q, 102000) == reduit(plein, 6 / 7)


def test_surcotisation_sur_le_traitement_d_un_temps_plein(configuration):
    _, partiel = _paye_temps_plein_et_partiel(configuration)
    q, date = partiel(2026, 1), partiel(2026, 1).date
    attendu = round(traitement_plein(partiel.fonctionnaire, date) * taux_surcotisation(0.8, date), 2)
    assert _valeur(q, 101050) == -attendu


def test_pacte_par_neuvieme_d_octobre_a_juin(configuration):
    _, partiel = _paye_temps_plein_et_partiel(configuration)
    assert _valeur(partiel(2025, 9), 202475) == 0
    assert _valeur(partiel(2025, 10), 202475) == round(1250 / 9, 2)
    assert _valeur(partiel(2026, 6), 202475) == round(1250 / 9, 2)
    assert _valeur(partiel(2026, 7), 202475) == 0


def _rafp(paye, mois):
    return round(sum(ligne.valeur for m in mois for ligne in paye(2025, m) if ligne.code == 501080), 2)


def test_rappel_de_traitement_releve_le_plafond_de_la_rafp(configuration):
    # Heures supplémentaires : le plafond de 20 % du traitement est atteint chaque mois.
    a_temps, en_retard = _paye(configuration, 1, 12), _paye(configuration, 1, 12)
    indice = en_retard.fonctionnaire.indice(dt.date(2025, 1, 31))
    en_retard.retard_indice((2025, 1), (2025, 3), indice=indice - 50)
    assert _rafp(en_retard, [1]) > _rafp(a_temps, [1])  # moins de traitement perçu, moins de RAFP
    assert _rafp(en_retard, [1, 2, 3]) == _rafp(a_temps, [1, 2, 3])  # le rappel rattrape


def test_assiette_rafp_sans_traitement_ni_frais(configuration):
    bulletin = _paye(configuration, 1, 12)(2025, 1)
    frais = sum(ligne.valeur for ligne in bulletin if ligne.code in (200039, 200041))
    assert frais > 0
    attendu = bulletin.ind_tot - frais + mgen_part_employeur(bulletin.date)
    assert bulletin.assiette_rafp == pytest.approx(attendu)


def test_assiette_contribution_solidarite_nette_du_transfert_primes_points(configuration):
    bulletin = _paye(configuration, 1, 12)(2025, 1)
    assert bulletin.tpp < 0
    frais = sum(ligne.valeur for ligne in bulletin if ligne.code in (200039, 200041))
    attendu = bulletin.revenus - frais + bulletin.rafp + bulletin.pc + bulletin.tpp
    assert bulletin.assiette_cs == pytest.approx(attendu)


def _total(bulletin, code):
    return sum(ligne.valeur for ligne in bulletin if ligne.code == code)


def _paye_2025(configuration):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2025, startmonth=1, n=6)
    return paye


def test_charge_ajoutee_survit_au_recalcul(configuration):
    paye = _paye_2025(configuration)
    avant = _total(paye(2025, 3), 401201)
    paye.addligne(2025, 3, Ligne(-10.0, "Régularisation CSG", code=401201, classe="CHARGE"))
    paye(2025, 3).generate_charges()
    assert _total(paye(2025, 3), 401201) == pytest.approx(avant - 10.0)


def test_erreur_montant_sur_une_charge_corrige_le_mois_et_rattrape_ensuite(configuration):
    paye, reference = _paye_2025(configuration), _paye_2025(configuration)
    csg = round(paye(2025, 3)(401301).valeur, 2)
    paye.erreur_montant((2025, 3), 401301, csg, csg - 5.0)  # 5 € de CSG retenus en trop
    assert _total(paye(2025, 3), 401301) == pytest.approx(csg - 5.0)
    assert _total(paye(2025, 5), 401301) == pytest.approx(_total(reference(2025, 5), 401301) + 5.0)


def test_promotion_payee_en_retard_a_temps_partiel_rappelle_la_fraction(configuration):
    carriere, agent = configuration
    carriere.write_text(
        carriere.read_text(encoding="utf-8") + "\n[[rentrees]]\nyear = 2026\ntemps_partiel = 0.5\n",
        encoding="utf-8",
    )
    fonc = charge_agent(agent, carriere)
    paye = Paye(fonc)
    paye.generate(startyear=2026, startmonth=9, n=4)
    jour = dt.date(2026, 9, 30)
    indice = fonc.indice(jour)
    paye.retard_indice((2026, 9), (2026, 11), indice=indice - 50)
    # À mi-temps, le traitement d'un mois vaut la moitié d'un temps plein (décret 82-624,
    # art. 2 : 50 % payés 50 %) : deux mois de 50 points à moitié.
    attendu = 2 * (calc_traitement_brut(indice, jour) - calc_traitement_brut(indice - 50, jour)) * 0.5
    rappel = sum(ligne.valeur for ligne in paye(2026, 11) if ligne.code == 999998)
    assert rappel == pytest.approx(attendu, abs=0.02)


def test_select_d_une_fonction_qui_echoue_le_fait_savoir(configuration):
    paye = _paye_2025(configuration)
    with pytest.raises(ZeroDivisionError):
        paye.select(lambda b: 1 / 0, 2025)


def test_trop_percu_lu_sur_le_pdf_garde_son_signe():
    bulletin = types.SimpleNamespace(lignes=[Ligne(101.75, "REMBT", code=200039, classe="INDEM")])
    Bulletin.join(bulletin, {"200039": -22.0})
    assert bulletin.lignes[0].valeur_reel == -22.0


def test_retenue_absente_du_calcul_prend_le_signe_d_une_retenue():
    assert signe_bpaye(Ligne(0.0, "CSG", code=401301, classe="CHARGE")) == -1
    assert signe_bpaye(Ligne(0.0, "REMBT", code=200039, classe="INDEM")) == 1


def test_bulletin_avant_l_entree_dans_la_carriere_refuse(configuration):
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    with pytest.raises(ValueError, match="avant l'entrée"):
        Paye(fonc).generate(startyear=2019, startmonth=8, n=2)


def test_ic_csg_de_l_agent_avant_son_premier_montant_refuse(configuration):
    carriere, agent = configuration
    agent.write_text(_ic_csg(agent, "2020-01-01", 30.0), encoding="utf-8")
    fonc = charge_agent(agent, carriere)
    with pytest.raises(ValueError, match="MANQUANT"):
        Paye(fonc).generate(startyear=2019, startmonth=9, n=4)


def test_agent_sans_ic_csg_refuse_les_mois_depuis_2018(configuration):
    carriere, agent = configuration
    texte = agent.read_text(encoding="utf-8")
    agent.write_text(texte[: texte.index("[ic_csg]")], encoding="utf-8")
    fonc = charge_agent(agent, carriere)
    with pytest.raises(ValueError, match=r"agent\.toml"):
        Paye(fonc).generate(startyear=2025, startmonth=1, n=1)


def test_annee_refuse_un_nom_que_le_bulletin_n_a_pas(configuration):
    paye = _paye_2025(configuration)
    annee = paye.annee(2025)
    assert annee.net == pytest.approx(sum(b.net for b in annee))
    nom = "nett"  # une faute de frappe
    with pytest.raises(AttributeError):
        getattr(annee, nom)
    copy.deepcopy(annee)  # sans TypeError


PSC = """
[[psc]]
date              = 2025-02-01
mutuelle_adherent = 40.00
mutuelle_enfants  = 10.00

[[psc]]
date        = 2026-05-01
cout_option = 7.24
prevoyance  = true
"""


def _avec_psc(configuration, psc=PSC):
    _, agent = configuration
    agent.write_text(agent.read_text(encoding="utf-8") + psc, encoding="utf-8")
    return _paye(configuration, 1, 18)


def _codes(bulletin):
    return {ligne.code: ligne.valeur for ligne in bulletin}


def test_ancienne_mutuelle_precomptee_jusqu_a_la_psc(configuration):
    sans = _paye(configuration, 1, 18)
    avec = _avec_psc(configuration)
    assert {700678, 700671} & set(_codes(avec(2025, 1))) == set()
    assert (_codes(avec(2025, 2))[700678], _codes(avec(2025, 2))[700671]) == (-40.0, -10.0)
    assert {700678, 700671} & set(_codes(avec(2026, 5))) == set()
    # Non déductible : le net imposable ne bouge pas.
    assert avec(2025, 2).net_imposable == pytest.approx(sans(2025, 2).net_imposable)


def test_participations_psc_option_et_prevoyance_depuis_mai_2026(configuration):
    lignes = _codes(_avec_psc(configuration)(2026, 5))
    assert (lignes[202483], lignes[202510]) == (3.62, 7.0)  # la moitié de 7,24 €


def test_participation_option_plafonnee_a_5_euros(configuration):
    psc = "[[psc]]\ndate = 2026-05-01\ncout_option = 12.0\n"
    assert _codes(_avec_psc(configuration, psc)(2026, 6))[202483] == 5.0


@pytest.mark.parametrize(
    ("ajout", "message"),
    [("mutuelle_conjoint = 1.0\n", "mutuelle_conjoint"), ("prevoyance = 7.0\n", "true ou false")],
)
def test_psc_mal_declaree_refusee(configuration, ajout, message):
    _, agent = configuration
    psc = "[[psc]]\ndate = 2026-05-01\n" + ajout
    agent.write_text(agent.read_text(encoding="utf-8") + psc, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_agent(agent)


@pytest.mark.parametrize("code", [201241, 201717, 201300])
def test_hse_d_une_autre_rubrique_au_taux_de_l_hse(configuration, code):
    paye = _paye(configuration, 1, 12)
    paye.hse((2025, 11), 3)
    paye.hse((2025, 11), 3, code=code)
    lignes = [ligne for ligne in paye(2025, 11) if ligne.code in (200215, code)]
    assert [ligne.code for ligne in lignes] == [200215, code]
    assert lignes[0].valeur == lignes[1].valeur


@pytest.mark.parametrize(("code", "exoneree"), [(201241, True), (201717, True), (201300, True)])
def test_hse_exoneree_selon_sa_rubrique(configuration, code, exoneree):
    paye = _paye(configuration, 1, 12)
    avant = paye(2025, 11).hs_brut
    paye.hse((2025, 11), 3, code=code)
    assert (paye(2025, 11).hs_brut > avant) is exoneree


def test_hse_code_inconnu_refuse(configuration):
    paye = _paye(configuration, 1, 12)
    with pytest.raises(ValueError, match="code d'HSE inconnu"):
        paye.hse((2025, 11), 3, code=200205)


@pytest.mark.parametrize("code", [201339, 201856])
def test_vacation_heures_au_taux_declare(configuration, code):
    paye = _paye(configuration, 1, 12)
    paye.vacation((2025, 11), 6, 42.0, code=code)
    assert [ligne.valeur for ligne in paye(2025, 11) if ligne.code == code] == [252.0]


def test_vacation_code_inconnu_refuse(configuration):
    paye = _paye(configuration, 1, 12)
    with pytest.raises(ValueError, match="code de vacation inconnu"):
        paye.vacation((2025, 11), 6, 42.0, code=200215)


ACADEMIE = """
[[academie]]
date = 2019-09-01
nom  = "paris"
"""

FMD_EN_FEVRIER = """
[[retards]]
code = 200041
du   = 1
paye = 2
"""


def test_fmd_en_retard_declare_paye_en_fevrier_en_rappel(configuration):
    _, agent = configuration
    agent.write_text(agent.read_text(encoding="utf-8") + ACADEMIE + FMD_EN_FEVRIER, encoding="utf-8")
    paye = _paye(configuration, 1, 3)
    assert [ligne for ligne in paye(2025, 1) if ligne.code == 200041] == []
    fevrier = [ligne for ligne in paye(2025, 2) if ligne.code == 200041]
    assert [ligne.valeur for ligne in fevrier] == [100.0]
    assert "RAPPEL" in fevrier[0].lib


def test_academie_inconnue_dans_agent_toml_refusee(configuration):
    _, agent = configuration
    agent.write_text(
        agent.read_text(encoding="utf-8") + ACADEMIE.replace("paris", "atlantide"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="académie inconnue"):
        load_agent(agent)


def test_retards_de_l_academie_a_la_date_du_bulletin(configuration):
    _, agent = configuration
    agent.write_text(agent.read_text(encoding="utf-8") + ACADEMIE, encoding="utf-8")
    fonc = load_agent(agent)
    assert (
        set(fonc.retards(dt.date(2019, 8, 31)))
        == set(fonc.retards(dt.date(2025, 10, 31)))
        == {
            (200205, 10),
            (200576, 10),
            (200597, 9),
        }
    )


def test_remplacement_de_courte_duree_a_sa_majoration_propre(configuration, tmp_path):
    from bpaye.config import Bareme
    from bpaye.hsa import hse

    fichier = tmp_path / "rcd.toml"
    fichier.write_text(
        '[hse_majoration_rcd]\ntype = "Taux"\nvalues = [{ date = 2005-08-27, valeur = 2.5 }]\n',
        encoding="utf-8",
    )
    bareme = Bareme.depuis_fichiers(fichier)
    carriere, agent = configuration
    fonc = charge_agent(agent, carriere)
    jour = dt.date(2025, 11, 30)
    rcd = hse(fonc, jour, 10, bareme=bareme, code=201241).valeur
    assert rcd == pytest.approx(2 * hse(fonc, jour, 10, bareme=bareme).valeur, abs=0.01)


def test_majoration_du_remplacement_de_courte_duree_de_25_pour_cent_des_2005():
    from bpaye.config import BAREME

    jour = dt.date(2006, 3, 31)
    assert (BAREME.load("hse_majoration_rcd")(jour), BAREME.load("hse_majoration")(jour)) == (1.25, 1.15)


def test_isoe_modulable_lue_sous_l_un_ou_l_autre_code(configuration):
    bulletin = _paye(configuration, 11, 1)(2025, 11)
    bulletin.append(Ligne(124.82, "ISOE Part modulable", code=202566, classe="INDEM"))
    bulletin.join({"201228": 124.82})
    assert [ligne.valeur_reel for ligne in bulletin if ligne.code == 202566] == [124.82]


@pytest.mark.parametrize("groupe", [{"201228", "202566"}, {"202206", "202209"}, {"604970", "604972"}])
def test_codes_d_une_meme_ligne(groupe):
    from bpaye.codes import equivalents

    assert all(equivalents(code) == groupe for code in groupe)


def test_heures_de_surveillance_a_la_moitie_du_trente_sixieme(configuration):
    from bpaye.hsa import taux_hsa_annuel

    paye = _paye(configuration, 1, 12)
    paye.surveillance((2025, 11), 4)
    lignes = [ligne for ligne in paye(2025, 11) if ligne.code == 200216]
    taux = taux_hsa_annuel(paye.fonctionnaire, dt.date(2025, 11, 30), rounded=False)
    assert [ligne.valeur for ligne in lignes] == [round(taux / 36 * 0.5 * 4, 2)]  # décret 50-1253, art. 5


def test_heures_de_surveillance_exonerees_comme_les_autres(configuration):
    paye = _paye(configuration, 1, 12)
    avant = paye(2025, 11).hs_brut
    paye.surveillance((2025, 11), 4)
    assert paye(2025, 11).hs_brut > avant


def test_taux_des_heures_de_surveillance_refuse_avant_2008():
    from bpaye.config import BAREME

    with pytest.raises(ValueError, match="MANQUANT"):
        BAREME.load("hs_surveillance")(dt.date(2007, 12, 31))


def _paye_echelon_le_8(configuration):
    """L'agent du conftest, entré le 8 septembre 2019 : ses échelons se prennent un 8."""
    carriere, agent = configuration
    carriere.write_text(carriere.read_text().replace("date       = 2019-09-01", "date       = 2019-09-08"))
    fonc = charge_agent(agent, carriere)
    changement = next(d for d, _ in fonc.echelon.values[1:] if d.day == 8 and d.year >= 2023)
    paye = Paye(fonc)
    paye.generate(startyear=changement.year, startmonth=changement.month, n=6)
    return paye, fonc, changement


def test_rappel_d_un_echelon_pris_en_cours_de_mois_au_centime_de_la_paie(configuration):
    # La paie ne rappelle, le mois du changement, que les 23 jours à compter du 8, chaque
    # traitement tronqué (décompte de juillet 2021 : 2 719,61 − 2 550,75 = 168,86, quand le
    # dû moins le perçu fait 168,85).
    paye, fonc, changement = _paye_echelon_le_8(configuration)
    jours, ancien, nouveau = fonc.changement_d_indice(changement)
    assert jours == 7
    mois = (changement.year, changement.month)
    paiement = (changement.year + (changement.month + 2) // 12, (changement.month + 2) % 12 + 1)
    paye.retard_indice(mois, paiement, indice=ancien, every=False)
    rappel = next(ligne for ligne in paye(*paiement) if ligne.code == CODE_RAPPEL_TRAITEMENT)
    t_ancien = calc_traitement_brut(ancien, changement)
    t_nouveau = calc_traitement_brut(nouveau, changement)
    attendu = round(truncate(t_nouveau * 23 / 30, 2) - truncate(t_ancien * 23 / 30, 2), 2)
    assert round(rappel.valeur, 2) == attendu


def test_rappels_d_une_rubrique_arrondis_depuis_leurs_montants_exacts(configuration):
    # Décembre 2017 : deux neuvièmes d'HSA rappelés ensemble, 2 × 2 742,4055 € = 5 484,81 €
    # sur le bulletin, quand deux lignes arrondies feraient 5 484,82 €.
    bulletin = _paye(configuration, 1, 1)(2025, 1)
    for _ in range(2):
        rappel = Ligne(2742.41, "RAPPEL HSA", code=200205, classe="INDEM", sommable=True)
        rappel.exacte = 2742.4055
        bulletin.append(rappel)
    rappels = [ligne for ligne in bulletin if ligne.code == 200205 and ligne.sommable]
    assert [ligne.valeur for ligne in rappels] == [5484.81]


def test_total_et_frais_exoneres_du_bulletin(configuration):
    bulletin = _paye(configuration, 1, 1)(2025, 1)
    rdt = sum(ligne.valeur for ligne in bulletin if ligne.code == 200039)
    fmd = sum(ligne.valeur for ligne in bulletin if ligne.code == 200041)
    assert bulletin.total(200039) == rdt
    assert bulletin.frais_exoneres == pytest.approx(rdt + fmd)


def test_bulletin_d_un_mois_non_genere_refuse(configuration):
    paye = _paye(configuration, 1, 1)
    assert paye.bulletin(2025, 1) is paye(2025, 1)
    with pytest.raises(ValueError, match="pas de bulletin généré pour 03/2025"):
        paye.bulletin(2025, 3)


def test_rattrapage_d_une_erreur_date_comme_un_rappel(configuration):
    paye = _paye(configuration, 1, 3)
    paye.erreur((2025, 1), (2025, 3), 50.0, 200364)
    (rattrapage,) = [ligne for ligne in paye(2025, 3) if ligne.code == 200364 and ligne.valeur == -50.0]
    assert rattrapage.lib == "[2025-1] RATTRAPAGE Erreur"
