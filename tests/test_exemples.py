import runpy
import sys
from pathlib import Path

import pytest

EXEMPLES = Path(__file__).resolve().parents[1] / "examples"


def _sortie(capsys, monkeypatch, nom):
    monkeypatch.setattr(sys, "argv", ["bulletins.py", nom])
    runpy.run_path(str(EXEMPLES / "bulletins.py"), run_name="__main__")
    return capsys.readouterr().out


@pytest.mark.parametrize(
    ("nom", "attendus"),
    [
        ("college", ["Indemnité de sujétion REP", "ISOE Part modulable", "Part fonctionnelle (Pacte)"]),
        ("agrege_cpge", ["Indemnité Fonctions particulières CPGE", "Agrégé CN", "dont colles   824.33"]),
        ("carriere_longue", ["PE HC", "ISAE", "ISS directeur d'école", "  2011  brut"]),
    ],
)
def test_exemple_tourne_et_montre_ses_rubriques(capsys, monkeypatch, nom, attendus):
    sortie = _sortie(capsys, monkeypatch, nom)
    for attendu in attendus:
        assert attendu in sortie


def test_carriere_longue_sans_isoe(capsys, monkeypatch):
    assert "ISOE" not in _sortie(capsys, monkeypatch, "carriere_longue")


def test_verifier_lit_controle_et_compare(tmp_path, capsys, monkeypatch, faux_bulletin_pdf):
    faux_bulletin_pdf(tmp_path / "2026_01_BP_janvier.pdf")
    monkeypatch.setattr(sys, "argv", ["verifier.py", str(tmp_path), "2026", str(EXEMPLES / "college")])
    runpy.run_path(str(EXEMPLES / "verifier.py"), run_name="__main__")
    sortie = capsys.readouterr().out
    assert "janvier    net à payer   2350.00 €  lecture complète" in sortie
    assert "rappels : 200205" in sortie
    assert "101000 TB" in sortie  # le traitement du faux bulletin n'est pas celui de l'agente


def test_exporter_ecrit_un_fichier_par_mois_et_les_deux_tableaux(
    tmp_path, capsys, monkeypatch, faux_bulletin_pdf
):
    faux_bulletin_pdf(tmp_path / "2026_01_BP_janvier.pdf")
    sortie = tmp_path / "csv"
    monkeypatch.setattr(sys, "argv", ["exporter.py", str(tmp_path), str(EXEMPLES / "college"), str(sortie)])
    runpy.run_path(str(EXEMPLES / "exporter.py"), run_name="__main__")
    assert "1 mois, de 01/2026 à 01/2026" in capsys.readouterr().out
    assert sorted(p.name for p in sortie.iterdir()) == [
        "2026-01.csv",
        "bulletins_calcules.csv",
        "bulletins_lus.csv",
    ]
