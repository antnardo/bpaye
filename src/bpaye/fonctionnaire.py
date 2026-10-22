"""Le fonctionnaire : sa situation, lue dans agent.toml, et sa carrière, dans carriere.toml.

Chaque donnée de carrière est datée (Temporal) : échelon et ancienneté, grille,
ORS, heures supplémentaires, enfants, résidence, détachement. Les avancements se
calculent d'après les durées de la grille en vigueur au moment du passage
(ancienneté, choix, grand choix avant PPCR), au jour anniversaire de l'entrée dans le
corps ; un échelon pris en cours de mois est payé par trentièmes des deux traitements
(point.traitement_indiciaire).
"""

import datetime as dt
from pathlib import Path
from typing import Any, Self

from bpaye.academies import ACADEMIE_PAR_DEFAUT, CleRetard, Retard, lit_retard, remplace, retards_academie
from bpaye.classes import Fixe, Taux, Temporal
from bpaye.colles import CollesExternes, CollesPrevues
from bpaye.config import depuis_section
from bpaye.employeurs import Employeur, lit_employeur
from bpaye.grille import Grille
from bpaye.hsa import CODE
from bpaye.ors import CORPS_SANS_ORS, ORS_CORPS, calc_ors
from bpaye.point import POINT
from bpaye.reclassement import DATE_PPCR, reclasse
from bpaye.temps_partiel import fraction_remuneration
from bpaye.utils import add_date_round, date_de, lit_toml, truncate, veille
from bpaye.vacances import VACANCES, ZONE_PAR_DEFAUT

__all__ = [
    "PSC_DECLAREE",
    "Fonctionnaire",
    "anciennete_conservee",
    "charge_agent",
    "charge_dossier",
    "echelon_d_accueil",
    "load_agent",
]

# Ce que [[psc]] d'agent.toml déclare et que le barème ne peut connaître : le coût de
# l'option santé choisie (sa participation vient du barème), l'adhésion à la prévoyance
# (1 ou 0, idem), et l'ancienne mutuelle précomptée sur la paie avant mai 2026.
PSC_DECLAREE = ("cout_option", "prevoyance", "mutuelle_adherent", "mutuelle_enfants")


class Fonctionnaire:
    """Un agent : sa situation (agent.toml) et sa carrière (carriere.toml), chacune lue par
    sa méthode, load_agent et load_carriere, dans cet ordre ou dans l'autre."""

    def __init__(self) -> None:
        self.nom = ""
        self.date_depart: dt.date  # posée par load_carriere
        self.jour_anniversaire = 1
        self.echelon: Temporal[int] = Temporal()
        self.anciennete: Temporal[float] = Temporal()
        self.grille: Temporal[Grille] = Temporal()
        self.point = POINT
        self.ors: Temporal[int] = Temporal()
        self.enfants: Temporal[int] = Temporal()
        self.vs: Temporal[float] = Temporal()
        # Les Temporal remplis par défaut (complete_par_defaut), qu'agent.toml remplace.
        self._par_defaut: set[int] = set()
        self.residence: Temporal[int] = Temporal()
        self.detachement: Temporal[bool] = Temporal()
        # Indemnité de fonction d'un détachement à la Défense : montant annuel individuel,
        # fixé par décision du ministre (décret 2003-745, art. 2), déclaré dans carriere.toml.
        self.indemnite_detachement: Temporal[float | None] = Temporal()
        self.frais_transport = Fixe()
        self.fmd_niveau: Temporal[int] = Temporal()
        self.effectif: Temporal[int] = Temporal()
        self.ic_csg: Temporal[float] | None = (
            None  # indemnité compensatrice de CSG propre à l'agent (agent.toml)
        )
        self.taux_pas = Taux(dt.date(2001, 1, 1), 0)  # prélèvement à la source (agent.toml)
        # Options et prévoyance de la PSC, ancienne mutuelle précomptée : montants mensuels
        # propres au contrat de l'agent (agent.toml, [[psc]]), par clé de PSC_DECLAREE.
        self.psc: Temporal[dict[str, float]] = Temporal()
        # Retards habituels de la paie (academies.toml), puis ceux de l'agent (agent.toml).
        self.academie: Temporal[str] = Temporal()
        self.retards_declares: list[Retard] = []
        self.siret: str | None = None  # du gestionnaire (agent.toml) : trie les bulletins PDF
        # Ses employeurs, par dates (agent.toml, [[employeur]]) : désignent, parmi les
        # bulletins d'un mois, celui qui se compare au calcul (employeurs.py).
        self.employeurs: Temporal[Employeur] = Temporal()
        self.zone_vacances = ZONE_PAR_DEFAUT  # celle du lycée d'affectation, pour les colles
        self.colles_prevues: dict[int, CollesPrevues] = {}  # par année de rentrée
        self.colles_externes: dict[int, list[CollesExternes]] = {}  # idem
        self.noms_grille: Temporal[str] = (
            Temporal()
        )  # nom de la grille (GRILLE_AGCN…), pour les reclassements
        self.corps: Temporal[str] = Temporal()  # « Agrégé », « Certifié », « PE »… : ORS, ISOE ou ISAE, HSA
        self.cpge: Temporal[bool] = Temporal()  # service en CPGE à la rentrée : ORS, IFP, base des HSA
        self.education_prioritaire: Temporal[str | None] = (
            Temporal()
        )  # « REP », « REP+ » ou None, par rentrée
        self.professeur_principal: Temporal[str | None] = (
            Temporal()
        )  # niveau de la classe, ou None, par rentrée
        self.quotite: Temporal[float] = Temporal()  # service / temps complet, par rentrée (1.0)
        self.surcotisation: Temporal[bool | str] = Temporal()  # retenue sur un temps plein (L11 bis)
        self.nbi: Temporal[int] = Temporal()  # points de NBI, par rentrée
        self.pacte: Temporal[float] = Temporal()  # parts fonctionnelles (Pacte), par rentrée
        self.specialite: Temporal[str | None] = Temporal()  # PsyEN : « EDA » ou « EDO »
        self.documentaliste: Temporal[bool] = Temporal()  # professeur documentaliste, par rentrée
        self.direction_ecole: Temporal[int] = Temporal()  # classes de l'école dirigée, 0 sinon

    def __str__(self) -> str:
        s = f"{self.nom}"
        s += f"\n* enfants\n{self.enfants}"
        s += f"\n* Échelons\n{self.echelon}"
        s += f"\n* ORS\n{self.ors}"
        s += f"\n* VS\n{self.vs}"
        return s

    def __repr__(self) -> str:
        return self.__str__()

    def update_detachement(
        self, date: dt.date, detachement: bool, indemnite_fonction: float | None = None
    ) -> None:
        """``indemnite_fonction`` : le montant annuel de l'indemnité de fonction d'un
        détachement à la Défense, celui de la décision individuelle du ministre."""
        assert isinstance(detachement, bool)
        self.detachement.append(date, detachement)
        self.indemnite_detachement.append(date, indemnite_fonction)

    def update_transport(self, date: dt.date, abonnement_annuel: float) -> None:
        self.frais_transport.append(date, annuel=abonnement_annuel)

    def is_detache(self, date: dt.date) -> bool:
        return self.detachement(date)

    def update_ors(self, year: int, annee: int, eff: int, type_classe: str = "sciences") -> None:
        """ORS d'un service en CPGE, d'après l'année de la classe, son type et son effectif."""
        ors = calc_ors(eff, annee, type_classe=type_classe)
        self.ors.append(dt.date(year, 9, 1), ors)
        self.effectif.append(dt.date(year, 9, 1), eff)

    def complete_par_defaut(self) -> None:
        """Ce que ni carriere.toml ni agent.toml ne donnent, à la date de départ : pas de
        détachement, d'enfant, de transport ni de forfait mobilités, une zone de résidence
        à 0 % (zone 3).

        Un enfant, un abonnement ou un forfait déclaré plus tard ne vaut qu'à partir de sa
        date : avant, l'agent n'en a pas (sans quoi un Temporal rendrait la première valeur
        déclarée, et le SFT d'un enfant né en 2009 serait payé dès 2006). La zone de
        résidence déclarée, elle, garde la main depuis le départ : rien ne dit où vivait
        l'agent avant."""
        jour = self.date_depart
        # Des Temporal de types différents : détachement, nombre d'enfants, niveau, zone.
        defauts: tuple[tuple[Temporal[Any], object], ...] = (
            (self.detachement, False),
            (self.enfants, 0),
            (self.fmd_niveau, 0),
            (self.residence, 3),
            (self.quotite, 1.0),
            (self.surcotisation, False),
            (self.nbi, 0),
            (self.pacte, 0.0),
            (self.specialite, None),
            (self.documentaliste, False),
            (self.direction_ecole, 0),
        )
        absents_avant_declaration = (id(self.detachement), id(self.enfants), id(self.fmd_niveau))
        for temporal, defaut in defauts:
            if not len(temporal):
                temporal.append(jour, defaut)
                self._par_defaut.add(id(temporal))
            elif id(temporal) in absents_avant_declaration and temporal.values[0][0] > jour:
                temporal.append(jour, defaut)
        if not len(self.frais_transport):
            self.frais_transport.append(jour, annuel=0.0)
            self._par_defaut.add(id(self.frais_transport))
        elif self.frais_transport.values[0][0] > jour:
            self.frais_transport.append(jour, annuel=0.0)

    def _declare(self, temporal: Temporal[Any]) -> None:
        """Avant d'y écrire une donnée d'agent.toml, efface la valeur par défaut qu'y a mise
        complete_par_defaut : la donnée déclarée prend sa place, même à la date de départ."""
        if id(temporal) in self._par_defaut:
            temporal.values.clear()
            self._par_defaut.discard(id(temporal))

    def _depart(
        self, nom: str, echelon: int, date: dt.date, grille: Temporal[Grille], anciennete: float
    ) -> None:
        """L'entrée dans la carrière ([depart] de carriere.toml), puis les avancements à
        l'ancienneté qui en découlent."""
        self.nom = nom
        self.date_depart = date
        self.jour_anniversaire = date.day
        self.echelon.append(date, echelon)
        self.anciennete.append(date, anciennete)
        self.grille = grille
        self.generate_avancement()

    def load_agent(self, path: str | Path) -> Self:
        """La situation de l'agent, lue dans agent.toml : taux du prélèvement à la source,
        enfants, zone de résidence, transport, FMD, indemnité compensatrice de CSG. Elle
        reste propre à cet agent : deux agents d'un même processus ne se mélangent pas."""
        cfg = lit_toml(path)
        self.siret = cfg.get("siret")
        for entry in cfg.get("employeur", []):
            self.employeurs.append(*lit_employeur(entry, "agent.toml [[employeur]]"))
        if self.siret and not len(self.employeurs):
            # Un seul SIRET, sans [[employeur]] : l'employeur de toute la carrière.
            self.employeurs.append(dt.date.min, Employeur("", (self.siret,)))
        for entry in cfg["ir"]["values"]:
            date = date_de(entry)
            if date != dt.date(2001, 1, 1):  # valeur initiale déjà présente
                self.taux_pas.append(date, entry["valeur"])
            else:
                self.taux_pas.update_value(date, entry["valeur"])
        if cfg.get("fmd"):
            self._declare(self.fmd_niveau)
        for entry in cfg.get("fmd", []):
            self.update_fmd_niveau(date_de(entry), entry["niveau"])
        if cfg.get("enfants"):
            self._declare(self.enfants)
        for e in cfg.get("enfants", []):
            self.update_enfants(date_de(e), e["nombre"])
        if cfg.get("residence"):
            self._declare(self.residence)
        for r in cfg.get("residence", []):
            self.update_residence(date_de(r), r["zone"])
        if cfg.get("transport"):
            self._declare(self.frais_transport)
        for t in cfg.get("transport", []):
            self.update_transport(date_de(t), t["abonnement_annuel"])
        for entry in cfg.get("academie", []):
            retards_academie(entry["nom"])  # refuse une académie inconnue
            self.academie.append(date_de(entry), entry["nom"])
        for entry in cfg.get("retards", []):
            self.retards_declares.append(lit_retard(entry, "agent.toml [[retards]]"))
        for entry in cfg.get("psc", []):
            montants = {cle: float(v) for cle, v in entry.items() if cle != "date"}
            if not isinstance(entry.get("prevoyance", False), bool):
                raise ValueError("[[psc]] : prevoyance attend true ou false")
            if inconnues := set(montants) - set(PSC_DECLAREE):
                raise ValueError(
                    f"[[psc]] : clés inconnues {sorted(inconnues)}, attendues {list(PSC_DECLAREE)}"
                )
            self.psc.append(date_de(entry), montants)
        if "ic_csg" in cfg:
            # Propre à l'agent : avant le premier montant déclaré, aucun n'est connu.
            self.ic_csg = depuis_section(cfg["ic_csg"])
            self.ic_csg.strict = True
        return self

    def retards(self, date: dt.date) -> dict[CleRetard, Retard]:
        """Les retards habituels de son académie à ``date`` (le défaut avant la première
        déclarée), et les siens, qui remplacent tous ceux de leurs rubriques."""
        nom = self.academie.declare_au(date, ACADEMIE_PAR_DEFAUT)
        return remplace(retards_academie(nom), self.retards_declares)

    def employeur(self, date: dt.date) -> Employeur | None:
        """L'employeur déclaré à ``date`` ; aucun avant le premier, ni sans déclaration."""
        return self.employeurs.declare_au(date, None)

    def psc_declaree(self, date: dt.date) -> dict[str, float]:
        """Les montants de [[psc]] en vigueur à ``date`` ; aucun avant la première entrée."""
        return self.psc.declare_au(date, {})

    def neutre_avant_rentrees(self) -> None:
        """Avant la première rentrée déclarée, le service ordinaire du corps : pas de CPGE, ni
        d'heures supplémentaires, d'éducation prioritaire, de classe en charge, de temps
        partiel, de NBI, de Pacte ni de direction d'école. Sans cela, un Temporal rendrait
        avant sa première date la valeur de la première rentrée : la REP ou les HSA de 2024
        seraient payées dès l'entrée dans le métier."""
        jour = self.date_depart
        corps = self.corps(jour)
        neutres: list[tuple[Temporal[Any], object]] = [
            (self.cpge, False),
            (self.vs, 0),
            (self.education_prioritaire, None),
            (self.professeur_principal, None),
            (self.quotite, 1.0),
            (self.surcotisation, False),
            (self.nbi, 0),
            (self.pacte, 0.0),
            (self.specialite, None),
            (self.documentaliste, False),
            (self.direction_ecole, 0),
        ]
        if corps in CORPS_SANS_ORS:
            neutres.append((self.ors, 0))
        elif corps in ORS_CORPS:
            neutres.append((self.ors, ORS_CORPS[corps]))
        for temporal, neutre in neutres:
            if len(temporal) and temporal.values[0][0] > jour:
                temporal.append(jour, neutre)

    def corps_au(self, date: dt.date) -> str:
        """Le corps à ``date`` : celui déclaré, à défaut celui de sa grille."""
        return self.corps.au(date, self.grille.value(date).corps)

    def en_cpge(self, date: dt.date) -> bool:
        """Vrai pour un service en CPGE à ``date`` (rentrées de carriere.toml)."""
        return bool(self.cpge.au(date, False))

    def points_nbi(self, date: dt.date) -> int:
        """Les points de NBI à ``date`` ; 0 sans NBI déclarée."""
        return self.nbi.au(date, 0)

    def quotite_au(self, date: dt.date) -> float:
        """La quotité de service à ``date`` ; 1 sans temps partiel déclaré."""
        return self.quotite.au(date, 1.0)

    def employeurs_declares(self) -> list[Employeur]:
        """Les employeurs déclarés ([[employeur]]), chacun une fois, dans l'ordre des dates."""
        connus: list[Employeur] = []
        for _, employeur in self.employeurs.values:
            if employeur not in connus:
                connus.append(employeur)
        return connus

    def fraction(self, date: dt.date) -> float:
        """La fraction de rémunération du mois : 1 à temps plein (temps_partiel.py)."""
        return fraction_remuneration(self.quotite_au(date))

    def reclasse(self, date: dt.date, echelon: int, anciennete: float) -> None:
        """À partir de ``date``, l'échelon ``echelon`` avec ``anciennete`` années déjà
        acquises ; les avancements suivants se recalculent sur la grille de ce jour."""
        self.echelon.remove_after(date)
        self.anciennete.remove_after(date)
        self.echelon.append(date, echelon)
        self.anciennete.append(date, anciennete)
        self.generate_avancement()

    def update_vs(self, year: int, hsa_vs: float) -> None:
        self.vs.append(dt.date(year, 9, 1), hsa_vs)

    def update_enfants(self, date: dt.date, n_enfants: int) -> None:
        self.enfants.append(date, n_enfants)

    def update_fmd_niveau(self, date: dt.date, niveau: int) -> None:
        """Enregistre le niveau FMD (1, 2 ou 3) à partir d'une date."""
        assert niveau in (1, 2, 3), f"Niveau FMD invalide : {niveau} (attendu 1, 2 ou 3)"
        self.fmd_niveau.append(date, niveau)

    def update_residence(self, date: dt.date, zone: int) -> None:
        self.residence.append(date, zone)

    def update_grille(
        self, date: dt.date, echelon_depart: int, nouvelle_grille: Temporal[Grille], anciennete: float = 0.0
    ) -> None:
        """Changement de corps : bascule sur nouvelle_grille à partir de date, à
        ``echelon_depart`` avec ``anciennete`` années déjà acquises (anciennete_conservee)."""
        grille_perso: Temporal[Grille] = Temporal()
        for d, g in self.grille.values:
            if d < date:
                grille_perso.append(d, g)
        grille_perso.append(date, nouvelle_grille.value(date))
        for d, g in nouvelle_grille.values:
            if d > date:
                grille_perso.append(d, g)
        self.grille = grille_perso
        # Les échelons pris avant le changement restent : remove_fromdate retirait aussi celui
        # en vigueur la veille (le 9e d'agrégé de 2021 disparaissait jusqu'en 2023).
        self.echelon.remove_after(date)
        self.anciennete.remove_after(date)
        self.echelon.append(date, echelon_depart)
        self.anciennete.append(date, anciennete)
        # L'ancienneté dans le nouveau corps part du changement : les échelons suivants
        # tombent à son jour (le 1er septembre 2023 → le 1er septembre 2025, rappel compris
        # sur les bulletins d'avril 2026), plus au jour anniversaire de l'entrée en carrière.
        self.jour_anniversaire = date.day
        self.generate_avancement()

    def nouvelle_rentree(
        self,
        year: int,
        annee: int | None = None,
        effectif: int | None = None,
        hsa_vs: float = 0,
        colles: dict[int, float] | None = None,
        colles_debut: dt.date | None = None,
        colles_fin: dt.date | None = None,
        colles_classe: float = 0.0,
        ors: int | None = None,
        type_classe: str = "sciences",
        education_prioritaire: str | None = None,
        professeur_principal: str | None = None,
        temps_partiel: float | None = None,
        heures_service: float | None = None,
        surcotisation: bool | str = False,
        nbi: int = 0,
        pacte: float = 0.0,
        specialite: str | None = None,
        documentaliste: bool = False,
        direction_ecole: int = 0,
    ) -> None:
        """La rentrée ``year``. Avec ``annee`` (1re ou 2e année de classe préparatoire) et
        ``effectif``, le service est en CPGE et son ORS en dépend ; sans eux, l'ORS est
        celle du corps (ors.ORS_CORPS). ``ors`` l'impose dans les deux cas.

        ``education_prioritaire`` (« REP » ou « REP+ ») et ``professeur_principal`` (un
        niveau de taux.toml [isoe_modulable]) valent pour l'année scolaire.

        Temps partiel : ``temps_partiel`` (quotité, 0.8 pour 80 %) ou ``heures_service``
        (heures hebdomadaires ; quotité = heures / ORS, code de l'éducation R911-7) ;
        ``surcotisation`` (True, ou temps_partiel.SURCOTISATION_ANTERIEURE pour un choix fait
        avant février 2024). ``nbi`` : points de nouvelle bonification indiciaire. ``pacte`` :
        nombre de parts fonctionnelles (une demi-part vaut 0.5).

        ``specialite`` : celle d'un PsyEN (« EDA » ou « EDO ») ; ``documentaliste`` : professeur
        documentaliste ; ``direction_ecole`` : nombre de classes de l'école que l'agent dirige.
        Un CPE ou un PsyEN n'a pas d'ORS d'enseignement : ni heures supplémentaires, ni
        ``heures_service``."""
        rentree = dt.date(year, 9, 1)
        en_cpge = annee is not None
        self.cpge.append(rentree, en_cpge)
        self.education_prioritaire.append(rentree, education_prioritaire)
        self.professeur_principal.append(rentree, professeur_principal)
        if ors is not None:
            self.ors.append(rentree, ors)
        elif annee is not None:  # en_cpge
            if effectif is None:
                raise ValueError(f"rentrée {year} : l'effectif de la classe est attendu avec annee")
            self.update_ors(year, annee=annee, eff=effectif, type_classe=type_classe)
        else:
            corps = self.corps(rentree)
            if corps in CORPS_SANS_ORS:
                self.ors.append(rentree, 0)
            elif corps not in ORS_CORPS:
                raise ValueError(f"rentrée {year} : pas d'ORS connue pour le corps {corps!r} (donner ors)")
            else:
                self.ors.append(rentree, ORS_CORPS[corps])
        self.update_vs(year, hsa_vs)
        if heures_service is not None:
            if not self.ors(rentree):
                raise ValueError(
                    f"rentrée {year} : heures_service sans ORS d'enseignement (donner temps_partiel)"
                )
            temps_partiel = heures_service / self.ors(rentree)
        self.quotite.append(rentree, 1.0 if temps_partiel is None else temps_partiel)
        self.surcotisation.append(rentree, surcotisation)
        self.nbi.append(rentree, nbi)
        self.pacte.append(rentree, pacte)
        self.specialite.append(rentree, specialite)
        self.documentaliste.append(rentree, documentaliste)
        self.direction_ecole.append(rentree, direction_ecole)
        if colles or colles_classe:
            self.prevoit_colles(year, colles or {}, colles_debut, colles_fin, colles_classe)

    def prevoit_colles(
        self,
        year: int,
        heures: dict[int, float],
        debut: dt.date | None,
        fin: dt.date | None,
        heures_classe: float = 0.0,
    ) -> None:
        """Colles prévues de la rentrée ``year`` : ``heures`` par semaine pour chaque
        code de colle (hsa.CODE), chaque semaine de colles du ``debut`` à la ``fin`` ;
        ``heures_classe``, le budget hebdomadaire de sa classe, dont le reliquat est payé
        en fin d'année (colles.inject_colles_prevues)."""
        _verifie_colles(year, heures, debut, fin)
        assert debut is not None and fin is not None  # vérifiés par _verifie_colles
        self.colles_prevues[year] = CollesPrevues(debut, fin, dict(heures), heures_classe)

    def prevoit_colles_externes(
        self,
        year: int,
        zone: str,
        heures: dict[int, float],
        debut: dt.date | None,
        fin: dt.date | None,
        etablissement: str = "",
    ) -> None:
        """Colles de la rentrée ``year`` dans un autre établissement, de la ``zone`` de
        vacances ``zone`` : payées à part du salaire (colles.CollesExternes)."""
        _verifie_colles(year, heures, debut, fin)
        assert debut is not None and fin is not None  # vérifiés par _verifie_colles
        if zone not in VACANCES:
            raise ValueError(
                f"rentrée {year} : zone de vacances inconnue {zone!r}, attendu {sorted(VACANCES)}"
            )
        externes = CollesExternes(zone, debut, fin, dict(heures), etablissement)
        self.colles_externes.setdefault(year, []).append(externes)

    def indice_detenu(self, date: dt.date) -> int:
        """L'indice majoré détenu le jour ``date`` : celui de l'échelon et de la grille de ce
        jour, sans le prorata d'un échelon pris en cours de mois (indice)."""
        return self.grille.value(date).indice(self.echelon(date))

    def changement_d_indice(self, date: dt.date) -> tuple[int, int, int] | None:
        """Pour un mois où un échelon est pris en cours de mois : (jours à l'ancien indice,
        ancien indice, nouvel indice) ; None sinon, et pour le premier échelon de la
        carrière, sans échelon d'avant."""
        d = self.echelon.date_trigger(date)
        if d is None or d.day == 1 or d <= self.echelon.values[0][0]:
            return None
        # L'échelon d'avant se lit dans la grille d'avant (indice_detenu) : un changement de
        # grade ou de corps change aussi de grille.
        return min(d.day - 1, 30), self.indice_detenu(veille(d)), self.indice_detenu(d)

    def indice(self, date: dt.date) -> float:
        """L'indice du mois de ``date``, quel qu'en soit le jour : au prorata des jours de
        l'ancien et du nouveau pour un échelon pris en cours de mois. Il s'affiche ; le
        traitement de ce mois, lui, proratise les deux traitements (point.traitement_indiciaire)."""
        changement = self.changement_d_indice(date)
        if changement is not None:
            jours, i_prec, i = changement
            return truncate(jours / 30 * i_prec + (30 - jours) / 30 * i, 2)
        return self.indice_detenu(date)

    def avancement(
        self,
        echelon: int,
        type_avancement: str | None = None,
        anciennete: float = 0,
        nouvelle_date: dt.date | None = None,
    ) -> None:
        assert type_avancement in ["A", "C", "GC", None]
        if type_avancement == "A":
            return
        prev_echelon = echelon - 1
        prev_date = self.echelon.value_todate(prev_echelon)
        ancienne_date = self.echelon.value_todate(echelon)
        if type_avancement in ("C", "GC"):
            grille = self.grille(prev_date)
            durees = grille.choix if type_avancement == "C" else grille.grandchoix
            assert durees is not None, f"{grille} : pas d'avancement {type_avancement}"
            duree = durees[prev_echelon - 1]
            assert duree is not None, f"{grille} : pas d'avancement {type_avancement} au {prev_echelon}e"
            delta = duree - self.anciennete(prev_date)
        else:
            delta = 0
        if nouvelle_date is None:
            nouvelle_date = add_date_round(prev_date, delta, self.jour_anniversaire)
        self.echelon.update_date_fromvalue(echelon, nouvelle_date)
        self.anciennete.update_date(ancienne_date, nouvelle_date)
        self.anciennete.update_value(nouvelle_date, anciennete)
        self.generate_avancement(start_echelon=echelon + 1)

    def generate_avancement(self, start_echelon: int | None = None) -> None:
        if start_echelon is None:
            e = self.echelon.value() + 1
        else:
            e = start_echelon
            # Les échelons suivants se recalculent : on les retire d'abord.
            start_date = self.echelon.value_todate(start_echelon)
            self.echelon.remove_fromdate(start_date)
            self.anciennete.remove_fromdate(start_date)
        prev_echelon = e - 1
        prev_date = self.echelon.value_todate(prev_echelon)
        grille = self.grille(prev_date)
        while e <= grille.lastechelon:
            an = self.grille(prev_date).anciennete[prev_echelon - 1]
            if an is None:
                break  # échelon sans avancement automatique (ex : CHSUP échelon 8/11)
            delta = an - self.anciennete(prev_date)
            nouvelle_date = add_date_round(prev_date, delta, self.jour_anniversaire)
            self.echelon.append(nouvelle_date, e)
            self.anciennete.append(nouvelle_date, 0)
            prev_echelon = e
            prev_date = nouvelle_date
            grille = self.grille(nouvelle_date)
            e += 1

    def load_carriere(self, path: str | Path, grilles_map: dict[str, Temporal[Grille]] | None = None) -> Self:
        """
        La carrière de l'agent, lue dans carriere.toml.

        Paramètres
        ----------
        path        : chemin vers le fichier TOML
        grilles_map : dict associant les noms de grille (str) aux objets Temporal
                      ex: {'GRILLE_AGCN': GRILLE_AGCN} ; par défaut, toutes celles de
                      grilles.toml

        Chaque [[rentrees]] peut prévoir ses colles, pour la paye à venir :

            colles        = { 161 = 4.0, 6 = 1.0 }  # heures par semaine, par code de colle
                                                    # (161, 6, 7, 8 ; 157, 1, 90 en chaire sup.)
            colles_debut  = 2025-09-22              # première semaine de colles
            colles_fin    = 2026-04-10              # au plus tard (20 semaines de colles)
            colles_classe = 7.0                     # heures par semaine du budget de sa classe,
                                                    # dont le reliquat est payé en fin d'année

        Ce sont les colles du lycée d'affectation, payées avec le salaire, dans sa zone de
        vacances ([depart] zone_vacances, C par défaut). Celles d'un autre établissement,
        payées à part, suivent la zone de cet établissement :

            [[rentrees.colles_externes]]
            etablissement = "…"                     # pour mémoire
            zone          = "B"
            colles        = { 1 = 2.0 }             # heures par semaine, au code déclaré là-bas
            colles_debut  = 2025-09-22
            colles_fin    = 2026-04-10

        Voir colles.inject_colles_prevues et colles.brut_colles_externes.
        """
        if grilles_map is None:
            from bpaye.grille import GRILLES

            grilles_map = GRILLES
        cfg = lit_toml(path)

        dep = cfg["depart"]
        grille = grilles_map[dep["grille"]]

        fonc = self
        fonc._depart(dep["nom"], dep["echelon"], date_de(dep), grille, dep["anciennete"])
        depart = date_de(dep)
        fonc.noms_grille.append(depart, dep["grille"])
        fonc.corps.append(depart, dep.get("corps", grille.value(depart).corps))
        fonc.zone_vacances = dep.get("zone_vacances", ZONE_PAR_DEFAUT)
        if fonc.zone_vacances not in VACANCES:
            raise ValueError(f"zone de vacances inconnue {fonc.zone_vacances!r}, attendu {sorted(VACANCES)}")

        for d in cfg.get("detachements", []):
            fonc.update_detachement(date_de(d), d["detache"], d.get("indemnite_fonction"))

        # Les avancements s'appliquent dans l'ordre chronologique, quel que soit leur ordre dans le
        # fichier : un choix de 2015 avant le reclassement de 2017, une accélération de 2020
        # après. La date d'un avancement d'échelon est celle où l'agent atteint l'échelon d'avant,
        # dans la carrière telle qu'elle est à ce moment : elle se recalcule à chaque étape.
        def date_avancement(av: dict[str, Any]) -> dt.date:
            if av["type"] == "PPCR":
                return DATE_PPCR
            if av["type"] == "reclassement":
                return date_de(av)
            try:
                return fonc.echelon.value_todate(av["echelon"] - 1)
            except ValueError:
                return dt.date.max  # échelon d'avant jamais atteint : en dernier

        restants = list(cfg.get("avancements", []))
        while restants:
            av = min(restants, key=date_avancement)
            restants.remove(av)
            t = av["type"]
            if t == "PPCR":
                reclasse(fonc, DATE_PPCR)
            elif t == "reclassement":
                reclasse(fonc, date_de(av))
            else:
                fonc.avancement(av["echelon"], t)

        for cc in cfg.get("changements_corps", []):
            jour = date_de(cc)
            nouvelle = grilles_map[cc["grille"]]
            echelon = cc.get("echelon_depart")
            if echelon is None:
                echelon = echelon_d_accueil(nouvelle.value(jour), fonc.indice(veille(jour)))
            # Un changement de grade dans une grille partagée (hors classe d'un PE) garde le corps ;
            # un changement de grille d'un autre corps (agrégation, chaire supérieure) le change.
            la_veille = veille(jour)
            meme_famille = nouvelle.value(jour).corps == fonc.grille.value(la_veille).corps
            corps = cc.get("corps", fonc.corps(la_veille) if meme_famille else nouvelle.value(jour).corps)
            anciennete = anciennete_conservee(fonc, jour, nouvelle.value(jour), echelon)
            fonc.update_grille(jour, echelon, nouvelle, anciennete)
            fonc.noms_grille.append(jour, cc["grille"])
            fonc.corps.append(jour, corps)

        for r in cfg.get("rentrees", []):
            fonc.nouvelle_rentree(
                year=r["year"],
                annee=r.get("annee"),
                effectif=r.get("effectif"),
                hsa_vs=r.get("hsa_vs", 0),
                ors=r.get("ors"),
                type_classe=r.get("type_classe", "sciences"),
                education_prioritaire=r.get("education_prioritaire"),
                professeur_principal=r.get("professeur_principal"),
                temps_partiel=r.get("temps_partiel"),
                heures_service=r.get("heures_service"),
                surcotisation=r.get("surcotisation", False),
                nbi=r.get("nbi", 0),
                pacte=r.get("pacte", 0.0),
                specialite=r.get("specialite"),
                documentaliste=r.get("documentaliste", False),
                direction_ecole=r.get("direction_ecole", 0),
                colles={int(code): heures for code, heures in r.get("colles", {}).items()},
                colles_debut=r.get("colles_debut"),
                colles_fin=r.get("colles_fin"),
                colles_classe=r.get("colles_classe", 0.0),
            )
            for ext in r.get("colles_externes", []):
                fonc.prevoit_colles_externes(
                    r["year"],
                    zone=ext["zone"],
                    heures={int(code): heures for code, heures in ext["colles"].items()},
                    debut=ext.get("colles_debut"),
                    fin=ext.get("colles_fin"),
                    etablissement=ext.get("etablissement", ""),
                )

        fonc.neutre_avant_rentrees()
        fonc.complete_par_defaut()
        return fonc


def load_agent(path: str | Path) -> Fonctionnaire:
    """Un agent nouveau, sa situation lue dans agent.toml ; sa carrière se lit ensuite
    par agent.load_carriere(chemin)."""
    return Fonctionnaire().load_agent(path)


def charge_agent(agent: str | Path, carriere: str | Path) -> Fonctionnaire:
    """Un agent, sa situation lue dans ``agent`` (agent.toml) et sa carrière dans
    ``carriere`` (carriere.toml)."""
    return load_agent(agent).load_carriere(carriere)


def charge_dossier(dossier: str | Path) -> Fonctionnaire:
    """Un agent dont agent.toml et carriere.toml sont dans ``dossier``."""
    return charge_agent(Path(dossier) / "agent.toml", Path(dossier) / "carriere.toml")


def anciennete_conservee(fonc: Fonctionnaire, jour: dt.date, accueil: Grille, echelon: int) -> float:
    """L'ancienneté que l'agent garde en changeant de corps le ``jour``, classé à
    ``echelon`` de la grille ``accueil``.

    Chaire supérieure (décret 68-503, art. 5, inchangé depuis 1967) : l'ancienneté acquise
    dans l'ancien échelon est conservée, dans la limite de la durée de l'échelon d'accueil,
    si la nomination procure un gain d'indice inférieur à celui d'une promotion d'échelon
    dans l'ancien grade, ou si l'agrégé était au 11e échelon ; sinon, aucune.
    https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000868842/2023-09-01/
    Pour un autre corps, la règle de classement de son statut n'est pas relue : aucune
    ancienneté conservée, comme jusqu'ici (supposé)."""
    if accueil.corps != "Chaire Supérieure":
        return 0.0
    la_veille = veille(jour)
    ancienne, e, im = fonc.grille(la_veille), fonc.echelon(la_veille), fonc.indice(la_veille)
    entree = max(d for d, v in fonc.echelon.values if v == e and d <= la_veille)
    acquise = fonc.anciennete(entree) + (jour - entree).days / 365.25
    gain_promotion = ancienne.indice(e + 1) - im if e < len(ancienne) else 0
    au_onzieme_agrege = ancienne.corps == "Agrégé" and e == 11
    if accueil.indice(echelon) - im >= gain_promotion and not au_onzieme_agrege:
        return 0.0
    duree = accueil.anciennete[echelon - 1]
    return round(min(acquise, duree), 4) if duree is not None else round(acquise, 4)


def echelon_d_accueil(grille: Grille, indice: float) -> int:
    """Le premier échelon de ``grille`` dont l'indice égale ou dépasse ``indice`` : la
    règle de classement des statuts lors d'une promotion de corps ou de grade (« à
    l'échelon comportant un traitement égal ou immédiatement supérieur », décret 68-503,
    art. 5, pour les chaires supérieures)."""
    for echelon, im in enumerate(grille.indices, start=1):
        if im >= indice:
            return echelon
    # Aucun échelon n'atteint l'ancien indice : le texte prévoit alors un maintien à titre
    # personnel, que bpaye ne modélise pas.
    raise ValueError(
        f"Aucun échelon de la grille n'atteint l'indice {indice} (indice personnel non modélisé)"
    )


def _verifie_colles(year: int, heures: dict[int, float], debut: dt.date | None, fin: dt.date | None) -> None:
    if debut is None or fin is None or fin < debut:
        raise ValueError(f"rentrée {year} : colles_debut et colles_fin attendus, dans l'ordre")
    inconnus = [code for code in heures if code not in CODE]
    if inconnus:
        raise ValueError(f"rentrée {year} : codes de colle inconnus {inconnus}, attendus {list(CODE)}")
