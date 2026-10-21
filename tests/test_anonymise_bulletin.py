import importlib.util
from pathlib import Path

import pdfplumber
import pytest

from bpaye.pdf import extract_bulletin

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "anonymise_bulletin.py"
NIR = "1 99 12 75 123 456"  # fictif


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("anonymise_bulletin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bulletin_identifie(tmp_path):
    """Un bulletin fictif qui porte ce qu'un vrai a d'identifiant : NIR dans la ligne
    d'identification et au pied, nom et adresse dans la fenêtre d'enveloppe, SIRET."""
    from reportlab_layout import PDFMaker

    chemin, h = tmp_path / "2026_01_BP_janvier.pdf", 842
    with PDFMaker(str(chemin)) as doc:
        c = doc.canvas
        c.setFont("Helvetica", 6)
        for i, lettre in enumerate("PAY18E-V4.2-29"):
            c.drawString(570, h - 300 - 7 * i, lettre)
        c.setFont("Courier-Bold", 9)
        for x, top, texte in [
            (528.0, 60.0, "19750000000000"),
            (15.2, 105.7, "206"),
            (44.0, 105.7, NIR),
            (214.1, 105.7, "PROF. AGREGE CN"),
            (16.4, 135.4, "101000"),
            (53.0, 135.4, "TRAITEMENT BRUT"),
            (385.4, 135.4, "3000,00"),
            (380.0, 623.4, "3000,00"),
            (420.0, 641.4, "3000,00"),
            (15.2, 641.0, NIR),
            (226.0, 685.0, "CAMILLE EXEMPLE"),
            (226.0, 705.0, "1 RUE FICTIVE 75000 PARIS"),
            (120.0, 709.4, "3000,00"),
        ]:
            c.drawString(x, h - top - 6.6, texte)
        c.setFont("Helvetica", 8)
        c.drawString(361.4, h - 135.4 - 6.6, "€")
    return chemin


def _texte(chemin):
    with pdfplumber.open(chemin) as pdf:
        return "".join(c["text"] for p in pdf.pages for c in p.chars)


def test_anonymisation_garde_la_lecture_et_retire_les_identifiants(script, bulletin_identifie, tmp_path):
    sortie = tmp_path / "anonyme.pdf"
    bilan = script.anonymise(bulletin_identifie, sortie)
    assert (bilan.nir_present, bilan.differences) == (False, ())
    assert dict(extract_bulletin(sortie)) == dict(extract_bulletin(bulletin_identifie))
    texte = _texte(sortie)
    for identifiant in (NIR.replace(" ", ""), "CAMILLE", "FICTIVE", "19750000000000"):
        assert identifiant not in texte.replace(" ", "")
    assert "PROF. AGREGE CN" in texte


def test_siret_fictif_ecrit_sur_demande(script, bulletin_identifie, tmp_path):
    from bpaye.pdf import extract_sirets

    sortie = tmp_path / "anonyme.pdf"
    script.anonymise(bulletin_identifie, sortie, siret="12345678901234")
    assert extract_sirets(sortie) == {"12345678901234"}


@pytest.mark.parametrize(
    ("top", "x", "garde"),
    [
        (106.0, 44.0, False),  # NIR
        (106.0, 214.0, True),  # grade
        (641.0, 15.2, False),  # NIR répété au pied
        (685.0, 226.0, False),  # nom, fenêtre d'enveloppe
        (713.0, 22.0, False),  # montant imposable de l'année
        (713.0, 125.0, True),  # montant imposable du mois
        (300.0, 16.4, True),  # ligne de paye
        (810.0, 76.8, False),  # compte bancaire
    ],
)
def test_zones_gardees(script, top, x, garde):
    caractere = {"fontname": "Courier-Bold", "top": top, "x0": x, "upright": True}
    assert script.garde(caractere) is garde


def test_datamatrix_jamais_garde(script):
    caractere = {"fontname": "ABCDEF+Code_Datamatrix", "top": 300.0, "x0": 100.0, "upright": True}
    assert script.garde(caractere) is False
