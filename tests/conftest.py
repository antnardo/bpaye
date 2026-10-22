import pytest

CARRIERE = """
[depart]
nom        = "Agent Fictif"
grille     = "GRILLE_AGCN"
echelon    = 3
anciennete = 0.0
date       = 2019-09-01

[[detachements]]
date    = 2019-09-01
detache = false

[[rentrees]]
year     = 2024
annee    = 2
effectif = 40
hsa_vs   = 6

[[rentrees]]
year         = 2025
annee        = 2
effectif     = 40
hsa_vs       = 6
colles       = { 161 = 4.0 }
colles_debut = 2025-09-22
colles_fin   = 2026-04-10
"""

AGENT = """
siret = "19750000000000"

[ir]
type = "Taux"
values = [{ date = 2019-01-01, valeur = 0.05 }]

[[enfants]]
date   = 2019-01-01
nombre = 0

[[residence]]
date = 2019-09-01
zone = 1

[[fmd]]
date   = 2019-01-01
niveau = 1

[[transport]]
date              = 2019-09-01
abonnement_annuel = 1000

[ic_csg]
type   = "Fixe"
unite  = "mensuel"
values = [{ date = 2018-01-01, valeur = 57.55 }]
"""


@pytest.fixture
def configuration(tmp_path):
    carriere, agent = tmp_path / "carriere.toml", tmp_path / "agent.toml"
    carriere.write_text(CARRIERE, encoding="utf-8")
    agent.write_text(AGENT, encoding="utf-8")
    return carriere, agent


LIGNES_FAUX_BULLETIN = [
    ("101000", "TRAITEMENT BRUT", "3000,00"),
    ("200205", "HEURES ANNEES ENSEIGNT", "300,00"),
    ("200205", "HEURES ANNEES ENSEIGNT    RAPPEL ANNEE C", "50,00"),
    ("401301", "C.S.G. DEDUCTIBLE", "1000,00", 457.4),
    ("404001", "COT PAT MALADIE DEPLAFON", "2000,00", 517.0),
]


def ecrit_pdf(chemin, morceaux, hauteur=842.0, version=("PAY18E-V4.2-29", 570.0, 300.0)):
    """Un PDF d'une page, du texte seul, placé comme sur un bulletin PAY18E.

    ``morceaux`` : des (police, corps, x, ligne, texte), où ``ligne`` est la ligne de base
    en points depuis le haut de la page. ``version`` : (texte, x, ligne de la première
    lettre), écrit à la verticale en Helvetica 6, une lettre tous les 7 points."""
    from reportlab_layout import PDFMaker

    with PDFMaker(str(chemin), pagesize=(595.0, hauteur)) as doc:
        c = doc.canvas
        texte, x, ligne = version
        c.setFont("Helvetica", 6)
        for i, lettre in enumerate(texte):
            c.drawString(x, hauteur - ligne - 7 * i, lettre)
        for police, corps, x, ligne, morceau in morceaux:
            c.setFont(police, corps)
            c.drawString(x, hauteur - ligne, morceau)


def _ecrit_faux_bulletin(chemin, lignes=LIGNES_FAUX_BULLETIN, totaux="3350,00", entete=None):
    """Un bulletin PAY18E fictif, écrit comme les vrais : Courier-Bold 9 pt, code et libellé
    à gauche, « € » puis le montant à droite, version à la verticale, pied en bas.

    ``entete`` : le mois (« AOUT 2026 »), puis les colonnes de la ligne d'identification
    (grade, enfants, échelon, indice, temps partiel) et le taux du prélèvement à la source,
    aux abscisses des vrais bulletins. En Courier-Bold 9 pt, la ligne de base est 6,6 pt
    sous le haut que donne pdfplumber à ce PDF (``top``)."""
    morceaux = []
    if entete:
        morceaux.append(("Courier-Bold", 9, 317.8, 28.2, entete["mois"]))
        for x, cle in [
            (214.1, "grade"),
            (347.6, "enfants"),
            (380.3, "echelon"),
            (415.4, "indice"),
            (525.0, "temps_partiel"),
        ]:
            morceaux.append(("Courier-Bold", 9, x, 112.3, entete.get(cle, "")))
        morceaux += [("Courier-Bold", 9, 15.2, 112.3, "206"), ("Courier-Bold", 9, 191.2, 112.3, "00")]
        if "taux_pas" in entete:
            morceaux.append(("Courier-Bold", 9, 53.0, 520.0, f"(TAUX PERSONNALISE {entete['taux_pas']}%)"))
    # Une ligne peut donner l'abscisse de son montant : 385,4 à payer (par défaut),
    # 457,4 à déduire, 517 pour information.
    sommes = {457.4: 0.0, 517.0: 0.0}
    for rang, (code, libelle, montant, *x) in enumerate(lignes):
        x_montant = x[0] if x else 385.4
        if x_montant in sommes:
            sommes[x_montant] += float(montant.replace(",", "."))
        ligne = 142.0 + 9 * rang
        morceaux += [
            ("Courier-Bold", 9, 16.4, ligne, code),
            ("Courier-Bold", 9, 53.0, ligne, libelle),
            ("Helvetica", 8, 361.4, ligne, "€"),
            ("Courier-Bold", 9, x_montant, ligne, montant),
        ]
    for x, ligne, texte in [
        (380.0, 630.0, totaux),
        (450.0, 630.0, f"{sommes[457.4]:.2f}".replace(".", ",")),
        (520.0, 630.0, f"{sommes[517.0]:.2f}".replace(".", ",")),
        (420.0, 648.0, "2350,00"),  # net à payer : 3 350 − 1 000 de retenues
        (120.0, 716.0, "2600,00"),  # montant imposable du mois
    ]:
        morceaux.append(("Courier-Bold", 9, x, ligne, texte))
    ecrit_pdf(chemin, morceaux)


@pytest.fixture(name="ecrit_pdf")
def ecrit_pdf_fixture():
    """Écrit un PDF de morceaux de texte placés (``ecrit_pdf``) : pour un faux bulletin sur
    mesure."""
    return ecrit_pdf


@pytest.fixture
def faux_bulletin_pdf():
    """Écrit un bulletin PAY18E fictif au chemin donné (il faut reportlab_layout)."""
    return _ecrit_faux_bulletin


# Un agrégé de classe normale au 4e échelon (IM 547) en août 2026, zone 1, professeur
# principal sous l'ancien code de l'ISOE modulable. Montants fictifs mais cohérents :
# 547 × 59,0734 / 12 = 2 692,76 € ; 3 % = 80,78 €.
LIGNES_AGREGE = [
    ("101000", "TRAITEMENT BRUT", "2692,76"),
    ("102000", "INDEMNITE DE RESIDENCE", "80,78"),
    ("200364", "ISOE PART FIXE", "212,50"),
    ("201228", "I.S.O.E. PART MODULABLE", "124,82"),
]
ENTETE_AGREGE = {
    "mois": "AOUT 2026",
    "grade": "PROF. AGREGE CN",
    "enfants": "00",
    "echelon": "04",
    "indice": "0547",
    "taux_pas": "6,20",
}


@pytest.fixture
def bulletin_agrege(tmp_path):
    """Écrit le faux bulletin de cet agrégé ; ``entete`` en change des champs (echelon="03")."""

    def ecrit(**entete):
        chemin = tmp_path / "2026_08_BP_aout.pdf"
        _ecrit_faux_bulletin(chemin, LIGNES_AGREGE, "3110,86", {**ENTETE_AGREGE, **entete})
        return chemin

    return ecrit
