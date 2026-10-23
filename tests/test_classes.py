import datetime as dt

import pytest

from bpaye.classes import Ligne, Temporal
from bpaye.config import BAREME


@pytest.mark.parametrize(
    ("section", "jour"),
    [
        ("pc", dt.date(2008, 6, 30)),  # taux d'avant 2011 non relu
        ("transport.plafond", dt.date(2015, 3, 31)),  # plafond d'avant août 2016 non relu
        ("rafp", dt.date(2003, 1, 31)),  # régime créé au 1/1/2005
    ],
)
def test_bareme_avant_sa_premiere_valeur_refuse_de_deviner(section, jour):
    with pytest.raises(ValueError, match="MANQUANT"):
        BAREME.load(section)(jour)


def test_donnee_d_agent_avant_sa_premiere_valeur_prend_celle_ci():
    echelon: Temporal[int] = Temporal()
    echelon.append(dt.date(2010, 9, 1), 3)
    assert echelon(dt.date(2010, 1, 31)) == 3


def test_message_sans_valeur_precedente_nomme_la_date():
    echelon: Temporal[int] = Temporal()
    echelon.append(dt.date(2010, 9, 1), 3)
    with pytest.raises(ValueError, match="2010-09-30"):
        echelon.value_prec(dt.date(2010, 9, 30))


def test_valeur_repetee_se_retrouve_a_sa_derniere_date():
    echelon: Temporal[int] = Temporal()
    for jour, valeur in ((dt.date(2010, 9, 1), 2), (dt.date(2012, 9, 1), 3), (dt.date(2015, 9, 1), 2)):
        echelon.append(jour, valeur)
    assert echelon.value_toindice(2) == 2
    echelon.update_date_fromvalue(2, dt.date(2016, 9, 1))
    assert echelon.values[-1] == (dt.date(2016, 9, 1), 2)


class TestTemporalAuDeclareAu:
    def test_au_le_defaut_si_rien_n_est_declare(self):
        assert Temporal().au(dt.date(2025, 1, 1), 1.0) == 1.0

    def test_au_la_premiere_valeur_avant_sa_date(self):
        quotite = Temporal()
        quotite.append(dt.date(2025, 9, 1), 0.8)
        assert quotite.au(dt.date(2025, 1, 1), 1.0) == 0.8

    def test_declare_au_le_defaut_avant_la_premiere_date(self):
        academie = Temporal()
        academie.append(dt.date(2019, 9, 1), "paris")
        assert academie.declare_au(dt.date(2019, 8, 31), "defaut") == "defaut"
        assert academie.declare_au(dt.date(2019, 9, 1), "defaut") == "paris"


def test_ligne_avec_change_la_copie_seulement():
    ligne = Ligne(100.0, "HSA", code=200205, classe="INDEM")
    ligne.valeur_reel = 99.0
    copie = ligne.avec(valeur=-100.0, sommable=True)
    assert (copie.valeur, copie.sommable, copie.valeur_reel, copie.lib) == (-100.0, True, 99.0, "HSA")
    assert (ligne.valeur, ligne.sommable) == (100.0, False)


def test_ligne_avec_un_attribut_inconnu_echoue():
    with pytest.raises(AttributeError, match="montant"):
        Ligne(1.0).avec(montant=2.0)
