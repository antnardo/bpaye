import datetime as dt
import tomllib
from pathlib import Path

import pytest

import bpaye
from bpaye.grille import GRILLE_CHSUP, GRILLES, indice_majore

GRILLES_TOML = Path(bpaye.__file__).parent / "grilles.toml"


@pytest.mark.parametrize(
    ("nom", "jour", "echelon", "indice"),
    [
        # Agrégés, classe normale : 8e échelon en 2019, 9e en 2022.
        ("GRILLE_AGCN", dt.date(2019, 10, 1), 8, 700),
        ("GRILLE_AGCN", dt.date(2022, 7, 1), 9, 757),
        # +5 points au 1/1/2024 (décret 2023-519) : IB 1027 → IM 835.
        ("GRILLE_AGCN", dt.date(2024, 1, 1), 11, 835),
        ("GRILLE_CHSUP", dt.date(2023, 9, 1), 4, 800),
        ("GRILLE_CHSUP", dt.date(2025, 9, 1), 5, 835),
        # Tableaux du ministère au 1/1/2024 : certifié CN 1er échelon 395, 11e 678.
        ("GRILLE_CERTCN", dt.date(2024, 1, 1), 1, 395),
        ("GRILLE_CERTCN", dt.date(2024, 1, 1), 11, 678),
    ],
)
def test_indice_majore_compose_depuis_l_indice_brut(nom, jour, echelon, indice):
    assert GRILLES[nom].value(jour).indice(echelon) == indice


def test_agrege_cn_avant_2010_ses_propres_indices():
    # Arrêté du 30 mai 1990 : IB 565, 618, 664 aux 3e à 5e, relevés à 579, 627, 673 en 2010.
    avant, apres = (
        GRILLES["GRILLE_AGCN"].value(dt.date(2009, 1, 1)),
        GRILLES["GRILLE_AGCN"].value(dt.date(2011, 1, 1)),
    )
    assert avant.indices[2:5] == [478, 518, 554]
    assert apres.indices[2:5] == [489, 526, 561]


def test_hors_echelle_trois_chevrons_par_groupe():
    ce = GRILLES["GRILLE_AGCE"].value(dt.date(2024, 1, 1))
    assert ce.indices == [835, 895, 930, 977, 977, 1018, 1072]


def test_chaire_superieure_heb_au_choix_avant_2023_a_l_anciennete_ensuite():
    assert GRILLES["GRILLE_CHSUP"].value(dt.date(2020, 1, 1)).anciennete[7] is None
    assert GRILLES["GRILLE_CHSUP"].value(dt.date(2024, 1, 1)).anciennete[7] == 1.5


def test_chaque_entree_de_grilles_toml_cite_sa_source():
    cfg = tomllib.loads(GRILLES_TOML.read_text(encoding="utf-8"))
    entrees = list(cfg.pop("bareme")) + list(cfg.pop("hors_echelle"))
    for spec in cfg.values():
        entrees += spec["indices"] + spec["durees"]
    assert entrees
    assert all("https://" in e["source"] for e in entrees)


def test_chaque_code_cite_sa_source_dgfip():
    from bpaye.codes import ALL_CODES

    sans_source = {code for code, info in ALL_CODES.items() if "DGFiP" not in info["source"]}
    # 555010, contribution exceptionnelle de solidarité supprimée en 2018 : aucune
    # nomenclature lue ne la donne ; 201228, ancien code de l'ISOE modulable : seulement
    # INGRES et un bulletin de 2026.
    assert sans_source == {"201228", "555010"}


@pytest.mark.parametrize(
    ("date", "attendu"),
    [
        # Barèmes lus sur les fac-similés du JO (décrets 2005-726 et 2006-1283).
        (dt.date(2006, 1, 31), 448),
        (dt.date(2006, 11, 30), 449),
    ],
)
def test_indice_majore_avant_2007_suit_les_baremes_du_jo(date, attendu):
    assert indice_majore(524, date) == attendu


def test_grille_des_chaires_superieures_avant_2010_refusee():
    with pytest.raises(ValueError, match="MANQUANT"):
        GRILLE_CHSUP.value(dt.date(2009, 6, 30))


def test_grilles_toml_est_celui_que_genere_le_script(tmp_path, capsys):
    """grilles.toml se régénère depuis les relevés de docs/verification
    (scripts/genere_grilles.py) : un relevé corrigé sans régénérer, ou l'inverse, se voit."""
    import importlib.util

    racine = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("genere_grilles", racine / "scripts" / "genere_grilles.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sortie = tmp_path / "grilles.toml"
    module.main(racine / "docs" / "verification", sortie)
    capsys.readouterr()
    assert sortie.read_text(encoding="utf-8") == GRILLES_TOML.read_text(encoding="utf-8")
