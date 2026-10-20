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


def _ecrit_faux_bulletin(chemin, lignes=LIGNES_FAUX_BULLETIN, totaux="3350,00", entete=None):
    """Un bulletin PAY18E fictif, écrit comme les vrais : Courier-Bold 9 pt, code et libellé
    à gauche, « € » puis le montant à droite, version à la verticale, pied en bas.

    ``entete`` : le mois (« AOUT 2026 »), puis les colonnes de la ligne d'identification
    (grade, enfants, échelon, indice, temps partiel) et le taux du prélèvement à la source,
    aux abscisses des vrais bulletins. Une ordonnée de reportlab (depuis le bas) vaut
    842 − haut du caractère − 6,6 en Courier-Bold 9 pt."""
    from reportlab_layout import PDFMaker

    hauteur = 842
    with PDFMaker(str(chemin)) as doc:
        c = doc.canvas
        c.setFont("Helvetica", 6)
        for i, lettre in enumerate("PAY18E-V4.2-29"):
            c.drawString(570, hauteur - 300 - 7 * i, lettre)
        c.setFont("Courier-Bold", 9)
        if entete:
            c.drawString(317.8, hauteur - 21.6 - 6.6, entete["mois"])
            identification = [
                (15.2, "206"),
                (191.2, "00"),
                (214.1, entete.get("grade", "")),
                (347.6, entete.get("enfants", "")),
                (380.3, entete.get("echelon", "")),
                (415.4, entete.get("indice", "")),
                (525.0, entete.get("temps_partiel", "")),
            ]
            for x, texte in identification:
                c.drawString(x, hauteur - 105.7 - 6.6, texte)
            if "taux_pas" in entete:
                c.drawString(53.0, hauteur - 520, f"(TAUX PERSONNALISE {entete['taux_pas']}%)")
        # Une ligne peut donner l'abscisse de son montant : 385,4 à payer (par défaut),
        # 457,4 à déduire, 517 pour information.
        sommes = {457.4: 0.0, 517.0: 0.0}
        for rang, (code, libelle, montant, *x) in enumerate(lignes):
            x_montant = x[0] if x else 385.4
            if x_montant in sommes:
                sommes[x_montant] += float(montant.replace(",", "."))
            y = hauteur - 142 - 9 * rang
            c.setFont("Courier-Bold", 9)
            c.drawString(16.4, y, code)
            c.drawString(53.0, y, libelle)
            c.setFont("Helvetica", 8)
            c.drawString(361.4, y, "€")
            c.setFont("Courier-Bold", 9)
            c.drawString(x_montant, y, montant)
        c.setFont("Courier-Bold", 9)
        for x, y, texte in [
            (380, 212, totaux),
            (450, 212, f"{sommes[457.4]:.2f}".replace(".", ",")),
            (520, 212, f"{sommes[517.0]:.2f}".replace(".", ",")),
            (420, 194, "2350,00"),  # net à payer : 3 350 − 1 000 de retenues
            (120, 126, "2600,00"),
        ]:
            c.drawString(x, y, texte)


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
