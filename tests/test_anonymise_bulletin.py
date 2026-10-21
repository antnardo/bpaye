import importlib.util
from pathlib import Path

import pdfplumber
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "anonymise_bulletin.py"
NIR = "1 99 12 75 123 456 78"  # fictif
IBAN = "FR76 3000 1007 9412 3456 7890 185"  # fictif


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("anonymise_bulletin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bulletin(tmp_path):
    """Un bulletin fictif qui porte ce qu'un vrai a d'identifiant, aux places des vrais : NIR
    dans la ligne d'identification et au pied, nom et adresse dans la fenêtre d'enveloppe,
    SIRET, IBAN ; et une ligne de paye que personne ne connaît."""
    from reportlab_layout import PDFMaker

    chemin, h = tmp_path / "2026_01_BP_janvier.pdf", 864
    with PDFMaker(str(chemin), pagesize=(595, h)) as doc:
        c = doc.canvas
        c.setFont("Helvetica", 6)
        c.drawString(528.0, h - 50 - 4.4, "SIRET")
        for i, lettre in enumerate("PAY18E-V4.2"):
            c.drawString(578.6, h - 700 - 7 * i, lettre)
        c.setFont("Courier-Bold", 10)
        for x, top, texte in [
            (494.6, 60.0, "19750000000000"),
            (15.2, 105.7, "206"),
            (44.0, 105.7, NIR),
            (214.1, 105.7, "PROF. AGREGE CN"),
            (16.4, 135.4, "101000 TRAITEMENT BRUT"),
            (385.4, 135.4, "3000,00"),
            (16.4, 144.4, "999999 LIGNE QUE PERSONNE NE CONNAIT"),
            (385.4, 144.4, "12,34"),
            (15.2, 641.0, NIR),
            (22.0, 713.0, "53 277,98"),  # montant imposable de l'année
            (118.7, 713.0, "3 648,69"),  # du mois
            (10.7, 819.0, IBAN),
        ]:
            c.drawString(x, h - top - 7.3, texte)
        c.setFont("Helvetica", 9)
        c.drawString(226.0, h - 685 - 6.6, "CAMILLE EXEMPLE")
        c.drawString(226.0, h - 705 - 6.6, "1 RUE IMAGINAIRE")
    return chemin


def _texte(chemin):
    with pdfplumber.open(chemin) as pdf:
        return "".join(c["text"] for p in pdf.pages for c in p.chars)


def test_identifiants_ecartes_et_tout_le_reste_garde(script, bulletin, tmp_path):
    sortie = tmp_path / "anonyme.pdf"
    bilan = script.anonymise(bulletin, sortie)
    assert bilan.restes == ()
    texte = _texte(sortie).replace(" ", "")
    for identifiant in (NIR, IBAN, "CAMILLE", "IMAGINAIRE", "19750000000000", "53277,98"):
        assert identifiant.replace(" ", "") not in texte
    for garde in ("PROF.AGREGECN", "999999LIGNEQUEPERSONNENECONNAIT", "12,34", "3648,69", "SIRET", "PAY18E"):
        assert garde in texte


def test_reste_signale(script, bulletin, tmp_path, monkeypatch):
    # Sans la zone du NIR au pied, le contrôle doit le retrouver et faire échouer le script.
    zones = tuple(z for z in script.ZONES if z.nom != "NIR au pied")
    monkeypatch.setattr(script, "ZONES", zones)
    bilan = script.anonymise(bulletin, tmp_path / "anonyme.pdf")
    assert "un numéro au format d'un NIR" in bilan.restes


def test_original_jamais_ecrase(script, bulletin):
    avant = bulletin.read_bytes()
    with pytest.raises(FileExistsError):
        script.anonymise(bulletin, bulletin)
    assert bulletin.read_bytes() == avant


def test_sortie_par_defaut_a_cote_et_jamais_ecrasee(script, bulletin, capsys):
    assert script.main([str(bulletin)]) == 0
    sortie = bulletin.with_name("2026_01_BP_janvier_anonyme.pdf")
    assert sortie.is_file()
    with pytest.raises(SystemExit):
        script.main([str(bulletin)])  # la sortie existe déjà
    assert "rien n'est écrasé" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("caractere", "zone"),
    [
        ({"fontname": "ABCDEF+Code_Datamatrix", "size": 10, "top": 300, "x0": 100}, "DataMatrix"),
        ({"fontname": "Courier-Bold", "size": 10, "top": 106, "x0": 44}, "NIR et clé"),
        ({"fontname": "Courier-Bold", "size": 10, "top": 106, "x0": 214}, None),
        ({"fontname": "Helvetica", "size": 9, "top": 685, "x0": 226}, "nom et adresse"),
        ({"fontname": "Helvetica", "size": 6, "top": 60, "x0": 21}, None),  # étiquette GESTION
        (
            {"fontname": "Courier-Bold", "size": 10, "top": 60, "x0": 494},
            "affectation, établissement, SIRET, poste",
        ),
        ({"fontname": "Courier-Bold", "size": 10, "top": 300, "x0": 16}, None),  # ligne de paye
    ],
)
def test_zones_de_la_liste_noire(script, caractere, zone):
    assert script.ecarte(caractere) == zone
