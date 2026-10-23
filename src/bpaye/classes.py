"""Les briques du calcul : valeurs datées, lignes de bulletin, listes de lignes et leurs sommes.

Temporal garde l'historique d'une valeur (taux, montant, échelon, grille) : la valeur
à une date est la dernière dont la date d'effet la précède. C'est ce qui permet de
rejouer une carrière entière, chaque bulletin prenant les règles de son mois. Fixe
range les montants en mensuel (un montant annuel est divisé par 12 à l'entrée),
AnnuelPonctuel les verse en une fois, Taux les applique à une assiette.

Un taux reste linéaire : ce qui dépend de l'assiette (l'abattement de CSG sous un seuil)
et les arrondis se calculent dans chaque fonction de calcul, pas dans la ligne.
"""

import datetime as dt
import warnings
from collections.abc import Iterator
from typing import Any, Generic, Self, TypeVar

import bpaye.format as fmt
from bpaye.codes import (
    COLLES,
    HSA,
    HSE,
    HSE_ACCOMPAGNEMENT,
    HSE_REMPLACEMENT,
    HSE_REUSSITE,
    HSE_SUPPLEANCES,
    MAJORATION_HSA,
    PACTE_ISAE,
    PACTE_ISOE,
    SURVEILLANCE,
    TPP,
)
from bpaye.utils import last_day_month, next_month

__all__ = [
    "AnnuelPonctuel",
    "Fixe",
    "Ligne",
    "ListeLignes",
    "Selection",
    "Somme",
    "Taux",
    "Temporal",
]

# La valeur gardée par un Temporal : un taux, un échelon, une grille, un nom de corps…
T = TypeVar("T")
D = TypeVar("D")  # le défaut d'une valeur non déclarée (Temporal.au)


class Temporal(Generic[T]):
    """Garde en mémoire l'évolution des taux et valeurs"""

    def __init__(self) -> None:
        self.values: list[tuple[dt.date, T]] = []
        # Un barème (taux.toml) refuse une date antérieure à sa première valeur : rien n'y
        # est vérifié (MANQUANT). Une donnée de l'agent (échelon, enfants, abonnement…)
        # prend sa première valeur, comme le fait la carrière avant son premier événement.
        self.strict = False

    def append(self, date: dt.date, value: T) -> None:
        self.values.append((date, value))
        self.sort()

    def sort(self) -> None:
        self.values.sort(key=lambda couple: couple[0])

    def __len__(self) -> int:
        return len(self.values)

    def __str__(self) -> str:
        s = ""
        for d, v in self.values:
            s += f"{d} : {v}\n"
        return s

    def __repr__(self) -> str:
        return self.__str__()

    def __call__(self, date: dt.date | None = None) -> T:
        return self.value(date)

    def au(self, date: dt.date, defaut: D) -> T | D:
        """La valeur à ``date`` ; ``defaut`` si rien n'est déclaré."""
        return self.value(date) if self.values else defaut

    def declare_au(self, date: dt.date, defaut: D) -> T | D:
        """La valeur à ``date`` ; ``defaut`` si rien n'est déclaré, ou avant la première date
        déclarée (une donnée de l'agent qui n'a pas d'effet avant d'être déclarée)."""
        return self.value(date) if self.values and date >= self.values[0][0] else defaut

    def date_toindice(self, date: dt.date | None) -> int:
        if date is None:
            return len(self) - 1
        if len(self) == 0:
            raise ValueError("Aucune donnée n'a été enregistrée dans la structure")
        for i, (d, _) in enumerate(self.values):
            if d > date:
                if i == 0:
                    if self.strict:
                        raise ValueError(
                            f"Pas de valeur vérifiée au {date}, la première date du {d} (MANQUANT)"
                        )
                    return 0
                return i - 1
        return len(self) - 1

    def value_toindice(self, value: T) -> int:
        """L'indice de la dernière occurrence de ``value``, comme value_todate : après un
        changement de corps, un même numéro d'échelon revient."""
        for i in range(len(self.values) - 1, -1, -1):
            if self.values[i][1] == value:
                return i
        raise ValueError(f"Valeur ({value}) non trouvée dans les données")

    def value_todate(self, value: T) -> dt.date:
        """Retourne la date la plus récente associée à value (utile après changement de corps)."""
        result = None
        for d, v in self.values:
            if v == value:
                result = d
        if result is not None:
            return result
        raise ValueError(f"Valeur ({value}) non trouvée dans les données")

    def date_trigger(self, date: dt.date) -> dt.date | None:
        debut, suivant = date.replace(day=1), next_month(date)
        for d, _ in self.values:
            if debut <= d < suivant:
                return d
        return None

    def date(self, date: dt.date | None = None) -> dt.date:
        i = self.date_toindice(date)
        return self.values[i][0]

    def value(self, date: dt.date | None = None) -> T:
        i = self.date_toindice(date)
        return self.values[i][1]

    def value_prec(self, date: dt.date | None = None) -> T:
        i = self.date_toindice(date)
        if i == 0:
            raise ValueError(f"Pas de données précédentes à {date}")
        return self.values[i - 1][1]

    def update_date(self, olddate: dt.date, newdate: dt.date) -> None:
        i = self.date_toindice(olddate)
        value = self.values[i][1]
        self.values[i] = (newdate, value)
        self.sort()

    def update_value(self, date: dt.date, newvalue: T) -> None:
        i = self.date_toindice(date)
        self.values[i] = (date, newvalue)

    def update_date_fromvalue(self, value: T, newdate: dt.date) -> None:
        i = self.value_toindice(value)
        self.values[i] = (newdate, value)
        self.sort()

    def remove_fromdate(self, date: dt.date) -> None:
        i = self.date_toindice(date)
        for _ in range(len(self) - i):
            del self.values[i]

    def remove_after(self, date: dt.date) -> None:
        """Retire les valeurs qui prennent effet le ``date`` ou après ; celle en vigueur
        la veille reste."""
        self.values = [(d, v) for d, v in self.values if d < date]

    def changed_trigger(self, date: dt.date) -> bool:
        data_date = self.date(date)
        suivant = next_month(data_date)
        dernier = last_day_month(suivant)
        next_month_same_dataday = suivant.replace(day=min(data_date.day, dernier.day))
        return data_date <= date < next_month_same_dataday

    def previous_value(self, date: dt.date) -> T | None:
        i = self.date_toindice(date)
        if i == 0:
            return None
        return self.values[i - 1][1]

    def previous_date(self, date: dt.date) -> dt.date | None:
        i = self.date_toindice(date)
        if i == 0:
            return None
        return self.values[i - 1][0]


class Fixe(Temporal[float]):
    """mensuel par défaut"""

    def __init__(
        self, date: dt.date | None = None, mensuel: float | None = None, annuel: float | None = None
    ) -> None:
        Temporal.__init__(self)
        if date is not None:
            self.append(date, mensuel=mensuel, annuel=annuel)

    def append(  # type: ignore[override]
        self, date: dt.date, mensuel: float | None = None, annuel: float | None = None
    ) -> None:
        assert annuel is not None or mensuel is not None
        if annuel is None:
            assert mensuel is not None
            Temporal.append(self, date, mensuel)
        else:
            assert mensuel is None
            Temporal.append(self, date, annuel / 12)

    def value_annuel(self, date: dt.date | None = None) -> float:
        return self(date) * 12


class AnnuelPonctuel(Temporal[float]):
    """Montant annuel versé en une seule fois, le mois indiqué dans mois_versement.

    Contrairement à Fixe(unite="annuel") qui divise par 12, ici le montant
    complet est renvoyé uniquement le mois de versement et 0 les autres mois.

    Paramètres TOML :
        type            = "AnnuelPonctuel"
        mois_versement  = 3              # entier 1-12 (ex. mars = 3)
        values          = [ { date = AAAA-MM-JJ, valeur = X }, ... ]

    Utilisation :
        obj(date)          → montant si date.month == mois_versement, sinon 0
        obj.montant(date)  → montant brut quelque soit le mois (utile pour affichage)
    """

    def __init__(self, mois_versement: int = 1) -> None:
        Temporal.__init__(self)
        self.mois_versement = mois_versement

    def append(self, date: dt.date, valeur: float) -> None:
        Temporal.append(self, date, valeur)

    def montant(self, date: dt.date | None = None) -> float:
        """Retourne le montant annuel sans condition de mois."""
        return self.value(date)

    def __call__(self, date: dt.date | None = None) -> float:
        """Retourne le montant si on est dans le mois de versement, sinon 0."""
        if date is not None and date.month != self.mois_versement:
            return 0.0
        return self.value(date)

    def value_annuel(self, date: dt.date | None = None) -> float:
        return self.value(date)


class Taux(Temporal[float]):
    def __init__(self, date: dt.date | None = None, taux: float | None = None) -> None:
        Temporal.__init__(self)
        if date is not None:
            assert taux is not None
            self.append(date, taux)

    def taux(self, brut: float, date: dt.date | None = None) -> float:
        return self(date) * brut


class Ligne:
    def __init__(
        self,
        valeur: float,
        lib: str = "",
        imposable: bool = False,
        code: int = 0,
        patronal: bool = False,
        classe: str = "BRUT",
        sommable: bool = False,
    ) -> None:
        self.valeur = valeur
        self.valeur_reel: float | None = None  # montant réel issu du bulletin PDF
        # Le montant avant arrondi, quand la paie arrondit une somme de lignes depuis leurs
        # montants exacts (des HSA de deux mois rappelées ensemble : hsa.py).
        self.exacte: float | None = None
        self.lib = lib
        self.code = code
        self.patronal = patronal
        self.imposable = imposable
        self.type = classe
        assert self.type in ["BRUT", "PC", "CHARGE", "INDEM", "RAFP", "IMPOT"]
        self.sommable = sommable

    def avec(self, **changements: Any) -> Self:
        """Une copie de la ligne, ``changements`` appliqués : ``ligne.avec(valeur=-ligne.valeur)``."""
        ligne = type(self)(
            self.valeur, self.lib, self.imposable, self.code, self.patronal, self.type, self.sommable
        )
        ligne.valeur_reel = self.valeur_reel
        ligne.exacte = self.exacte
        for nom, valeur in changements.items():
            if not hasattr(ligne, nom):
                raise AttributeError(f"Ligne n'a pas d'attribut {nom!r}")
            setattr(ligne, nom, valeur)
        return ligne

    def copy(self) -> Self:
        return self.avec()

    def __str__(self) -> str:
        wl = fmt.LIB_WIDTH
        fl = fmt.LIB_FORMAT
        wc = fmt.MT_WIDTH
        fc = fmt.MT_FORMAT
        s = f"[{self.code}] " + fl.format(self.lib[:wl]) + ":"
        if self.type in ["PC", "CHARGE", "RAFP", "IMPOT"]:
            s += " " * wc
        s += fc.format(self.valeur)
        return s

    def __repr__(self) -> str:
        return self.__str__()


# ═══════════════════════════════════════════════════════════════════════════════
# Somme – résultat de ListeLignes.somme()
# ═══════════════════════════════════════════════════════════════════════════════


class Somme:
    """Agrégat de montants calculé et réel sur une liste de lignes.

    Attributs
    ---------
    calcul : float   – somme des ``Ligne.valeur`` (calcul de bpaye)
    reel   : float   – somme des ``Ligne.valeur_reel`` (bulletins PDF)
                       Lève ValueError si aucune valeur réelle n'est disponible.
                       Avertit si des mois n'ont pas de bulletin PDF.
    """

    def __init__(
        self,
        calcul: float,
        reel: float | None,
        months_with_pdf: int = 0,
        months_total: int = 0,
        label: str = "",
    ) -> None:
        self._calcul = calcul
        self._reel = reel
        self._months_with_pdf = months_with_pdf
        self._months_total = months_total
        self._label = label

    @property
    def calcul(self) -> float:
        return round(self._calcul, 2)

    @property
    def reel(self) -> float:
        if self._reel is None:
            raise ValueError(
                f"Pas de données PDF disponibles pour {self._label!r}. "
                "Vérifiez que bull_dir est défini et que les PDF existent."
            )
        if self._months_total > 0 and self._months_with_pdf < self._months_total:
            warnings.warn(
                f"Données PDF incomplètes : {self._months_with_pdf}/{self._months_total} "
                f"bulletins trouvés pour {self._label!r}. "
                f"La valeur réelle ({self._reel:.2f} €) est partielle.",
                stacklevel=3,
            )
        return round(self._reel, 2)

    def reel_or(self, default: float = 0.0) -> float:
        """Retourne la valeur réelle, ou ``default`` si aucun PDF n'est disponible."""
        try:
            return self.reel
        except ValueError:
            return default

    def __add__(self, other: Self) -> Self:
        reel = None
        if self._reel is not None and other._reel is not None:
            reel = self._reel + other._reel
        elif self._reel is not None:
            reel = self._reel
        elif other._reel is not None:
            reel = other._reel
        return type(self)(
            calcul=self._calcul + other._calcul,
            reel=reel,
            months_with_pdf=self._months_with_pdf + other._months_with_pdf,
            months_total=self._months_total + other._months_total,
            label=f"{self._label}+{other._label}",
        )

    def __radd__(self, other: Self | int) -> Self:
        if other == 0:
            return self
        assert not isinstance(other, int), "seul 0 s'ajoute à une Somme (sum())"
        return self.__add__(other)

    def __neg__(self) -> Self:
        reel = -self._reel if self._reel is not None else None
        return type(self)(-self._calcul, reel, self._months_with_pdf, self._months_total, self._label)

    def __sub__(self, other: Self) -> Self:
        return self.__add__(-other)

    def __repr__(self) -> str:
        reel_s = f"{self._reel:.2f} €" if self._reel is not None else "—"
        calcul_s = f"{self._calcul:.2f} €"
        label = f" [{self._label}]" if self._label else ""
        mois = (
            f" ({self._months_with_pdf}/{self._months_total} mois PDF)"
            if self._months_total > 0 and self._months_with_pdf < self._months_total
            else ""
        )
        return f"Somme{label} réel={reel_s}  calcul={calcul_s}{mois}"


# ═══════════════════════════════════════════════════════════════════════════════
# ListeLignes – classe parente de Bulletin et Selection
# ═══════════════════════════════════════════════════════════════════════════════


class ListeLignes:
    """Liste de Ligne avec méthodes de recherche et de calcul."""

    lignes: list[Ligne]  # défini par les sous-classes (__init__)

    def __iter__(self) -> Iterator[Ligne]:
        return iter(self.lignes)

    def __len__(self) -> int:
        return len(self.lignes)

    def __getitem__(self, i: int) -> Ligne:
        return self.lignes[i]

    # ── Recherche ─────────────────────────────────────────────────────────────

    def get_fromcode(self, code: int) -> Ligne:
        """Retourne la première Ligne avec ce code (lève ValueError si absent)."""
        for ligne in self:
            if ligne.code == code:
                return ligne
        raise ValueError(f"Code {code} non trouvé")

    def get_all_fromcode(self, code: int) -> list[Ligne]:
        """Retourne toutes les Lignes avec ce code (liste vide si absent)."""
        return [ligne for ligne in self if ligne.code == code]

    def get_fromcode_sommable(self, code: int) -> Ligne | None:
        """Retourne la première Ligne sommable avec ce code (None si absente)."""
        for ligne in self:
            if ligne.code == code and ligne.sommable:
                return ligne
        return None

    def getindex_fromcode(self, code: int) -> int:
        for i, ligne in enumerate(self):
            if ligne.code == code:
                return i
        raise ValueError(f"Code {code} non trouvé")

    def __call__(self, code: int) -> Ligne:
        return self.lignes[self.getindex_fromcode(code)]

    def sort(self) -> None:
        self.lignes.sort(key=lambda ligne: ligne.code)

    # ── Agrégats (sur valeur = calcul) ────────────────────────────────────────

    def total(self, *codes: int) -> float:
        """Le total calculé des lignes de ces codes (somme : calcul et réel)."""
        return sum(ligne.valeur for ligne in self if ligne.code in codes)

    @property
    def brut(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.type == "BRUT")

    @property
    def pc(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.type == "PC")

    @property
    def charges(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.type == "CHARGE")

    @property
    def ind(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.type == "INDEM")

    @property
    def rafp(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.type == "RAFP")

    @property
    def tpp(self) -> float:
        return self.total(TPP)

    @property
    def imposable(self) -> float:
        return sum(ligne.valeur for ligne in self if ligne.imposable)

    @property
    def net(self) -> float:
        return sum(ligne.valeur for ligne in self)

    @property
    def net_imposable(self) -> float:
        return self.net - self.imposable

    @property
    def revenus(self) -> float:
        return self.brut + self.ind

    @property
    def hs_brut(self) -> float:
        """Montant brut des heures sup. (HSA, majo 1re HSA, colles HSI, HSE, HSE de suppléance),
        et des parts fonctionnelles du Pacte, qui ont le même régime : réduction de
        cotisations et exonération d'impôt (décret 2019-133, art. 1, 29°). Les heures, elles,
        le sont par le 2° du même article : toute heure supplémentaire du décret 50-1253
        faite dans l'activité principale, quel que soit son code de paie
        (https://www.legifrance.gouv.fr/loda/id/JORFTEXT000038168767). D'où 201241, 201717
        et 201300. Seul indice contraire pour 201300 : le référentiel INGRES V25.00.06 de la
        DGFiP la marque R_FOR_IMPOSA = 1, sens déduit des heures exonérées qui portent 0
        (feuille Annexes_14_15, ligne 1281, https://www.amue.fr/fileadmin/amue/ressources-humaines/2026/tour_de_web_special_paye/INGRES_C_V25.00.06_F25.00.00_P00_BG_ANNEXES14_ET_15.xlsx),
        et aucune annexe 14 A, 14 B ou 14 C de 2026 ne la classe. Si la paie ne l'exonère
        pas, l'écart le montre."""
        codes = (
            HSA,
            COLLES,
            HSE,
            SURVEILLANCE,
            HSE_SUPPLEANCES,
            MAJORATION_HSA,
            HSE_REMPLACEMENT,
            HSE_ACCOMPAGNEMENT,
            HSE_REUSSITE,
            PACTE_ISOE,
            PACTE_ISAE,
        )
        return self.total(*codes)

    # ── Somme calcul + reel ───────────────────────────────────────────────────

    def somme(self, code: int | str | None = None) -> Somme:
        """Agrège valeur (calcul) et valeur_reel (PDF) des lignes, celles de ``code`` seulement
        s'il est donné."""
        lignes = self.lignes if code is None else [ligne for ligne in self.lignes if ligne.code == int(code)]
        calcul = round(sum(ligne.valeur for ligne in lignes), 2)
        reel_vals = [ligne.valeur_reel for ligne in lignes if ligne.valeur_reel is not None]
        reel = round(sum(reel_vals), 2) if reel_vals else None
        return Somme(calcul=calcul, reel=reel)


# ═══════════════════════════════════════════════════════════════════════════════
# Selection – liste plate de Lignes sur une période, issue de P.select()
# ═══════════════════════════════════════════════════════════════════════════════


class Selection(ListeLignes):
    """Les lignes d'une période de bulletins (produit de Paye.select()).

    Chaque Ligne porte son montant calculé (``valeur``) et, si le bulletin PDF a pu être
    lu, son montant réel (``valeur_reel``) : ``P.select("558000", 2025).somme()`` donne
    l'un et l'autre (``.calcul``, ``.reel``).
    """

    def __init__(self) -> None:
        self.lignes: list[Ligne] = []
        self._months_total = 0
        self._months_with_pdf = 0
        self._label = ""

    def somme(self, code: int | str | None = None) -> Somme:  # type: ignore[override]
        """Agrège avec information sur la couverture PDF."""
        lignes = self.lignes if code is None else [ligne for ligne in self.lignes if ligne.code == int(code)]
        calcul = round(sum(ligne.valeur for ligne in lignes), 2)
        reel_vals = [ligne.valeur_reel for ligne in lignes if ligne.valeur_reel is not None]
        reel = round(sum(reel_vals), 2) if reel_vals else None
        return Somme(
            calcul=calcul,
            reel=reel,
            months_with_pdf=self._months_with_pdf,
            months_total=self._months_total,
            label=self._label,
        )
