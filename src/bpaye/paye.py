"""Le bulletin d'un mois et la paye d'une carrière : génération, événements, sélection.

Bulletin assemble les lignes d'un mois (traitement, indemnités, heures, cotisations,
impôt) ; Paye les génère mois après mois et y applique ce que la carrière ne prévoit
pas (retards de paiement, rappels, erreurs, colles). P.select joint les montants des
bulletins PDF aux lignes calculées, pour comparer calcul et réel.
"""

import datetime as dt
import warnings
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, ClassVar, Protocol, Self

import bpaye.format as fmt
import bpaye.rafp
from bpaye.academies import Retard
from bpaye.charges import (
    contribution_solidarite,
    crds,
    csg,
    csg_basculee,
    csg_nonded,
    ir,
    transfertprimepoint,
)
from bpaye.charges_impots import ExonerationHS, facteur_hs_net, reduc_cotis_hs
from bpaye.classes import Ligne, ListeLignes, Selection, Somme
from bpaye.codes import (
    FMD,
    HSE,
    PENSION,
    PRELEVEMENT_SOURCE,
    RAFP,
    RDT,
    RESIDENCE,
    SFT,
    TRAITEMENT,
    equivalents,
)
from bpaye.colles import Colle, Colles
from bpaye.config import BAREME, Bareme
from bpaye.fonctionnaire import Fonctionnaire
from bpaye.gipa import gipa as ligne_gipa
from bpaye.hsa import hsa, hsa_majo, hse, hsi, surveillance
from bpaye.indemnite_comp_csg import indemnite_comp_csg
from bpaye.indemnite_residence import indemnite_residence
from bpaye.indemnites import (
    forfait_mobilite_durable,
    indemnite_detachement,
    indemnite_education_prioritaire,
    indemnite_fonctions_part_cpge,
    indemnite_isae,
    indemnite_isoe,
    indemnite_transport,
    isoe_part_modulable,
    part_fonctionnelle,
    participation_psc,
    prime_attractivite,
    prime_equipement_info,
    psc_declaree,
)
from bpaye.indemnites_corps import (
    indemnite_cpe,
    indemnite_directeur,
    indemnite_documentaliste,
    indemnite_psyen,
)
from bpaye.mgen import mgen_charges, mgen_part_employeur
from bpaye.pc import pension_civile
from bpaye.point import (
    calc_traitement_brut,
    traitement_brut,
    traitement_indiciaire,
    traitement_nbi,
    traitement_plein,
)
from bpaye.sft import sft, sft_du_mois
from bpaye.temps_partiel import reduit, taux_surcotisation
from bpaye.utils import decalage_mois, dernier_jour, previous_month, range_mois, truncate

__all__ = [
    "CODE_RAPPEL",
    "CODE_RAPPEL_TRAITEMENT",
    "Annee",
    "Bulletin",
    "Paye",
    "signe_bpaye",
]

# Codes internes des rappels d'une promotion payée en retard (Paye.retard_statut), absents
# de la nomenclature : le bulletin réel les porte dans un décompte de rappel à part.
CODE_RAPPEL = 999999
CODE_RAPPEL_TRAITEMENT = 999998


def _mois_de_paiement(
    mois_du: tuple[int, int], decalage: int, paiement_date: tuple[int, int] | None
) -> tuple[int, int]:
    """Le mois où un rappel est payé : ``paiement_date``, sinon ``decalage`` mois après le
    mois dû."""
    return paiement_date if paiement_date is not None else decalage_mois(*mois_du, decalage)


def _libelle_rappel(nature: str, mois_du: tuple[int, int], libelle: str) -> str:
    """Le libellé d'une ligne payée un autre mois : « [2025-3] RAPPEL Majo 1ère HSA ». Le
    mois dû vient en tête, sur neuf caractères au plus : deux rappels d'une rubrique versés
    le même mois s'y fusionnent (Bulletin.append, « [2025-10][2025-11] RAPPEL … »)."""
    annee, mois = mois_du
    return f"[{annee}-{mois}] {nature} {libelle}"


# La classe d'une ligne de retenue, par code ; les autres retenues sont des charges.
_CLASSE_DE_RETENUE = {PENSION: "PC", RAFP: "RAFP", PRELEVEMENT_SOURCE: "IMPOT"}


def _classe_du_code(code: int) -> tuple[str, int]:
    """La classe d'une ligne de ce code et le signe de son montant (bpaye : une retenue est
    négative), d'après la catégorie du code (codes.toml)."""
    from bpaye.codes import ALL_CODES

    if ALL_CODES.get(f"{code:06d}", {}).get("cat") == "retenue":
        return _CLASSE_DE_RETENUE.get(code, "CHARGE"), -1
    return ("BRUT" if code == TRAITEMENT else "INDEM"), 1


def signe_bpaye(ligne: Ligne) -> int:
    """Le signe qu'un montant lu sur le PDF (positif dans sa colonne, négatif pour un
    trop-perçu) prend dans la convention de bpaye : celui de la ligne calculée, ou, pour une
    ligne nulle, celui de sa catégorie (une retenue est négative)."""
    if ligne.valeur:
        return -1 if ligne.valeur < 0 else 1
    from bpaye.codes import ALL_CODES  # codes.toml, lu seulement pour comparer aux PDF

    return -1 if ALL_CODES.get(f"{ligne.code:06d}", {}).get("cat") == "retenue" else 1


# Les classes de lignes que generate_charges recalcule à chaque changement du bulletin.
CLASSES_CHARGES = ("CHARGE", "PC", "RAFP", "IMPOT")


class HeureSup(Protocol):
    """Une rubrique d'heures ponctuelles : hsa.hse, hsa.hsi, hsa.surveillance."""

    def __call__(
        self,
        fonctionnaire: Fonctionnaire,
        date: dt.date,
        heures: float,
        comm: str = "",
        bareme: Bareme = BAREME,
    ) -> Ligne: ...


class LigneColles(Protocol):
    """Une ligne de paiement de colles d'une archive de déclarations (Paye.from_prepa_plus)."""

    @property
    def date_ramassage(self) -> dt.date: ...

    @property
    def code(self) -> int: ...

    @property
    def heures(self) -> float: ...

    @property
    def paiement(self) -> tuple[int, int] | None: ...

    @property
    def ramassage(self) -> object: ...


class ArchiveColles(Protocol):
    """Une archive de colles déclarées, que lit Paye.from_prepa_plus."""

    def lignes_paiement(self) -> Iterable[LigneColles]: ...


class Bulletin(ListeLignes):
    def __init__(
        self,
        fonctionnaire: Fonctionnaire,
        year: int,
        month: int,
        rafp: bpaye.rafp.RAFP,
        comm: str,
        exo_hs: ExonerationHS | None = None,
        bareme: Bareme = BAREME,
    ) -> None:
        self.fonctionnaire = fonctionnaire
        self.bareme = bareme
        self.rafp_calculateur = rafp
        self.date = dernier_jour(year, month)
        depart = getattr(fonctionnaire, "date_depart", None)
        if depart is not None and self.date < depart:
            raise ValueError(f"Bulletin de {month:02d}/{year} : avant l'entrée dans la carrière, le {depart}")
        self.comm = comm
        self.lignes: list[Ligne] = []
        self.codes_charges: list[int] = []
        self.autres_charges: list[Ligne] = []
        self.exo_hs = exo_hs  # charges_impots.ExonerationHS, partagée par les bulletins
        self._hs_exonerees = 0.0
        if exo_hs is not None:
            exo_hs.inscrit(self)
        self.generate()

    @property
    def hs_exonerees(self) -> float:
        """Le brut d'heures supplémentaires exonéré d'impôt sur ce bulletin."""
        return self.exo_hs.brut_exonere(self) if self.exo_hs is not None else 0.0

    @property
    def hs_exa_net(self) -> float:
        """011200 : les heures exonérées, nettes de leur CSG déductible."""
        return truncate(self.hs_exonerees * facteur_hs_net(self.date, self.bareme), 2)

    # Frais exonérés d'impôt : remboursement domicile-travail et forfait mobilités durables.
    FRAIS_EXONERES = (RDT, FMD)

    @property
    def frais_exoneres(self) -> float:
        """Les remboursements de frais du mois (FRAIS_EXONERES), hors de l'impôt et des
        cotisations."""
        return self.total(*self.FRAIS_EXONERES)

    @property
    def net_imposable(self) -> float:
        """Le net imposable : les frais exonérés en sortent ; la part employeur de la
        complémentaire santé obligatoire (MGEN, 720580), avantage imposable, y entre depuis
        mai 2026. Retrouve le montant imposable des bulletins de 2025 et 2026."""
        frais = self.frais_exoneres
        # Les heures exonérées en sortent, nettes (011200), avec leur CSG basculée en non
        # déductible : bulletins de janvier à mars 2024 à 2026, au centime.
        hs = self.hs_exonerees
        exonere = self.hs_exa_net + csg_basculee(self.assiette_csg, self.date, hs, self.bareme) if hs else 0.0
        return super().net_imposable - frais + mgen_part_employeur(self.date, self.bareme) - exonere

    def generate(self) -> None:
        date = self.date
        fonc = self.fonctionnaire
        b = self.bareme
        self.append(traitement_brut(fonc, date, b))
        self.append(traitement_nbi(fonc, date, b))
        self.append(sft(fonc, date, b))
        self.append(indemnite_residence(fonc, date, b))
        self.append(indemnite_transport(fonc, date, b))
        enseigne = fonc.ors(date) > 0  # un CPE ou un PsyEN n'a pas d'ORS (ors.CORPS_SANS_ORS)
        if enseigne:
            self.append(hsa(fonc, date, b))
        self.append(indemnite_isoe(fonc, date, b))
        self.append(indemnite_isae(fonc, date, b))
        self.append(prime_attractivite(fonc, date, b))
        self.append(isoe_part_modulable(fonc, date, b))
        self.append(indemnite_education_prioritaire(fonc, date, b))
        self.append(part_fonctionnelle(fonc, date, b))
        if enseigne:
            self.append(hsa_majo(fonc, date, b))
        self.append(indemnite_cpe(fonc, date, b))
        self.append(indemnite_psyen(fonc, date, b))
        self.append(indemnite_documentaliste(fonc, date, b))
        self.append(indemnite_directeur(fonc, date, b))
        self.append(indemnite_fonctions_part_cpge(fonc, date, b))
        self.append(indemnite_detachement(fonc, date))
        self.append(indemnite_comp_csg(date, fonc, b))
        self.append(participation_psc(date, b))
        for ligne in psc_declaree(fonc, date, "INDEM", b):
            self.append(ligne)
        self.append(forfait_mobilite_durable(fonc, date, b))
        self.append(prime_equipement_info(date, b))
        self.generate_charges()

    def generate_charges(self) -> None:
        self._en_calcul = True
        try:
            self._generate_charges()
        finally:
            self._en_calcul = False

    def _generate_charges(self) -> None:
        date = self.date
        self.remove_charges()
        b = self.bareme
        self.append(self.retenue_pension())
        self.append(transfertprimepoint(date, b))
        mge = mgen_part_employeur(date, b)
        hs_exonerees = self.hs_exonerees
        self.append(csg_nonded(self.assiette_csg, date, mge, hs_exonerees, b))
        self.append(csg(self.assiette_csg, date, mge, hs_exonerees, b))
        self.append(crds(self.assiette_csg, date, mge, hs_exonerees, b))
        self.append(self.rafp_calculateur(date, self.traitement_percu, self.assiette_rafp))
        self.append(contribution_solidarite(self.assiette_cs, date, self.net_mensuel_cs, b))
        if self.hs_brut > 0 and (reduction := reduc_cotis_hs(self.hs_brut, self.brut * 12, date, b)):
            self.append(reduction)
        # La part solidaire suit la rémunération brute du mois, pas le seul traitement
        # indiciaire (bulletin d'août 2026 sous le plafond : 24,78 € sur 3 403,54 € d'éléments
        # à payer, 19,60 € sur le traitement de 2 692,76 €). Les remboursements de frais n'en
        # sont pas, supposé : ce bulletin n'en a pas.
        frais = self.frais_exoneres
        for ligne in mgen_charges(self.revenus - frais, date, b):
            self.append(ligne)
        for ligne in psc_declaree(self.fonctionnaire, date, "CHARGE", b):
            self.append(ligne)
        for ligne in self.autres_charges:
            self.append(ligne)
        self.append(ir(self.net_imposable, date, self.fonctionnaire.taux_pas))
        if self.exo_hs is not None and hs_exonerees != self._hs_exonerees:
            # Le reste du plafond change pour les mois suivants de l'année.
            self._hs_exonerees = hs_exonerees
            for suivant in self.exo_hs.suivants(self):
                suivant.generate_charges()

    def retenue_pension(self) -> Ligne:
        """Pension civile sur le traitement perçu ; pour un agent à temps partiel qui
        surcotise (code des pensions, L11 bis), sur le traitement et la NBI d'un temps plein
        au taux de l'art. D5 (temps_partiel.py). Les rappels de traitement (999999, en
        classe INDEM) ont leur propre régulation de pension."""
        date, fonc, b = self.date, self.fonctionnaire, self.bareme
        option = fonc.surcotisation.au(date, False)
        quotite = fonc.quotite_au(date)
        if not option or quotite >= 1.0:
            return pension_civile(self.brut, date, b)
        taux = taux_surcotisation(quotite, date, option, b)
        montant = round(traitement_plein(fonc, date, b) * taux, 2)
        return Ligne(-montant, "Pension civile (surcotisation)", code=PENSION, classe="PC")

    def check_changes(self) -> str:
        s = ""
        prev: object  # indice, valeur du point, ORS, heures ou échelon : seulement affichés
        actuel: object
        if self.fonctionnaire.grille.changed_trigger(self.date):
            try:
                prev_date = previous_month(self.date)
                prev = self.fonctionnaire.indice(prev_date)
                actuel = self.fonctionnaire.indice(self.date)
                s += f"    La grille a changé : l'indice passe de {prev} à {actuel}\n"
            except ValueError:
                actuel = self.fonctionnaire.indice(self.date)
                s += f"    La grille a changé : l'indice passe à {actuel}\n"
        point = self.bareme.load("point")  # celui de la Paye, pas celui du paquet
        if point.changed_trigger(self.date):
            try:
                prev = point.previous_value(self.date)
                actuel = point(self.date)
                s += f"    La valeur du point a augmenté de {prev} à {actuel}\n"
            except ValueError:
                actuel = point(self.date)
                s += f"    La valeur du point a augmenté à {actuel}\n"
        fonc = self.fonctionnaire
        if fonc.ors.changed_trigger(self.date):
            for nom, temporal in (("L'ORS", fonc.ors), ("Le nombre d'HSA", fonc.vs)):
                prev, actuel = temporal.previous_value(self.date), temporal(self.date)
                if prev is None:
                    s += f"    {nom} : {actuel}\n"
                elif prev != actuel:
                    s += f"    {nom} passe de {prev} à {actuel}\n"
        if self.fonctionnaire.echelon.changed_trigger(self.date):
            try:
                prev = self.fonctionnaire.echelon.previous_value(self.date)
                actuel = self.fonctionnaire.echelon(self.date)
                s += f"    Avancement d'échelon de {prev} à {actuel}\n"
            except ValueError:
                actuel = self.fonctionnaire.echelon(self.date)
                s += f"    Avancement d'échelon à {actuel}\n"
        return s

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def month(self) -> int:
        return self.date.month

    def getindex_fromcode_and_montant(self, code: int, montant: float) -> int:
        for i, ligne in enumerate(self):
            if ligne.code == code and (
                truncate(ligne.valeur, 2) == montant or truncate(ligne.valeur, 2, up=True) == montant
            ):
                return i
        raise ValueError(f"Code non trouvé {code} {montant}€")

    def pop(self, code: int, recalc: bool = False) -> Ligne:
        index = self.getindex_fromcode(code)
        ligne = self.lignes.pop(index)
        if recalc:
            self.generate_charges()
        return ligne

    def pop_montant(self, code: int, montant: float, recalc: bool = False) -> Ligne:
        index = self.getindex_fromcode_and_montant(code, montant)
        ligne = self.lignes.pop(index)
        if recalc:
            self.generate_charges()
        return ligne

    def append(self, ligne: Ligne | None, recalc: bool = False, newcharge: bool | None = None) -> None:
        """Ajoute une ligne, sommée à celle de même code si elles sont sommables.

        Une charge (CSG, pension, RAFP, impôt…) ajoutée hors du calcul des charges est
        gardée dans autres_charges (``newcharge`` par défaut) : sans cela, le recalcul qui
        suit l'effacerait avec les charges calculées."""
        if ligne is None:
            return
        code = ligne.code
        classe = ligne.type
        if newcharge is None:
            newcharge = not getattr(self, "_en_calcul", False)
        if ligne.valeur != 0 and classe in CLASSES_CHARGES and newcharge:
            self.autres_charges.append(ligne.copy())
            if recalc or not getattr(self, "_en_calcul", False):
                self.generate_charges()
            return
        if ligne.valeur != 0:
            autreligne = self.get_fromcode_sommable(code)
            if autreligne is not None:
                assert code == autreligne.code and classe == autreligne.type
                if autreligne.exacte is not None and ligne.exacte is not None:
                    # Rappelées ensemble, des lignes s'arrondissent depuis la somme de leurs
                    # montants exacts : deux neuvièmes d'HSA (2 × 2 742,4055 €) font
                    # 5 484,81 € sur le bulletin de décembre 2017, non 2 × 2 742,41 €.
                    autreligne.exacte += ligne.exacte
                    autreligne.valeur = round(autreligne.exacte, 2)
                else:
                    autreligne.exacte = None
                    autreligne.valeur = autreligne.valeur + ligne.valeur
                autreligne.lib = autreligne.lib[:9] + ligne.lib
            else:
                self.lignes.append(ligne)
                self.sort()
                if classe in CLASSES_CHARGES:
                    self.codes_charges.append(code)
            if recalc:
                self.generate_charges()

    def remove_charges(self) -> None:
        codes = set(self.codes_charges)
        self.lignes = [ligne for ligne in self.lignes if ligne.code not in codes]
        self.codes_charges = []

    @property
    def assiette_cs(self) -> float:
        """La rémunération nette totale de la contribution de solidarité, hors remboursements
        de frais professionnels (code du travail, L5423-27) : nette de la pension, de la RAFP
        et du transfert primes/points, abattement sur les primes qui diminue la rémunération.
        Le transfert n'est pas nommé par un texte lu ; relevé sur 11 bulletins de 2017 sur 12,
        au centime (le douzième compte en plus le rappel net d'un décompte)."""
        frais = self.frais_exoneres
        return self.revenus - frais + self.rafp + self.pc + self.tpp

    @property
    def net_mensuel_cs(self) -> float:
        """La rémunération mensuelle nette du seuil de la contribution de solidarité :
        traitement et indemnité de résidence, nets de la pension et de la RAFP (L5423-32)."""
        residence = self.total(RESIDENCE)
        return self.brut + residence + self.pc + self.rafp

    @property
    def assiette_csg(self) -> float:
        # RDT (200039) et FMD (200041) sont des remboursements de frais, exonérés de CSG/CRDS
        frais_pro = self.frais_exoneres
        return self.revenus + self.tpp - frais_pro

    @property
    def ind_tot(self) -> float:
        return self.ind + self.tpp

    @property
    def traitement_percu(self) -> float:
        """Le traitement indiciaire perçu ce mois, rappel de traitement compris : la base du
        plafond de la RAFP (décret 2004-569, art. 2 : « traitement indiciaire brut total […]
        perçu[] au cours de l'année »)."""
        rappel = self.total(CODE_RAPPEL_TRAITEMENT)
        return self.brut + rappel

    @property
    def assiette_rafp(self) -> float:
        """Les revenus d'activité de l'assiette de la CSG, hors ceux qui comptent pour la
        pension (traitement et NBI, de classe BRUT, et rappel de traitement) : décret
        2004-569, art. 2. Les remboursements de frais en sortent, comme de la CSG ; la part
        employeur de la PSC santé (720580) y entre."""
        rappel = self.total(CODE_RAPPEL_TRAITEMENT)
        assiette_csg_hors_traitement = self.assiette_csg - self.brut - rappel
        return assiette_csg_hors_traitement + mgen_part_employeur(self.date, self.bareme)

    def join(self, pdf_data: Mapping[str, Any]) -> Self:
        """Attache les montants réels (PDF) à chaque Ligne du bulletin.

        pdf_data : dict retourné par extract_bulletin().
        Les montants sont signés selon la convention bpaye (positif=revenu, négatif=retenue).
        Rend le bulletin, pour enchaîner les appels.
        """
        for ligne in self.lignes:
            # Un code équivalent (codes.CODES_EQUIVALENTS) porte la même ligne.
            keys = [key for key in sorted(equivalents(f"{ligne.code:06d}")) if key in pdf_data]
            if keys:
                ligne.valeur_reel = signe_bpaye(ligne) * sum(pdf_data[key] for key in keys)
        return self

    def __str__(self) -> str:
        w = fmt.WIDTH
        wl = fmt.LIB_WIDTH - 1
        wc = fmt.MT_WIDTH
        fc = fmt.MT_FORMAT
        s = ""
        s += "*" * w + "\n"
        s += f"{fmt.MOIS[self.date.month - 1]} {self.date.year}"
        if self.comm != "":
            s += f" ({self.comm})"
        fonc = self.fonctionnaire
        corps = fonc.corps_au(self.date)
        s += f" -- {corps} {fonc.grille(self.date).classe} ({fonc.indice(self.date)}) "
        s += f"    ORS: {self.fonctionnaire.ors(self.date)}, HSA:{self.fonctionnaire.vs(self.date)}\n"
        s += self.check_changes()
        s += "-" * w + "\n"
        for ligne in self:
            s += " " + str(ligne) + "\n"
        s += "-" * w + "\n"
        s += " " * wl + "BRUT TOTAL :" + fc.format(self.revenus) + "\n"
        s += " " * wl + "CHARGES    :" + " " * wc + fc.format(self.pc + self.rafp + self.charges) + "\n"
        s += " " * wl + "Net impos. :" + fc.format(self.net_imposable) + "\n"
        s += " " * wl + "NET        :" + fc.format(self.net) + "\n"
        return s

    def __repr__(self) -> str:
        return self.__str__()


class Annee:
    def __init__(self, annee: int) -> None:
        self.annee = annee
        self.bulletins: list[Bulletin] = []

    def __getitem__(self, i: int) -> Bulletin:
        return self.bulletins[i]

    def __iter__(self) -> Iterator[Bulletin]:
        return iter(self.bulletins)

    def __len__(self) -> int:
        return len(self.bulletins)

    def append(self, b: Bulletin) -> None:
        self.bulletins.append(b)

    def sort(self) -> None:
        self.bulletins.sort(key=lambda b: b.date)

    def __getattr__(self, attr: str) -> Any:
        """La somme sur l'année d'une grandeur du bulletin (``annee.net``, ``annee.brut``) ;
        un nom que le bulletin n'a pas reste une erreur, même pour une année vide."""
        if attr.startswith("_") or not hasattr(Bulletin, attr):
            raise AttributeError(attr)
        return sum(getattr(b, attr) for b in self)


class Paye:
    def __init__(
        self,
        fonctionnaire: Fonctionnaire,
        libelle: str = "",
        bull_dir: str | Path | None = None,
        bareme: Bareme = BAREME,
    ) -> None:
        """La paye de ``fonctionnaire``, calculée avec ``bareme`` (celui du paquet par défaut,
        ou config.Bareme.depuis_fichiers(…) pour d'autres taux)."""
        self.fonctionnaire = fonctionnaire
        self.bareme = bareme
        self.libelle = libelle
        self.bull_dir = bull_dir  # chemin vers le dossier des PDF (optionnel)
        self.bulletins: list[Bulletin] = []
        self.annees: dict[int, Annee] = {}  # année → ses bulletins
        self.RAFP = bpaye.rafp.RAFP(bareme)  # objet callable, donné à bulletin, qui garde en mémoire
        self.EXO_HS = ExonerationHS(bareme)  # plafond annuel d'exonération des heures sup., partagé
        self.COLLES = Colles(bareme=bareme)

    def annee(self, year: int) -> Annee:
        return self.annees[year]

    def generate(self, startyear: int, startmonth: int, n: int) -> None:
        nouveaux: list[Bulletin] = []
        for y, m in range_mois(start=(startyear, startmonth), n=n):
            b = Bulletin(
                self.fonctionnaire, y, m, self.RAFP, comm=self.libelle, exo_hs=self.EXO_HS, bareme=self.bareme
            )
            self.append(b)
            nouveaux.append(b)
        # Les retards habituels de la paie (academies.py) : la ligne reste due son mois et
        # arrive en rappel le mois de paiement.
        for b in nouveaux:
            for retard in self.fonctionnaire.retards(b.date).values():
                if retard.concerne(b.date):
                    self._paie_en_retard(b, retard)

    def generate_annees(self, premiere: int, derniere: int | None = None) -> None:
        """Les bulletins de janvier ``premiere`` à décembre ``derniere`` (``premiere`` seule
        par défaut). Des années entières : la RAFP se plafonne sur l'année civile, comme
        l'exonération des heures supplémentaires."""
        fin = premiere if derniere is None else derniere
        self.generate(startyear=premiere, startmonth=1, n=12 * (fin - premiere + 1))

    def _paie_en_retard(self, bulletin: Bulletin, retard: Retard) -> None:
        if not bulletin.get_all_fromcode(retard.code) or bulletin.get_fromcode(retard.code).valeur == 0:
            return
        paiement = decalage_mois(bulletin.year, bulletin.month, retard.decalage)
        if self(*paiement) is None:
            bulletin.pop(retard.code, recalc=True)  # payé après la fin des bulletins générés
        else:
            self.retard_paiement((bulletin.year, bulletin.month), retard.code, paiement_date=paiement)

    def append(self, bulletin: Bulletin) -> None:
        y, m = bulletin.year, bulletin.month
        if y not in self.annees:
            self.annees[y] = Annee(y)

        if self(y, m) is None:
            self.bulletins.append(bulletin)
            self.annees[y].append(bulletin)
        else:
            raise ValueError(f"Le bulletin de {y}-{m} existe déjà")

    def addligne(self, year: int, mois: int, ligne: Ligne, newcharge: bool | None = None) -> None:
        bulletin = self.bulletin(year, mois)
        bulletin.append(ligne, recalc=True, newcharge=newcharge)

    def sort(self) -> None:
        self.bulletins.sort(key=lambda bulletin: bulletin.date)

    def __getitem__(self, i: int) -> Bulletin:
        return self.bulletins[i]

    def __iter__(self) -> Iterator[Bulletin]:
        return iter(self.bulletins)

    def __str__(self) -> str:
        s = ""
        for b in self:
            s += str(b)
        return s

    def __repr__(self) -> str:
        return self.__str__()

    def __call__(self, year: int, mois: int) -> Bulletin | None:
        for bulletin in self:
            if year == bulletin.year and mois == bulletin.month:
                return bulletin
        return None

    def bulletin(self, year: int, mois: int) -> Bulletin:
        """Le bulletin du mois ; une erreur s'il n'a pas été généré (generate)."""
        bulletin = self(year, mois)
        if bulletin is None:
            raise ValueError(f"pas de bulletin généré pour {mois:02d}/{year}")
        return bulletin

    def _reporte(
        self,
        ligne: Ligne,
        nature: str,
        mois_du: tuple[int, int],
        libelle: str,
        decalage: int = 2,
        paiement_date: tuple[int, int] | None = None,
    ) -> None:
        """Porte ``ligne`` au mois où se paie le rappel de ``mois_du`` (_mois_de_paiement),
        sous le libellé de rappel de ``nature`` (RAPPEL, RATTRAPAGE)."""
        ligne.lib = _libelle_rappel(nature, mois_du, libelle)
        self.addligne(*_mois_de_paiement(mois_du, decalage, paiement_date), ligne)

    def retard_paiement(
        self,
        original_date: tuple[int, int],
        code: int,
        decalage: int = 2,
        paiement_date: tuple[int, int] | None = None,
    ) -> None:
        year, mois = original_date
        bulletin = self.bulletin(year, mois)
        ligne = bulletin.pop(code, recalc=True)
        ligne.sommable = True
        self._reporte(ligne, "RAPPEL", (year, mois), ligne.lib, decalage, paiement_date)

    def erreur_montant(
        self,
        original_date: tuple[int, int],
        code: int,
        montant_init: float,
        montant_final: float,
        decalage: int = 2,
        paiement_date: tuple[int, int] | None = None,
    ) -> None:
        year, mois = original_date
        bulletin = self.bulletin(year, mois)
        if bulletin(code).type in CLASSES_CHARGES:
            # Une charge se recalcule : l'erreur s'y ajoute comme un écart, gardé au recalcul.
            calculee = bulletin.lignes[bulletin.getindex_fromcode_and_montant(code, montant_init)]
            ecart = calculee.copy()
            ecart.valeur = montant_final - calculee.valeur
            ecart.lib = f"{calculee.lib} (erreur montant)"
            self.addligne(year, mois, ecart)
            rattrapage = ecart.copy()
            rattrapage.valeur = -ecart.valeur
            self._reporte(rattrapage, "RATTRAPAGE", (year, mois), calculee.lib, decalage, paiement_date)
            return
        ligne = bulletin.pop_montant(code, montant_init)
        montant_init = ligne.valeur  # au centime près, le montant exact de la ligne
        ligne.valeur = montant_final
        ligne.sommable = False
        ligne.lib = f"{ligne.lib} (erreur montant)"
        self.addligne(year, mois, ligne)
        ligne = ligne.copy()
        ligne.sommable = True
        ligne.valeur = montant_init - montant_final
        self._reporte(ligne, "RATTRAPAGE", (year, mois), ligne.lib, decalage, paiement_date)

    def heure_sup(
        self,
        fonction: HeureSup,
        original_date: tuple[int, int],
        heures: float,
        comm: str = "",
        paiement_date: tuple[int, int] | None = None,
    ) -> None:
        if paiement_date is None:
            pyear, pmois = original_date
        else:
            pyear, pmois = paiement_date
        odate = dernier_jour(pyear, pmois)
        ligne = fonction(self.fonctionnaire, odate, heures, comm, bareme=self.bareme)
        self.addligne(pyear, pmois, ligne)

    def hse(
        self,
        original_date: tuple[int, int],
        heures: float,
        comm: str = "",
        paiement_date: tuple[int, int] | None = None,
        code: int = HSE,
    ) -> None:
        """Heures supplémentaires effectives, sous ``code`` (hsa.CODES_HSE) : 201241 pour
        un remplacement de courte durée, 201717 puis 201300 pour la réussite au lycée."""

        def fonction(
            fonctionnaire: Fonctionnaire,
            date: dt.date,
            heures: float,
            comm: str = "",
            bareme: Bareme = BAREME,
        ) -> Ligne:
            return hse(fonctionnaire, date, heures, comm, bareme, code=code)

        self.heure_sup(fonction, original_date, heures, comm, paiement_date)

    # Rémunérations à l'heure, au taux de chaque formation ou action : vacations de
    # formation (décret 2010-235), actions à pilotage national (décret 2014-1394).
    CODES_VACATION: ClassVar[dict[int, str]] = {
        201339: "Vacations de formation",
        201856: "Actions à pilotage national",
    }

    def vacation(
        self, paiement_date: tuple[int, int], heures: float, taux: float, code: int = 201339, comm: str = ""
    ) -> None:
        """``heures`` à ``taux`` € l'heure, payées le mois ``paiement_date`` : le taux est
        celui de la formation ou de l'action, que l'agent lit sur son ordre de mission."""
        if code not in self.CODES_VACATION:
            raise ValueError(f"code de vacation inconnu {code}, attendus {list(self.CODES_VACATION)}")
        libelle = f"{self.CODES_VACATION[code]} {heures}h × {taux} € {comm}".rstrip()
        self.addligne(*paiement_date, Ligne(round(heures * taux, 2), libelle, code=code, classe="INDEM"))

    def hsi(self, *args: Any, **kwargs: Any) -> None:
        self.heure_sup(hsi, *args, **kwargs)

    def surveillance(self, *args: Any, **kwargs: Any) -> None:
        """Heures de surveillance (devoirs, examens), payées le mois donné (hsa.surveillance)."""
        self.heure_sup(surveillance, *args, **kwargs)

    def colle(
        self,
        original_date: tuple[int, int],
        codesheures: dict[int, float],
        decalage: int = 2,
        payee: bool = True,
        paiement_date: tuple[int, int] | None = None,
        comm: str = "",
    ) -> list[Colle]:
        year, mois = original_date
        nouvelles = self.COLLES.append(year, mois, codesheures, comm)
        if payee:
            pyear, pmois = _mois_de_paiement((year, mois), decalage, paiement_date)
            bulletin = self.bulletin(pyear, pmois)
            Colles.paiement(bulletin, nouvelles)  # gère l'ajout dans bulletin
        return nouvelles

    def paye_colle(self, paiement_date: tuple[int, int], c: Colle) -> None:
        year, mois = paiement_date
        self.addligne(year, mois, c.paiement(dernier_jour(year, mois)))

    def colle_troppercue(
        self, paiement_date: tuple[int, int], codesheures: dict[int, float], comm: str = ""
    ) -> list[Colle]:
        year, mois = paiement_date
        bulletin = self.bulletin(year, mois)
        return self.COLLES.paye(year, mois, codesheures, comm, bulletin)

    def from_prepa_plus(self, archive: ArchiveColles, comm: str = "prepa+") -> None:
        """
        Importe les colles déclarées d'une archive : tout objet dont lignes_paiement()
        donne des lignes à date_ramassage, code, heures, paiement et ramassage : par
        exemple les déclarations de colles d'un lycée, relevées mois par mois.

        Pour chaque groupe (ramassage, code) :
          - original_date  = mois du ramassage
          - paiement_date  = mois du ramassage + archive.decalage_paiement
          - codesheures    = {code: heures}

        Paramètres
        ----------
        archive : objet à lignes_paiement()
        comm    : préfixe de commentaire dans les lignes de bulletin
        """
        for p in archive.lignes_paiement():
            original_date = (p.date_ramassage.year, p.date_ramassage.month)
            self.colle(
                original_date=original_date,
                codesheures={p.code: p.heures},
                paiement_date=p.paiement,
                comm=f"{comm} ram.{p.ramassage}",
            )

    def retard_statut(
        self,
        original_date: tuple[int, int],
        paiement_date: tuple[int, int],
        indice_retard: float | None = None,
        n_enfants_retard: int | None = None,
        every: bool = True,
    ) -> None:
        year, mois = original_date
        date = dt.date(year, mois, 1)
        previous_date = previous_month(date)
        if indice_retard is None:
            # récupération de la valeur à mettre à jour
            indice_retard = self.fonctionnaire.indice(previous_date)
        if n_enfants_retard is None:
            n_enfants_retard = self.fonctionnaire.enfants(previous_date)
        pyear, pmois = paiement_date
        pdate = dt.date(pyear, pmois, 1)
        du_traitement: float = 0
        du_sft: float = 0
        charges_du: float = 0
        while dt.date(year, mois, 1) < pdate:
            # parcoure tous les mois jusqu'à régulation
            # mise à jour des valeurs avec les données retardées
            # enregistrement des anciennes (dues)
            bulletin = self.bulletin(year, mois)
            pc_due = bulletin(PENSION).valeur  # avant d'enlever des lignes, qui refont calculer...
            ligne_brut = bulletin.pop(TRAITEMENT)
            # Sans enfant à charge, le bulletin n'a pas de ligne de SFT.
            sft_du = bulletin.pop(SFT).valeur if bulletin.get_all_fromcode(SFT) else 0.0
            # Le traitement et le SFT perçus à l'ancien indice, comme ceux du bulletin : à la
            # fraction d'un temps partiel, le SFT sur le traitement et la NBI d'un temps plein.
            jour = bulletin.date
            fraction = self.fonctionnaire.fraction(jour)
            plein_retard = calc_traitement_brut(indice_retard, jour, self.bareme)
            brut_retard = reduit(plein_retard, fraction)
            bulletin.append(Ligne(brut_retard, f"Traitement Brut (indice {indice_retard})", code=TRAITEMENT))
            nbi = traitement_plein(self.fonctionnaire, jour, self.bareme) - traitement_indiciaire(
                self.fonctionnaire, jour, self.bareme
            )
            sft_retard = sft_du_mois(n_enfants_retard, plein_retard + nbi, fraction, jour, self.bareme)
            bulletin.append(
                Ligne(
                    sft_retard,
                    f"Supplément familial traitement ({n_enfants_retard} enfants)",
                    code=SFT,
                    classe="INDEM",
                )
            )
            bulletin.generate_charges()  # pension et cotisations sur ce qui a été perçu
            pc_retard = bulletin(PENSION).valeur
            # cumuls :
            changement = self.fonctionnaire.changement_d_indice(jour)
            if changement is not None:
                # Le mois où l'échelon change, la paie ne rappelle que les jours à compter du
                # changement, chaque traitement tronqué, et la pension sur chacun : décomptes
                # de rappel de juillet 2018 (mars 2018, 23 jours : 2 496,86 − 2 320,83) et de
                # juillet 2021 (septembre 2020 : 2 719,61 − 2 550,75 = 168,86, retenue PC
                # 301,88 − 283,13). Le rappel passe d'un centime le dû moins le perçu.
                jours, _, i_nouveau = changement
                nouveau = reduit(calc_traitement_brut(i_nouveau, jour, self.bareme), fraction)
                du_part = truncate(nouveau * (30 - jours) / 30, 2)
                percu_part = truncate(brut_retard * (30 - jours) / 30, 2)
                du_traitement += du_part - percu_part
                charges_du += (
                    pension_civile(du_part, jour, self.bareme).valeur
                    - pension_civile(percu_part, jour, self.bareme).valeur
                )
            else:
                du_traitement += ligne_brut.valeur - brut_retard
                charges_du += pc_due - pc_retard
            du_sft += sft_du - sft_retard
            # incrémentation
            if every:
                year, mois = decalage_mois(year, mois, 1)
            else:
                year, mois = pdate.year, pdate.month  # un seul mois : on sort
        # régulation
        year, mois = original_date
        lib = f" {year}-{mois} - {pyear}-{pmois} (ind. {indice_retard}/{n_enfants_retard} enf.)"
        # Le rappel de traitement relève le plafond de la RAFP (traitement perçu) sans
        # entrer dans son assiette ; celui du SFT entre dans l'assiette, comme le SFT.
        rappel_traitement = Ligne(
            du_traitement, "Rappel de traitement" + lib, code=CODE_RAPPEL_TRAITEMENT, classe="INDEM"
        )
        self.addligne(pyear, pmois, rappel_traitement)
        if du_sft:
            self.addligne(
                pyear, pmois, Ligne(du_sft, "Rappel de SFT" + lib, code=CODE_RAPPEL, classe="INDEM")
            )
        ligne_pc = Ligne(truncate(charges_du, 2), "Régulation cotisation PC" + lib, code=604000, classe="PC")
        self.addligne(pyear, pmois, ligne_pc, newcharge=True)

    def gipa(self, annee: int, paiement_date: tuple[int, int]) -> None:
        """La GIPA au titre de ``annee`` (gipa.py), sur le bulletin de ``paiement_date`` ;
        rien si le traitement a suivi l'inflation."""
        ligne = ligne_gipa(self.fonctionnaire, annee, self.bareme)
        if ligne is not None:
            self.addligne(*paiement_date, ligne)

    def retard_indice(
        self,
        original_date: tuple[int, int],
        paiement_date: tuple[int, int],
        indice: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.retard_statut(original_date, paiement_date, indice_retard=indice, **kwargs)

    def retard_sft(
        self,
        original_date: tuple[int, int],
        paiement_date: tuple[int, int],
        n_enfants: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Un enfant de plus payé en retard : de ``original_date`` jusqu'à la veille de
        ``paiement_date``, les bulletins portent le SFT de ``n_enfants`` (par défaut, le
        nombre d'enfants déclaré le mois d'avant), et ``paiement_date`` rappelle l'écart.
        Le pendant de ``retard_indice`` pour le supplément familial."""
        self.retard_statut(original_date, paiement_date, n_enfants_retard=n_enfants, **kwargs)

    def erreur(
        self, date: tuple[int, int], paiement_date: tuple[int, int], montant: float, code: int
    ) -> None:
        """Une erreur de la paie : ``montant`` porté en trop le mois ``date`` sur la rubrique
        ``code``, dans le sens de sa colonne (un trop-versé, ou pour une retenue un trop-
        prélevé), puis repris le mois ``paiement_date``. La ligne prend la classe de la
        catégorie du code (codes.toml) : une retenue reste une retenue."""
        classe, signe = _classe_du_code(code)
        self.addligne(*date, Ligne(signe * montant, "Erreur", code=code, classe=classe))
        ligne_neg = Ligne(-signe * montant, code=code, classe=classe)
        self._reporte(ligne_neg, "RATTRAPAGE", date, "Erreur", paiement_date=paiement_date)

    def somme_annee(self, code_or_fn: str | int | Callable[[Bulletin], float], year: int) -> Somme:
        """Obsolète : utiliser P.select(code_or_fn, year).somme() à la place."""
        warnings.warn(
            "somme_annee() est obsolète. Utilisez select().somme().", DeprecationWarning, stacklevel=2
        )
        return self.select(code_or_fn, year).somme()

    def select(
        self,
        code_or_fn: str | int | Callable[[Bulletin], float],
        *date_args: int | dt.date | tuple[int, int] | list[int],
    ) -> Selection:
        """Les lignes d'une période de bulletins, jointes aux PDF.

        ``code_or_fn`` est un code de rubrique à 6 chiffres (toutes ses lignes, rappels du
        mois compris) ou une fonction ``lambda b: float``, qui donne une ligne calculée par
        bulletin, sans réel. La période est une année (``2025``, de janvier à décembre) ou
        deux bornes incluses (``dt.date`` ou ``(année, mois)``). Chaque ligne de la
        Selection porte ``valeur`` (calcul) et ``valeur_reel`` (PDF, s'il a été lu).
        """

        # ── Les bornes de la période ────────────────────────────────────────
        def _to_date(arg: int | dt.date | tuple[int, int] | list[int], last: bool = False) -> dt.date:
            if isinstance(arg, dt.date):
                return arg
            if isinstance(arg, (tuple, list)):
                y, m = arg
                return dernier_jour(y, m)
            # int = année
            m = 12 if last else 1
            d = 31 if last else 1
            return dt.date(arg, m, d)

        if len(date_args) == 1:
            date_start = _to_date(date_args[0], last=False)
            date_end = _to_date(date_args[0], last=True)
        elif len(date_args) == 2:
            date_start = _to_date(date_args[0], last=False)
            date_end = _to_date(date_args[1], last=True)
        else:
            raise ValueError("Attendu : select(code, year) ou select(code, date_start, date_end)")

        # ── Les bulletins de la période ────────────────────────────────────
        bulletins_in_range = [b for b in self.bulletins if date_start <= b.date <= date_end]

        # ── Chargement des PDF (une fois par année couverte) ───────────────
        pdf_by_month: dict[tuple[int, int], Mapping[str, Any]] = {}
        if self.bull_dir is not None:
            # Importé ici seulement : lire les PDF demande pdfplumber, dont le calcul de
            # la paye n'a pas besoin.
            from bpaye.bulletins import trouve_bulletins

            # Le bulletin de l'employeur du mois (bulletins.py), seul comparable au calcul.
            years_covered = {b.date.year for b in bulletins_in_range}
            for trouve in trouve_bulletins(self.bull_dir, self.fonctionnaire, years_covered):
                cle = (trouve.date.year, trouve.date.month)
                if trouve.compare and cle not in pdf_by_month:
                    pdf_by_month[cle] = trouve.lu

        # ── Construction de la Selection ───────────────────────────────────
        sel = Selection()
        if isinstance(code_or_fn, (str, int)):
            code_int = int(code_or_fn)
            sel._label = str(code_or_fn)
        else:
            code_int = -1  # non utilisé dans la branche lambda
            sel._label = getattr(code_or_fn, "__name__", repr(code_or_fn))

        for b in bulletins_in_range:
            month_key = (b.date.year, b.date.month)
            has_pdf = month_key in pdf_by_month
            sel._months_total += 1
            if has_pdf:
                sel._months_with_pdf += 1
                b.join(pdf_by_month[month_key])

            if isinstance(code_or_fn, (str, int)):
                # Un code équivalent (codes.CODES_EQUIVALENTS) porte la même ligne.
                codes = equivalents(f"{code_int:06d}")
                lignes = [ligne for ligne in b if f"{ligne.code:06d}" in codes]
                if has_pdf:
                    # Le réel du mois est celui du bulletin, le code et son rappel (_R) : bpaye
                    # n'a pas toujours la ligne du rappel (IFP de septembre 2025 payée en
                    # décembre), ni une seule ligne par code (HSA d'octobre et de novembre).
                    # La première ligne le porte ; une ligne de 0 si bpaye n'en a pas.
                    pdf = pdf_by_month[month_key]
                    reel = sum(pdf.get(c, 0.0) + pdf.get(f"{c}_R", 0.0) for c in codes)
                    if not lignes and reel:
                        lignes = [Ligne(0.0, sel._label, code=code_int)]
                    for rang, ligne in enumerate(lignes):
                        ligne.valeur_reel = signe_bpaye(ligne) * reel if rang == 0 else 0.0
                sel.lignes.extend(lignes)
            else:
                # Une grandeur calculée : le PDF n'en donne pas le réel, et une erreur du
                # calcul doit se voir plutôt que compter zéro.
                sel.lignes.append(Ligne(float(code_or_fn(b)), sel._label, code=0))

        return sel
