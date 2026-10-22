"""Cotisations sociales salariales : CSG, CRDS, contribution solidarité, TPP, IR.

──────────────────────────────────────────────────────────────
ASSIETTE CSG/CRDS
──────────────────────────────────────────────────────────────
Composants inclus : traitement indiciaire, indemnité de résidence, SFT,
    primes et indemnités, avantages en nature.
Composants exclus : remboursement domicile-travail (200039), forfait
    mobilité durable (200041) — frais professionnels exonérés.
TPP (transfert prime-point, code 604970) : Ligne négative dans le bulletin,
    ajoutée algébriquement (Bulletin.tpp < 0 → réduit l’assiette).

    assiette_brute = revenus + tpp − frais_pro
        avec  revenus   = somme des lignes BRUT + INDEM
              tpp       = valeur de 604970 (négatif)
              frais_pro = somme 200039 + 200041

Abattement de 1,75 % sur la part de l'assiette sous 4 plafonds mensuels de la
sécurité sociale (16 020 € en 2026 ; seuil_abattement) :
    assiette_abattue = assiette_brute × 0,9825
Au-delà du seuil, seule la part qui le dépasse échappe à l'abattement (L136-2, I :
« pour leur montant inférieur à quatre fois la valeur du plafond »). Avant le
22/12/2010, l'abattement portait sur tout le montant, et valait 5 % jusqu'en 2004,
3 % de 2005 au 22/12/2011 : taux.toml en donne les sources.

──────────────────────────────────────────────────────────────
SUPPLEMENT HORS ABATTEMENT (depuis mai 2026 – MGEN)
──────────────────────────────────────────────────────────────
La participation patronale MGEN (code 720580 = 37,70 €) est soumise à
CSG/CRDS intégralement, sans bénéficier de l’abattement forfaitaire de
1,75 % (décret PSC : la cotisation patronale de complémentaire santé
obligatoire est un avantage en nature soumis en totalité).

Elle s’ajoute donc APRÈS l’abattement :
    assiette_finale = assiette_abattue + supplement_hors_abat

Les fonctions csg(), csg_nonded() et crds() acceptent ce supplément via le
paramètre supplement_hors_abat (défaut 0,0 pour tous les mois antérieurs).

Formule complète (depuis mai 2026, hors HSI), sur un exemple fictif :
    assiette_brute  = 7 000,00 €
    assiette_abattu = 7 000,00 × 0,9825 = 6 877,50 €
    assiette_finale = 6 877,50 + 37,70  = 6 915,20 €

──────────────────────────────────────────────────────────────
TAUX ET ARRONDI
──────────────────────────────────────────────────────────────
    assiette_abattue au centime : tronquée jusqu'en janvier 2026, arrondie depuis
    (changement de logiciel de paie) ; les heures exonérées abattues à part
    CSG déductible  = round(6,8 % × assiette_abattue, 2)
                    + round(6,8 % × supplement_hors_abat, 2)  ← deux arrondis
    CSG non ded.    = round(2,4 % × assiette_finale, 2)
    CRDS            = round(0,5 % × assiette_finale, 2)

La part déductible se calcule à part sur le salaire abattu et sur la part
employeur MGEN, chacune arrondie ; la part non déductible, sur leur somme.

Sur les heures supplémentaires exonérées d'impôt (charges_impots.ExonerationHS), la CSG
n'est pas déductible : la part à 6,8 % assise sur elles (abattues) passe de la CSG
déductible à la CSG non déductible, en un arrondi à part (csg_basculee). Le total ne
change pas. D'où l'« anomalie » des mois de janvier et février, tant que le plafond
annuel d'exonération n'est pas atteint.
Cette règle retrouve tous les bulletins de 2020 à 2026 sans rappel, là où une
troncature manquait un centime un mois sur deux et un arrondi unique ratait
mai et juin 2026 : voir docs/csg.md et scripts/verifie_csg.py.

──────────────────────────────────────────────────────────────
DÉFISCALISATION HS
──────────────────────────────────────────────────────────────
Plafond brut annuel = 5 000 / (1 − 0,9825 × 0,068) = 5 357,96 → 5 358 €
    (porté à 8 037 € pour les heures faites depuis le 1/1/2022, loi 2022-1157, art. 4)

Montant net défiscalisé (code 011200) :
    S = (N + C_nd + R − M) / 0,93319
    où N = net avant IR, C_nd = CSG non ded., R = CRDS, M = montant imposable
"""

import datetime as dt
import math

from bpaye.classes import Ligne, Taux
from bpaye.codes import CONTRIBUTION_SOLIDARITE, TPP
from bpaye.config import BAREME, Bareme
from bpaye.point import calc_traitement_brut
from bpaye.utils import truncate

__all__ = [
    "NOUVEAU_LOGICIEL_PAIE",
    "contribution_solidarite",
    "crds",
    "csg",
    "csg_basculee",
    "csg_nonded",
    "ir",
    "net_colles_seules",
    "seuil_abattement",
    "transfertprimepoint",
]


# Le logiciel de paie a changé en février 2026 (bulletins PAY18E V2.3, puis V4.0 et V4.2) :
# l'ancien tronquait les assiettes abattues au centime, le nouveau les arrondit. Chaque
# règle retrouve les bulletins de son logiciel ; l'autre manque un centime çà et là
# (docs/csg.md).
NOUVEAU_LOGICIEL_PAIE = dt.date(2026, 2, 1)


def _au_centime(montant: float, date: dt.date) -> float:
    if date >= NOUVEAU_LOGICIEL_PAIE:
        return round(montant, 2)
    return math.floor(montant * 100 + 1e-9) / 100


def seuil_abattement(date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le montant mensuel sous lequel l'assiette est abattue : 4 plafonds mensuels de la
    sécurité sociale du mois depuis le 22/12/2010, aucun seuil avant (math.inf)."""
    plafonds = bareme.au("csg.abattement_plafonds", date)
    if math.isinf(plafonds):
        return math.inf
    return plafonds * bareme.au("pmss", date)


def _abattu(
    montant: float,
    assiette: float,
    date: dt.date,
    abattement: str = "csg.abattement_taux",
    bareme: Bareme = BAREME,
) -> float:
    """Un morceau d'assiette, abattu sur sa part sous le seuil.

    Au-delà du seuil, la part abattue de chaque morceau est sa part du seuil, au prorata
    de l'assiette : aucun bulletin ne montre comment la paie répartit le seuil entre le
    salaire et les heures exonérées. Sans heures exonérées, c'est la règle du texte."""
    if montant == 0:
        return 0.0
    seuil = seuil_abattement(date, bareme)
    if assiette <= seuil:
        return _au_centime(bareme.load(abattement).taux(montant, date), date)
    sous_seuil = montant * seuil / assiette
    return _au_centime(montant - sous_seuil + bareme.load(abattement).taux(sous_seuil, date), date)


def _assiettes(
    assiette: float,
    date: dt.date,
    hs_exonerees: float = 0.0,
    abattement: str = "csg.abattement_taux",
    bareme: Bareme = BAREME,
) -> tuple[float, float]:
    """Le salaire abattu hors heures exonérées, puis ces heures abattues : la paie les abat
    séparément, chacun ramené au centime."""
    hs = max(hs_exonerees, 0.0)
    return (
        _abattu(assiette - hs, assiette, date, abattement, bareme),
        _abattu(hs, assiette, date, abattement, bareme),
    )


def _appliquer_abattement_csg(assiette: float, date: dt.date, bareme: Bareme = BAREME) -> float:
    """L'assiette abattue, au centime comme sur les bulletins (_au_centime)."""
    return _abattu(assiette, assiette, date, bareme=bareme)


def csg_basculee(assiette: float, date: dt.date, hs_exonerees: float = 0.0, bareme: Bareme = BAREME) -> float:
    """La CSG déductible des heures supplémentaires exonérées d'impôt, que la paie passe en
    non déductible (voir en tête)."""
    heures = _assiettes(assiette, date, hs_exonerees, bareme=bareme)[1]
    return round(bareme.load("csg.deductible").taux(heures, date), 2)


def csg_nonded(
    assiette: float,
    date: dt.date,
    supplement_hors_abat: float = 0.0,
    hs_exonerees: float = 0.0,
    bareme: Bareme = BAREME,
) -> Ligne:
    salaire, heures = _assiettes(assiette, date, hs_exonerees, bareme=bareme)
    base = salaire + heures + supplement_hors_abat
    taux = bareme.load("csg.non_deductible")
    val = -(round(taux.taux(base, date), 2) + csg_basculee(assiette, date, hs_exonerees, bareme))
    return Ligne(val, "CSG non déductible", code=401201, imposable=True, classe="CHARGE")


def csg(
    assiette: float,
    date: dt.date,
    supplement_hors_abat: float = 0.0,
    hs_exonerees: float = 0.0,
    bareme: Bareme = BAREME,
) -> Ligne:
    # Deux arrondis : sur le salaire abattu, puis sur la part employeur MGEN (voir en tête).
    # Les heures exonérées en sortent : leur CSG est non déductible.
    salaire, _ = _assiettes(assiette, date, hs_exonerees, bareme=bareme)
    taux = bareme.load("csg.deductible")
    val = -(round(taux.taux(salaire, date), 2) + round(taux.taux(supplement_hors_abat, date), 2))
    return Ligne(val, "CSG déductible", code=401301, classe="CHARGE")


def crds(
    assiette: float,
    date: dt.date,
    supplement_hors_abat: float = 0.0,
    hs_exonerees: float = 0.0,
    bareme: Bareme = BAREME,
) -> Ligne:
    salaire, heures = _assiettes(assiette, date, hs_exonerees, "crds.abattement_taux", bareme)
    val = -round(bareme.load("crds.taux").taux(salaire + heures + supplement_hors_abat, date), 2)
    return Ligne(val, "CRDS", code=401501, imposable=True, classe="CHARGE")


def net_colles_seules(brut: float, date: dt.date, bareme: Bareme = BAREME) -> float:
    """Le net d'un bulletin qui ne paie que des colles : celui d'un autre établissement,
    avec son propre payeur.

    Ce que montrent ces bulletins (janvier à avril 2026) : la CSG entière passe en non
    déductible (401201), les heures étant exonérées d'impôt, mais se calcule en deux
    parts arrondies chacune, 6,8 % et 2,4 % de l'assiette abattue ; la CRDS ; ni RAFP, ni
    réduction de cotisations, ni impôt. Un arrondi unique à 9,2 % manque d'un centime un
    mois sur deux.
    """
    base = _appliquer_abattement_csg(brut, date, bareme)
    deductible, non_deductible = bareme.load("csg.deductible"), bareme.load("csg.non_deductible")
    csg_entiere = round(deductible.taux(base, date), 2) + round(non_deductible.taux(base, date), 2)
    return round(brut - csg_entiere + crds(brut, date, bareme=bareme).valeur, 2)


def contribution_solidarite(
    assiette: float, date: dt.date, net_mensuel: float, bareme: Bareme = BAREME
) -> Ligne:
    """Contribution exceptionnelle de solidarité (555010), jusqu'en 2017. Code du travail,
    L5423-27 et L5423-32 : 1 % de la rémunération nette totale hors remboursements de frais
    (``assiette``), dans la limite du plafond de l'assurance chômage (4 PMSS, taux.toml) ;
    exonérée quand la rémunération mensuelle nette (traitement et indemnité de résidence,
    nets de la pension et de la RAFP : ``net_mensuel``) est sous le traitement brut de
    l'indice de référence (taux.toml, contrisoli_seuil). Tronquée au centime : aucun texte
    lu ne fixe l'arrondi (MANQUANT) ; relevé sur les bulletins de 2017, où 1 % de
    2 999,74 € donne 29,99 €."""
    taux = bareme.load("contrisoli")
    if taux(date) == 0.0:
        return Ligne(0.0, "Contribution Solidarité", code=CONTRIBUTION_SOLIDARITE, classe="CHARGE")
    seuil = calc_traitement_brut(bareme.get("contrisoli_seuil.indice_majore"), date, bareme)
    plafond = bareme.get("contrisoli_plafond.pmss") * bareme.au("pmss", date)
    montant = 0.0 if net_mensuel < seuil else truncate(taux.taux(min(assiette, plafond), date), 2)
    return Ligne(-montant, "Contribution Solidarité", code=CONTRIBUTION_SOLIDARITE, classe="CHARGE")


def transfertprimepoint(date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    montant = bareme.au("transfertpp", date)
    return Ligne(-round(montant, 2), "Transfert Prime Point", code=TPP, classe="CHARGE")


def ir(assiette: float, date: dt.date, taux_pas: Taux) -> Ligne:
    """Le prélèvement à la source au taux personnel de l'agent (agent.toml)."""
    return Ligne(
        -round(taux_pas.taux(assiette, date), 2),
        f"Impot Revenu {100 * taux_pas.value(date):.1f}%",
        code=558000,
        classe="IMPOT",
        imposable=True,
    )
