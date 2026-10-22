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
def bulletin(tmp_path, ecrit_pdf):
    """Un bulletin fictif qui porte ce qu'un vrai a d'identifiant, aux places des vrais : NIR
    dans la ligne d'identification et au pied, nom et adresse dans la fenêtre d'enveloppe,
    SIRET, IBAN ; et une ligne de paye que personne ne connaît. Lignes de base, depuis le
    haut d'une page de 864 points comme celles de l'ENSAP."""
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    donnees = [
        (494.6, 67.3, "19750000000000"),
        (15.2, 113.0, "206"),
        (44.0, 113.0, NIR),
        (214.1, 113.0, "PROF. AGREGE CN"),
        (16.4, 142.7, "101000 TRAITEMENT BRUT"),
        (385.4, 142.7, "3000,00"),
        (16.4, 151.7, "999999 LIGNE QUE PERSONNE NE CONNAIT"),
        (385.4, 151.7, "12,34"),
        (15.2, 648.3, NIR),
        (22.0, 720.3, "53 277,98"),  # montant imposable de l'année
        (118.7, 720.3, "3 648,69"),  # du mois
        (10.7, 826.3, IBAN),
    ]
    morceaux = [("Helvetica", 6, 528.0, 54.4, "SIRET")]
    morceaux += [("Courier-Bold", 10, x, ligne, texte) for x, ligne, texte in donnees]
    morceaux += [
        ("Helvetica", 9, 226.0, 691.6, "CAMILLE EXEMPLE"),
        ("Helvetica", 9, 226.0, 711.6, "1 RUE IMAGINAIRE"),
    ]
    ecrit_pdf(chemin, morceaux, hauteur=864.0, version=("PAY18E-V4.2", 578.6, 700.0))
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


def _glyphe(police, corps, ligne, x, hauteur=864.0):
    """Un glyphe tel que le décrit reportlab_layout : ``ligne``, sa ligne de base depuis le
    haut de la page."""
    from reportlab_layout import PdfElement

    y = hauteur - ligne
    return PdfElement("text", (x, y - 2, x + 6, y + 7), 0, origin=(x, y), text="X", font=police, size=corps)


@pytest.mark.parametrize(
    ("element", "zone"),
    [
        (_glyphe("ABCDEF+Code_Datamatrix", 10, 300, 100), "DataMatrix"),
        (_glyphe("Courier-Bold", 10, 114, 44), "NIR et clé"),
        (_glyphe("Courier-Bold", 10, 114, 214), None),  # grade
        (_glyphe("Helvetica", 9, 692, 226), "nom et adresse"),
        (_glyphe("Helvetica", 6, 65, 21), None),  # étiquette GESTION
        (_glyphe("Courier-Bold", 10, 68, 494), "affectation, établissement, SIRET, poste"),
        (_glyphe("Courier-Bold", 10, 721, 22), "cumuls de l'année (base SS, montant imposable)"),
        (_glyphe("Courier-Bold", 10, 721, 125), None),  # montant imposable du mois
        (_glyphe("Courier-Bold", 9, 300, 16), None),  # ligne de paye
    ],
)
def test_zones_de_la_liste_noire(script, element, zone):
    assert script.raison(element, 864.0) == zone
