import datetime as dt
import tomllib
from pathlib import Path

import pytest

from bpaye.academies import ACADEMIE_PAR_DEFAUT, ACADEMIES, Retard, lit_retard, remplace, retards_academie

RELEVE = Path(__file__).resolve().parents[1] / "docs" / "verification" / "academies.toml"


def _cles_relevees():
    with RELEVE.open("rb") as f:
        releve = tomllib.load(f)
    cles = {a["cle"] for a in releve["academies"]} | {a["cle"] for a in releve["anciennes"]}
    return cles | {releve["defense"]["cle"]}


def test_academies_du_paquet_sont_celles_du_releve():
    assert set(ACADEMIES) - {ACADEMIE_PAR_DEFAUT} == _cles_relevees()


def test_retards_par_defaut_ceux_releves_a_paris():
    assert retards_academie() == retards_academie("paris")
    assert {r.code: (r.du, r.paye) for r in retards_academie().values()} == {
        200205: (10, 11),
        200576: (10, 11),
        200597: (9, 10),
    }


def test_academie_inconnue_refusee():
    with pytest.raises(ValueError, match="académie inconnue"):
        retards_academie("atlantide")


@pytest.mark.parametrize(
    ("entree", "message"),
    [
        ({"code": 999123, "du": 1, "paye": 2}, "inconnu"),
        ({"code": 200041, "du": 13, "paye": 2}, "de 1 à 12"),
        ({"code": 200041, "du": 1, "paye": 1}, "distincts"),
    ],
)
def test_retard_mal_forme_refuse(entree, message):
    with pytest.raises(ValueError, match=message):
        lit_retard(entree, "test")


def test_retard_de_decembre_paye_en_janvier():
    retard = Retard(200041, 12, 1, depuis=dt.date(2024, 1, 1))
    assert retard.decalage == 1
    assert retard.concerne(dt.date(2024, 12, 31))
    assert not retard.concerne(dt.date(2023, 12, 31))


def test_remplace_garde_deux_mois_d_une_meme_rubrique():
    octobre, novembre = Retard(200205, 10, 12), Retard(200205, 11, 12)
    assert remplace({}, [octobre, novembre]) == {(200205, 10): octobre, (200205, 11): novembre}


def test_remplace_tous_les_retards_d_une_rubrique():
    herites = retards_academie()  # dont les HSA d'octobre, payées en novembre
    propre = Retard(200205, 11, 12)
    retards = remplace(herites, [propre])
    assert [r for r in retards.values() if r.code == 200205] == [propre]
    assert (200597, 9) in retards  # les autres rubriques restent


def test_defense_hsa_d_octobre_et_novembre_en_decembre_sans_retard_d_ifp():
    retards = retards_academie("defense")
    assert {(r.code, r.du, r.paye) for r in retards.values()} == {
        (200205, 10, 12),
        (200205, 11, 12),
        (200576, 10, 12),
        (200576, 11, 12),
    }
