"""Indemnités à montant fixe : IFP des CPGE, ISOE, transport, PSC, FMD, équipement informatique.

- IFP (200597) : indemnité de fonctions particulières des enseignants de CPGE, décret
  99-886 du 19 octobre 1999 ; taux annuel fixé par arrêté, indexé sur le point.
- ISOE part fixe (200364) : décret 93-55 du 15 janvier 1993 ; 2 550 € par an depuis
  septembre 2023 (arrêté du 15/1/1993, art. 1). Elle reste indexée sur le point (décret
  93-55, art. 4) : une hausse du point demandera un montant nouveau dans taux.toml.
- Remboursement domicile-travail (200039) : une part de l'abonnement, plafonnée
  (taux.toml) ; les abonnements RATP se calculent sur le tarif annuel.
- FMD (200041) et prime d'équipement informatique (202321) : versements annuels.

- Part fonctionnelle de l'ISOE (202475) ou de l'ISAE (202476), le « Pacte » : 1 250 € par
  part (arrêté du 15/1/1993, art. 2-1 ; arrêté du 30/8/2013, art. 1-1), versée par
  neuvième (décret 93-55, art. 6 ; décret 2013-790, art. 3). Aucun texte lu ne dit sur
  quels mois tombent les neuf neuvièmes : bpaye suppose octobre à juin (MOIS_PACTE).

À temps partiel, ces indemnités suivent la fraction de rémunération (code général de la
fonction publique, L612-5 : « primes et indemnités de toute nature ») : aucun de leurs
décrets n'en dispose autrement, ce qui reste « a priori » (temps_partiel.py). Exceptions
lues : la prime d'équipement informatique est versée à taux plein (décret 2020-1524,
art. 1). Le remboursement domicile-travail, la PSC, le FMD et la part fonctionnelle n'ont
pas de règle de temps partiel lue : ils sont versés tels quels.

Les montants sont dans taux.toml ; ce module les met en lignes de bulletin.
"""

import datetime as dt
from typing import Any

import bpaye.config as config
from bpaye.classes import Ligne
from bpaye.codes import FMD, PACTE_ISAE, PACTE_ISOE, RDT
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire

__all__ = [
    "calc_transport",
    "forfait_mobilite_durable",
    "indemnite_detachement",
    "indemnite_fonctions_part_cpge",
    "indemnite_isoe",
    "indemnite_transport",
    "part_fonctionnelle",
    "participation_psc",
    "prime_equipement_info",
    "psc_declaree",
]

# Les tables du barème du paquet (les fonctions prennent un barème : bareme=…).
_PRIME_ATTRACTIVITE: list[dict[str, Any]] = sorted(config.get("prime_attractivite"), key=lambda e: e["date"])


# Qui touche quoi, selon le corps (Fonctionnaire.corps).
# ISOE : « personnels enseignants du second degré » et « enseignants des classes
# post-baccalauréat » (décret 93-55, art. 1 et 2, https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000725858/2026-10-17/).
# Les professeurs documentalistes, certifiés, touchent leur indemnité de sujétions
# particulières à la place (indemnites_corps.py).
CORPS_ISOE = frozenset({"Agrégé", "Certifié", "PLP", "PEPS", "Chaire Supérieure"})
# ISAE : professeurs des écoles (décret 2013-790, https://www.legifrance.gouv.fr/loda/id/JORFTEXT000027914226/2026-10-17/).
CORPS_ISAE = frozenset({"PE"})
# Prime d'attractivité : pas les corps accessibles uniquement par liste d'aptitude, donc
# pas les chaires supérieures (décret 2021-276, art. 2, https://www.legifrance.gouv.fr/loda/id/JORFTEXT000043246480/2026-10-17/).
CORPS_SANS_PRIME_ATTRACTIVITE = frozenset({"Chaire Supérieure"})
# ISOE part modulable : code 201228 jusqu'au 31/8/2024, 202566 ensuite (codes.toml).
DATE_RECODAGE_ISOE_MODULABLE = dt.date(2024, 9, 1)
# Pacte : les mois des neuf neuvièmes, supposés (aucun texte lu ne les donne).
MOIS_PACTE = frozenset({10, 11, 12, 1, 2, 3, 4, 5, 6})


def calc_transport(mensuel: float, date: dt.date, bareme: Bareme = BAREME) -> float:
    if not mensuel:
        return 0.0  # sans abonnement, ni taux ni plafond à lire
    val = bareme.load("transport.taux").taux(mensuel, date)
    return min(val, bareme.au("transport.plafond", date))


def indemnite_detachement(fonc: Fonctionnaire, date: dt.date) -> Ligne | None:
    """Indemnité de fonction d'un enseignant détaché à la Défense (201150), versée
    mensuellement (décret 2003-745, art. 3). Son montant est individuel : une décision du
    ministre de la Défense le fixe, dans la limite de quatre fois le montant moyen de la
    catégorie de l'établissement (sept fois dans les écoles d'enseignement supérieur), indexé
    sur le point (art. 2 ; arrêté du 31/07/2003 : 770 € en moyenne pour les lycées
    militaires). bpaye prend donc le montant annuel déclaré (``indemnite_fonction``)."""
    if not fonc.is_detache(date):
        return None
    annuel = fonc.indemnite_detachement.au(date, None)
    if annuel is None:
        raise ValueError(
            f"détachement à la Défense le {date} : déclarer indemnite_fonction, le montant annuel "
            "de la décision individuelle, dans [[detachements]] (décret 2003-745, art. 2)"
        )
    montant = fonc.au_prorata(round(annuel / 12, 2), date)
    return Ligne(montant, "Indemnité de fonction (Défense)", code=201150, classe="INDEM")


def indemnite_fonctions_part_cpge(
    fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME
) -> Ligne | None:
    """IFP, aux seuls enseignants dont la rentrée est en CPGE (carriere.toml).

    Écart au texte, choisi : le montant suit celui de la paie (taux.toml, ifp_cpge), 0,07 %
    au-dessus des 6 270 F de l'arrêté du 19/10/1999 convertis et indexés sur le point, faute
    d'un texte qui fixe la base et l'arrondi de l'indexation (docs/indexation.md)."""
    if not fonc.en_cpge(date):
        return None
    montant = fonc.au_prorata(bareme.au("ifp_cpge", date), date)
    return Ligne(montant, "Indemnité Fonctions particulières CPGE", code=200597, classe="INDEM")


def indemnite_isoe(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """ISOE part fixe, aux corps enseignants du second degré (CORPS_ISOE)."""
    if fonc.corps_au(date) not in CORPS_ISOE:
        return None
    if len(fonc.documentaliste) and fonc.documentaliste(date):
        return None  # leur indemnité de sujétions particulières (indemnites_corps.py)
    montant = fonc.au_prorata(bareme.au("isoe", date), date)
    return Ligne(montant, "ISOE Part fixe", code=200364, classe="INDEM")


def indemnite_isae(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """ISAE part fixe (201914), aux professeurs des écoles."""
    if fonc.corps_au(date) not in CORPS_ISAE:
        return None
    montant = fonc.au_prorata(bareme.au("isae", date), date)
    return Ligne(montant, "ISAE", code=201914, classe="INDEM")


def indemnite_education_prioritaire(
    fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME
) -> Ligne | None:
    """Indemnité de sujétion REP (201883) ou part fixe REP+ (201882), au douzième
    (décret 2015-1087, art. 1-2 : part fixe versée mensuellement)."""
    reseau = fonc.education_prioritaire.au(date, None)
    if reseau is None:
        return None
    if reseau == "REP":
        montant = fonc.au_prorata(bareme.au("rep", date), date)
        return Ligne(montant, "Indemnité de sujétion REP", code=201883, classe="INDEM")
    if reseau == "REP+":
        montant = fonc.au_prorata(bareme.au("rep_plus", date), date)
        return Ligne(montant, "Indemnité de sujétion REP+", code=201882, classe="INDEM")
    raise ValueError(f"éducation prioritaire inconnue {reseau!r}, attendu « REP » ou « REP+ »")


def isoe_part_modulable(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """ISOE part modulable du professeur principal, au douzième, selon le niveau de sa
    classe (taux.toml [isoe_modulable], indexée sur le point) ; depuis 2009, depuis 2021 pour
    le professeur référent."""
    niveau = fonc.professeur_principal.au(date, None)
    if niveau is None:
        return None
    if niveau not in bareme.get("isoe_modulable"):
        raise ValueError(f"niveau de professeur principal inconnu {niveau!r}")
    code = 202566 if date >= DATE_RECODAGE_ISOE_MODULABLE else 201228
    montant = fonc.au_prorata(bareme.au(f"isoe_modulable.{niveau}", date), date)
    return Ligne(montant, "ISOE Part modulable", code=code, classe="INDEM")


def montant_par_echelon(versions: list[dict[str, Any]], echelon: int, date: dt.date) -> float:
    """Le montant annuel de l'``echelon`` dans la version de ``versions`` en vigueur à
    ``date`` (entrées datées, chacune avec ``montants`` par échelon)."""
    en_vigueur = sorted((e for e in versions if e["date"] <= date), key=lambda e: e["date"])
    if not en_vigueur:
        return 0.0
    montants = en_vigueur[-1]["montants"]
    return float(montants[echelon - 1]) if echelon <= len(montants) else 0.0


def prime_attractivite(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """Prime d'attractivité (202326), selon l'échelon de classe normale : rien en hors
    classe ni en classe exceptionnelle, ni pour les corps qui en sont exclus
    (CORPS_SANS_PRIME_ATTRACTIVITE). Versée chaque mois, au douzième arrondi au centime."""
    grille = fonc.grille.value(date)
    if grille.classe != "CN" or fonc.corps_au(date) in CORPS_SANS_PRIME_ATTRACTIVITE:
        return None
    annuel = montant_par_echelon(bareme.get("prime_attractivite"), fonc.echelon(date), date)
    if annuel == 0.0:
        return None
    montant = fonc.au_prorata(round(annuel / 12, 2), date)
    return Ligne(montant, "Prime d'attractivité", code=202326, classe="INDEM")


def part_fonctionnelle(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """Les parts fonctionnelles du Pacte de l'année scolaire (Fonctionnaire.pacte, demi-parts
    permises), au neuvième arrondi au centime, les mois de MOIS_PACTE. Code 202476 pour un
    professeur des écoles (ISAE), 202475 sinon (ISOE, CPE et PsyEN compris : décret 93-55,
    art. 3-1). Non soumise à retenue pour pension (décret 93-55, art. 1) ; réduction de
    cotisations et exonération d'impôt comme les heures supplémentaires (décret 2019-133,
    art. 1, 29°)."""
    parts = fonc.pacte.au(date, 0.0)
    if not parts or date.month not in MOIS_PACTE:
        return None
    montant = round(parts * bareme.load("pacte_part").value_annuel(date) / 9, 2)
    code = PACTE_ISAE if fonc.corps_au(date) in CORPS_ISAE else PACTE_ISOE
    return Ligne(montant, "Part fonctionnelle (Pacte)", code=code, classe="INDEM")


def indemnite_transport(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    return Ligne(
        calc_transport(fonc.frais_transport(date), date, bareme),
        "REMBT DOMICILE-TRAVAIL",
        code=RDT,
        classe="INDEM",
    )


def participation_psc(date: dt.date, bareme: Bareme = BAREME) -> Ligne:
    """Participation mensuelle employeur à la mutuelle (PSC)."""
    return Ligne(bareme.au("psc", date), "Participation PSC", code=202354, classe="INDEM")


def psc_declaree(fonc: Fonctionnaire, date: dt.date, classe: str, bareme: Bareme = BAREME) -> list[Ligne]:
    """Les lignes de [[psc]] d'agent.toml de la ``classe`` donnée.

    « INDEM » : les participations de l'employeur, depuis mai 2026 (taux.toml) : à l'option
    santé, la moitié de son coût déclaré dans la limite de 5 € (202483) ; à la prévoyance,
    7 € par mois si l'agent y adhère (202510).

    « CHARGE » : l'ancienne mutuelle précomptée sur la paie (700678, 700671), aux montants
    du contrat, jusqu'à la PSC. Elle reste dans le net imposable, supposé : une adhésion
    facultative n'est pas un contrat collectif obligatoire, seul déductible (CGI, art. 83,
    1° quater ; BOI-RSA-BASE-30-10-20) ; aucun bulletin qui en porte n'a été lu."""
    declare = fonc.psc_declaree(date)
    lignes = []
    if classe == "INDEM":
        if cout := declare.get("cout_option", 0.0):
            taux, plafond = bareme.au("psc_option.taux", date), bareme.au("psc_option.plafond", date)
            participation = round(min(taux * cout, plafond), 2)
            lignes.append(Ligne(participation, "Participation PSC option santé", code=202483, classe="INDEM"))
        if declare.get("prevoyance", 0.0):
            prevoyance = bareme.au("psc_prevoyance", date)
            lignes.append(Ligne(prevoyance, "Participation PSC prévoyance", code=202510, classe="INDEM"))
    elif classe == "CHARGE":
        for cle, code, libelle in (
            ("mutuelle_adherent", 700678, "Mutuelle MGEN adhérent"),
            ("mutuelle_enfants", 700671, "Mutuelle MGEN enfants"),
        ):
            if montant := declare.get(cle, 0.0):
                lignes.append(Ligne(-montant, libelle, code=code, classe="CHARGE", imposable=True))
    return lignes


def forfait_mobilite_durable(fonc: Fonctionnaire, date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """FMD : versement annuel unique en janvier, au niveau attribué à l'agent."""
    niveau = fonc.fmd_niveau(date)
    if not niveau:
        return None
    montant = bareme.au(f"fmd.n{int(niveau)}", date)
    if montant == 0.0:
        return None
    return Ligne(montant, "Forfait Mobilité Durable", code=FMD, classe="INDEM")


def prime_equipement_info(date: dt.date, bareme: Bareme = BAREME) -> Ligne | None:
    """PRIME ÉQUIP. INFO : versement annuel unique, uniquement le mois de versement."""
    montant = bareme.au("prime_eq_info", date)
    if montant == 0.0:
        return None
    return Ligne(montant, "Prime équipement informatique", code=202321, classe="INDEM")
