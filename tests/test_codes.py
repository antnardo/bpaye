import tomllib
from pathlib import Path

import pytest

from bpaye.codes import ALL_CODES, CODES_TOML, load_codes


def test_chaque_code_a_six_chiffres_et_une_categorie():
    assert ALL_CODES
    assert all(len(code) == 6 and code.isdigit() for code in ALL_CODES)
    assert {fiche["cat"] for fiche in ALL_CODES.values()} == {"revenu", "retenue", "patronal", "special"}


def test_les_rubriques_courantes_sont_connues():
    assert (ALL_CODES["101000"]["cat"], ALL_CODES["401301"]["cat"]) == ("revenu", "retenue")


def test_load_codes_relit_le_meme_fichier():
    assert load_codes() == ALL_CODES


def _releves():
    """Les codes relevés dans docs/verification : codes.toml et codes_indemnites_corps.toml."""
    racine = Path(__file__).resolve().parents[1] / "docs" / "verification"
    with (racine / "codes.toml").open("rb") as f:
        codes = {c["code"]: c for c in tomllib.load(f)["code"]}
    with (racine / "codes_indemnites_corps.toml").open("rb") as f:
        corps = {c["code"]: c for c in tomllib.load(f)["code"]}
    # Ce relevé garde aussi ses impasses : 201529, périmé en 2010, et un MANQUANT ; seuls
    # les codes que le paquet a retenus se comparent.
    with CODES_TOML.open("rb") as f:
        retenus = {c["code"] for c in tomllib.load(f)["code"]}
    return codes, {code: c for code, c in corps.items() if code in retenus}


def _paquet():
    with CODES_TOML.open("rb") as f:
        return {c["code"]: c for c in tomllib.load(f)["code"]}


def test_chaque_code_du_paquet_a_son_releve():
    codes, corps = _releves()
    # 555010 : contribution de solidarité supprimée en 2018, aucune nomenclature ne la donne.
    assert set(_paquet()) - set(codes) - set(corps) == {"555010"}
    assert set(codes) <= set(_paquet())


@pytest.mark.parametrize("champ", ["ir", "categorie", "imposable", "source", "note"])
def test_code_du_paquet_identique_a_son_releve(champ):
    codes, _ = _releves()
    paquet = _paquet()
    ecarts = {c for c in codes if paquet[c].get(champ) != codes[c].get(champ)}
    assert ecarts == set()


def test_libelle_officiel_identique_au_releve():
    codes, corps = _releves()
    paquet = _paquet()
    assert {
        c for c in codes if paquet[c].get("libelle_officiel", paquet[c]["libelle"]) != codes[c]["libelle"]
    } == set()
    assert {c for c in corps if paquet[c]["libelle_officiel"] != corps[c]["libelle_officiel"]} == set()


def test_indemnites_de_corps_identiques_a_leur_releve():
    _, corps = _releves()
    paquet = _paquet()
    assert {c for c in corps if paquet[c]["ir"] != corps[c]["code_ir"]} == set()
    assert {c for c in corps if paquet[c].get("imposable") != corps[c]["imposable"]} == set()


def test_chaque_code_nomme_est_dans_codes_toml():
    import bpaye.codes as codes

    noms = [nom for nom in codes.__all__ if isinstance(getattr(codes, nom), int)]
    assert noms
    assert [nom for nom in noms if f"{getattr(codes, nom):06d}" not in ALL_CODES] == []
