"""Extraction des données depuis les bulletins de paye PDF (format PAY18E, de V1.4 à
V4.2).

Format : chaque ligne de paye occupe 3 lignes de texte extrait :
  CODE LIBELLE
  €
  montant
Les cotisations patronales et les lignes spéciales (011100, 011300, 558000)
suivent le même format.

Le footer contient NET À PAYER, TOTAUX DU MOIS,
MONTANT IMPOSABLE DU MOIS.
Plus difficiles à extraire : position.

"""

import logging
import re
import warnings
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from bpaye.codes import ALL_CODES

__all__ = [
    "COLONNES",
    "DR_MONTH_FR",
    "DR_ROW_CODES",
    "HORS_TOTAUX",
    "SUPPORTED_VERSIONS",
    "BulletinLu",
    "EmployeurLu",
    "LigneLue",
    "Span",
    "a_du_texte",
    "colonne",
    "ecart_totaux",
    "ecarts_colonnes",
    "extract_bulletin",
    "extract_dr",
    "extract_employeur",
    "extract_sirets",
    "find_dr_pdfs",
    "find_pdfs",
    "is_agent_bulletin",
    "parse_amount",
]

_log = logging.getLogger(__name__)

# Un morceau de texte du bulletin : abscisse et ordonnée de son coin haut gauche (en
# points, origine en haut à gauche de la page), et son texte.
Span = tuple[float, float, str]

# Deux caractères consécutifs du flux appartiennent au même morceau s'ils sont sur la
# même ligne (DY) et se suivent à moins d'une largeur de caractère (ECART) : le code et
# le libellé d'une ligne de paye se rejoignent (« 101000 TRAITEMENT BRUT »), le symbole €
# et le montant, loin à droite, restent à part. Les bulletins de 2026 font chevaucher
# d'un point l'espace et la lettre qui la suit : un petit recul est toléré. Au-delà d'un
# point d'écart sans espace dans le flux, on en met une.
_DY = 1.5
_ECART = 6.0


# Les trois colonnes de montants, par l'abscisse du bord gauche du montant : à payer
# (≈ 385), à déduire (≈ 457), pour information (≈ 517 à 520). Relevées identiques sur les
# bulletins de 2019 à 2026, de V2.3 à V4.2.
COLONNES = ("payer", "deduire", "information")
_BORNES_COLONNES = (430.0, 500.0)
# La colonne où un code de chaque catégorie s'imprime d'ordinaire ; un montant dans une
# autre colonne (une reprise de traitement « à déduire ») change de signe.
_COLONNE_DE_CATEGORIE = {"revenu": "payer", "retenue": "deduire", "patronal": "information"}


def colonne(x: float) -> str:
    """La colonne d'un montant dont le bord gauche est à l'abscisse ``x``."""
    if x < _BORNES_COLONNES[0]:
        return "payer"
    return "deduire" if x < _BORNES_COLONNES[1] else "information"


@dataclass(frozen=True, slots=True)
class LigneLue:
    """Une ligne de paye telle qu'imprimée : son code, son libellé, la colonne et le montant
    (signe imprimé), et si c'est un rappel."""

    code: str
    libelle: str
    colonne: str
    montant: float
    rappel: bool


# Le pied du bulletin : la clé « _… » de chaque champ de BulletinLu, et son nom.
_PIED = {
    "_net_payer": "net_payer",
    "_totaux_mois": "totaux_mois",
    "_total_ret": "total_ret",
    "_total_pat": "total_pat",
    "_montant_imp": "montant_imp",
    "_rappel_decompte": "rappel_decompte",
    "_rappel_decompte_ret": "rappel_decompte_ret",
    "_total_dupercu": "total_dupercu",
}


@dataclass(frozen=True, slots=True)
class BulletinLu(Mapping[str, Any]):
    """Un bulletin PDF lu : ses montants par code (``"101000"``, et ``"101000_R"`` pour un
    rappel), son pied, ses codes inconnus de bpaye.

    Il se lit aussi comme un dictionnaire, clé par clé : ``lu["101000"]``, ``lu.get(…)``,
    ``"200205_R" in lu``, et ``lu["_totaux_mois"]`` pour un champ du pied, présent
    seulement s'il a été lu ; ``lu["_unknown"]`` donne les codes inconnus. Un script qui
    traitait la lecture comme un dict reste juste, sans pouvoir la modifier."""

    montants: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    inconnus: tuple[tuple[str, str, float], ...] = ()
    lignes: tuple[LigneLue, ...] = ()
    net_payer: float | None = None
    totaux_mois: float | None = None
    total_ret: float | None = None
    total_pat: float | None = None
    montant_imp: float | None = None
    rappel_decompte: float | None = None
    rappel_decompte_ret: float | None = None
    total_dupercu: float | None = None

    def _cles(self) -> dict[str, Any]:
        cles: dict[str, Any] = {"_unknown": list(self.inconnus)}
        cles.update(self.montants)
        for cle, nom in _PIED.items():
            valeur = getattr(self, nom)
            if valeur is not None:
                cles[cle] = valeur
        return cles

    def __getitem__(self, cle: str) -> Any:
        return self._cles()[cle]

    def __iter__(self) -> Iterator[str]:
        return iter(self._cles())

    def __len__(self) -> int:
        return len(self._cles())


def _lu(resultats: dict[str, Any], lignes: Sequence[LigneLue] = ()) -> BulletinLu:
    pied = {nom: resultats[cle] for cle, nom in _PIED.items() if cle in resultats}
    montants = {cle: v for cle, v in resultats.items() if not cle.startswith("_")}
    return BulletinLu(
        montants=MappingProxyType(montants),
        inconnus=tuple(resultats.get("_unknown", ())),
        lignes=tuple(lignes),
        **pied,
    )


def _pages(pdf_path: str | Path) -> list[list[Span]]:
    """Les morceaux de texte de chaque page, dans l'ordre du flux du PDF.

    pdfplumber (MIT) est importé seulement ici : le calcul de la paye n'en a pas
    besoin. L'ordre du flux est celui où PAY18E écrit le bulletin, ligne de paye par
    ligne de paye ; c'est lui que suit extract_bulletin, pas un tri par position."""
    import pdfplumber

    pages: list[list[Span]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            spans: list[list] = []
            for c in page.chars:
                if spans:
                    _, top, x1, texte = spans[-1]
                    ecart = c["x0"] - x1
                    if abs(c["top"] - top) <= _DY and -_ECART / 2 <= ecart <= _ECART:
                        spans[-1][2] = c["x1"]
                        spans[-1][3] = texte + (" " if ecart > 1.0 else "") + c["text"]
                        continue
                spans.append([c["x0"], c["top"], c["x1"], c["text"]])
            pages.append([(x0, top, texte.strip()) for x0, top, _, texte in spans if texte.strip()])
    return pages


# Versions de PAY18E dont la lecture est vérifiée sur des bulletins réels (V2.0 : jamais vue).
SUPPORTED_VERSIONS: set[str] = {"V1.4", "V1.6", "V2.1", "V2.3", "V4.0", "V4.2"}

_SIRET_RE = re.compile(r"^\d{14}$")
_CODE_RE = re.compile(r"^\d{6}\s+.+")
_AMOUNT_RE = re.compile(r"^-?[\d][\d\xa0 ]*,\d{1,2}$")  # accepte l'espace insécable
_VERSION_RE = re.compile(r"PAY18E\s*-\s*(V\d+\.\d)", re.IGNORECASE)


def parse_amount(s: str) -> float | None:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_sirets(pdf_path: str | Path) -> set[str]:
    """Retourne les SIRETs (14 chiffres) présents dans l'en-tête du bulletin (y < 120)."""
    return {t for _, y, t in _pages(pdf_path)[0] if y < 120 and _SIRET_RE.match(t)}


@dataclass(frozen=True, slots=True)
class EmployeurLu:
    """L'employeur imprimé en en-tête d'un bulletin : le service gestionnaire (« DRFIP DE LA
    GIRONDE »), le code de gestion du poste (« 08 A445 072 0314 »), le libellé de
    l'affectation et les SIRET. Le code de gestion reste le même sur tous les bulletins
    d'un employeur, même un rappel versé après le départ, que la paie imprime parfois sans
    SIRET."""

    gestionnaire: str = ""
    poste: str = ""
    libelle: str = ""
    sirets: frozenset[str] = frozenset()


# Les blocs de l'en-tête, par l'abscisse du bord gauche de leurs morceaux et leur ordonnée :
# le gestionnaire (x ≈ 81, y ≈ 6 à 29), le code de gestion du poste (x ≈ 78, y ≈ 60 et 71),
# le libellé (x ≈ 213, y ≈ 60 et 73). Relevés identiques de V1.4 (2017) à V4.2 (2026).
_GESTIONNAIRE = (75.0, 90.0, 0.0, 36.0)
_POSTE = (72.0, 90.0, 52.0, 80.0)
_LIBELLE = (205.0, 300.0, 52.0, 82.0)


def _bloc(spans: Sequence[Span], cadre: tuple[float, float, float, float]) -> str:
    x0, x1, y0, y1 = cadre
    return " ".join(" ".join(t.split()) for x, y, t in spans if x0 <= x < x1 and y0 <= y < y1)


def extract_employeur(pdf_path: str | Path) -> EmployeurLu:
    """L'employeur imprimé en en-tête du bulletin (première page)."""
    spans = _pages(pdf_path)[0]
    return EmployeurLu(
        gestionnaire=_bloc(spans, _GESTIONNAIRE),
        poste=_bloc(spans, _POSTE),
        libelle=_bloc(spans, _LIBELLE),
        sirets=frozenset(t for _, y, t in spans if y < 120 and _SIRET_RE.match(t)),
    )


def a_du_texte(pdf_path: str | Path) -> bool:
    """Vrai si la première page porte du texte : un bulletin de l'ENSAP en a toujours, un
    scan (une image seule) n'en a pas et ne se lit pas comme un PDF vectoriel."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return bool(pdf.pages) and bool(pdf.pages[0].chars)


def is_agent_bulletin(pdf_path: str | Path, agent_siret: str) -> bool:
    """Retourne True si le bulletin appartient à l'organisme identifié par agent_siret."""
    return agent_siret in extract_sirets(pdf_path)


def extract_bulletin(pdf_path: str | Path) -> BulletinLu:
    """
    Le bulletin lu (BulletinLu), qui se lit aussi comme un dict à ces clés :
      {code}         : montant courant pour chaque code BP
      {code}_R       : montant rappel si applicable
      '_net_payer'   : NET À PAYER (footer)
      '_totaux_mois' : TOTAUX DU MOIS (footer)
      '_total_ret'   : total retenues salariales (footer)
      '_total_pat'   : total cotisations patronales (footer)
      '_montant_imp' : MONTANT IMPOSABLE DU MOIS (footer)
      '_rappel_decompte'     : rappel sur rémunération principale, à payer (« * RAPPELS :
                               VOIR DÉCOMPTE », au-dessus des totaux), détaillé par le DR
      '_rappel_decompte_ret' : sa part de retenues, en négatif
      '_unknown'     : liste de (code, libellé, montant) pour codes non référencés

    Un rappel porte la mention « RAPPEL ANNEE COURANTE » ou « RAPPEL ANNEES ANTERIEURES »
    (parfois tronquée), soit fondue dans le libellé, soit juste après le montant : son
    montant va sous ``{code}_R``. La reprise sans mention d'un code qui peut être rappelé
    (codes.toml) est aussi un rappel. Un code présent plusieurs fois s'additionne : deux
    rappels de colles de mois différents, deux indemnités de jury. Relevé sur des
    bulletins de 2019 à 2026 (PAY18E V2.3 à V4.2) : la mention ne porte jamais de
    montant à part.
    """
    pages = _pages(pdf_path)
    _page_spans = pages[0]
    # La version (« PAY18E - V2.3 ») est écrite à la verticale, une lettre par morceau :
    # elle se lit sur les morceaux mis bout à bout.
    _vm = _VERSION_RE.search("".join(t for _, _, t in _page_spans))
    _version = _vm.group(1).upper() if _vm else None

    if _version is None or _version not in SUPPORTED_VERSIONS:
        warnings.warn(
            f"{Path(pdf_path).name} : version PAY18E non reconnue "
            f"({_version!r}). L'extraction du footer peut être incorrecte. "
            f"Versions prises en charge : {sorted(SUPPORTED_VERSIONS)}",
            stacklevel=2,
        )

    morceaux = [span for page in pages for span in page]
    lines = [t for _, _, t in morceaux]

    results: dict = {"_unknown": []}
    lues: list[LigneLue] = []
    inconnus_vus: set[str] = set()

    # ── Lignes de paye (tous codes 6 chiffres) ───────────────────────────────
    for i, line in enumerate(lines):
        if not _CODE_RE.match(line):
            continue
        code = line[:6]
        libelle = line[7:].strip()

        # Le montant : le premier qui suit, avant la ligne de paye suivante ; puis la
        # mention de rappel, si elle n'est pas déjà dans le libellé.
        amount = None
        x_montant = 0.0
        rappel = "RAPPEL" in libelle.upper()
        for j in range(i + 1, min(i + 6, len(lines))):
            lj = lines[j]
            if _CODE_RE.match(lj):
                break
            if lj in ("€", ""):
                continue
            if amount is None:
                if _AMOUNT_RE.match(lj):
                    amount = parse_amount(lj)
                    x_montant = morceaux[j][0]
                continue
            rappel = rappel or "RAPPEL" in lj.upper()
            break

        if amount is None:
            continue

        # Code inconnu : signaler et passer. Une rubrique nouvelle sur le bulletin ne doit
        # pas disparaître sans bruit : elle manque alors au calcul comme au classeur.
        if code not in ALL_CODES:
            if code not in inconnus_vus:
                results["_unknown"].append((code, libelle, amount))
                inconnus_vus.add(code)
                warnings.warn(
                    f"{Path(pdf_path).name} : code {code} inconnu ({libelle}, {amount} €), "
                    "à ajouter à codes.toml",
                    stacklevel=2,
                )
            continue

        # Sans mention, la reprise d'un code qui peut être rappelé est un rappel : en
        # novembre 2021, les HSA d'octobre suivent celles du mois, sans « RAPPEL ».
        if not rappel and code in results and ALL_CODES[code]["has_rappel"]:
            rappel = True
        cle = code + "_R" if rappel else code
        imprimee = colonne(x_montant)
        lues.append(LigneLue(code, libelle, imprimee, amount, rappel))
        # Un montant hors de la colonne de sa catégorie se compte en sens inverse : un
        # traitement repris « à déduire » diminue le traitement.
        attendue = _COLONNE_DE_CATEGORIE.get(ALL_CODES[code]["cat"])
        signe = -1 if attendue is not None and imprimee != attendue else 1
        results[cle] = round(results.get(cle, 0.0) + signe * amount, 2)

    # ── Footer par position (stable V2.3 et V4.0) ───────────────────────────
    #
    # Zones de capture (coordonnées en points, page 0, origine haut-gauche) :
    #
    #  Bandeau récapitulatif (y ≈ 621–634) :
    #    x ≈ 374  → _totaux_mois  (V4.0 : peut contenir _total_ret dans le
    #                               même span sous la forme "X    Y")
    #    x ≈ 446  → _total_ret    (span séparé en V2.3)
    #    x ≈ 521  → _total_pat
    #
    #  Ligne « * RAPPELS : VOIR DÉCOMPTE » (y ≈ 595–612), quand un décompte de rappel
    #  accompagne le bulletin : son montant à payer entre dans TOTAUX DU MOIS.
    #    x ≈ 374  → _rappel_decompte
    #    x ≈ 519  → _rappel_decompte_ret
    #
    #  Ligne NET À PAYER (y ≈ 638–652) :
    #    x ≈ 415  → _net_payer
    #
    #  Panneau bas-gauche MONTANT IMPOSABLE (y ≈ 705–720) :
    #    x ≈ 119  → _montant_imp  (colonne « DU MOIS »)
    #
    # TOTAL DU-PERCU reste extrait par regex (apparaît dans l'en-tête textuel).

    multi_re = re.compile(r"-?[\d][\d\xa0 ]*,\d{1,2}")
    dupercu_re = re.compile(r"TOTAL\s+DU-PERCU\s*:\s*([\d\xa0 ]*,\d{1,2})", re.IGNORECASE)

    # Zones : clé → (x_min, x_max, y_min, y_max)
    zones: dict[str, tuple] = {
        "_totaux_mois": (365, 440, 621, 634),
        "_total_ret": (438, 475, 621, 634),
        "_total_pat": (510, 545, 621, 634),
        "_net_payer": (395, 475, 638, 652),
        "_rappel_decompte": (365, 440, 595, 612),
        "_rappel_decompte_ret": (510, 545, 595, 612),
        "_montant_imp": (100, 145, 705, 720),
    }

    for key, (xmin, xmax, ymin, ymax) in zones.items():
        for sx, sy, st in _page_spans:
            if xmin <= sx <= xmax and ymin <= sy <= ymax:
                nums = [parse_amount(m.replace("\xa0", " ")) for m in multi_re.findall(st)]
                nums = [n for n in nums if n is not None]
                if not nums:
                    continue
                if key == "_totaux_mois":
                    results["_totaux_mois"] = nums[0]
                    # V4.0 : deux montants dans le même span
                    if len(nums) >= 2 and "_total_ret" not in results:
                        results["_total_ret"] = nums[1]
                elif key not in results:
                    results[key] = nums[0]
                break

    # TOTAL DU-PERCU : montant inline dans l'en-tête textuel
    for line in lines:
        m = dupercu_re.search(line)
        if m:
            v = parse_amount(m.group(1))
            if v is not None:
                results["_total_dupercu"] = v
            break

    lu = _lu(results, lues)
    for nom, ecart in ecarts_colonnes(lu).items():
        if ecart:
            warnings.warn(
                f"{Path(pdf_path).name} : les lignes lues ne font pas le total « {_TOTAL_DE[nom]} » "
                f"(écart de {ecart} €) : une ligne est manquée",
                stacklevel=2,
            )
    return lu


# Le total du pied que chaque colonne doit retrouver.
_TOTAL_DE = {"payer": "TOTAUX DU MOIS à payer", "deduire": "à déduire", "information": "pour information"}


# Les lignes imprimées qui ne comptent dans aucun total du pied : les nets (011…) et le
# montant simulé du prélèvement à la source de fin 2018 (558001), imprimé pour information
# mais hors du total pour information (bulletins de décembre 2018 : les cotisations
# patronales seules retrouvent ce total).
HORS_TOTAUX = ("011", "558001")


def _somme(lu: BulletinLu, nom: str) -> float:
    """Les montants imprimés dans la colonne ``nom``, hors lignes qui ne comptent dans aucun
    total (HORS_TOTAUX) ; les codes inconnus n'y sont pas, pour que leur absence se voie."""
    return sum(
        ligne.montant
        for ligne in lu.lignes
        if ligne.colonne == nom and not ligne.code.startswith(HORS_TOTAUX)
    )


def ecart_totaux(lu: Mapping[str, Any]) -> float | None:
    """TOTAUX DU MOIS (à payer) moins les montants lus dans la colonne à payer, rappel sur
    décompte compris, au centime : 0 quand toutes les lignes à payer ont été lues ; None
    sans TOTAUX DU MOIS. Le contrôle de la lecture : une ligne manquée ou écrasée s'y voit.
    Vérifié nul sur 98 bulletins de 2019 à 2026.

    Une lecture sans colonnes (un dict d'une ancienne lecture) se contrôle sur les codes de
    catégorie revenu."""
    total = lu.get("_totaux_mois")
    if total is None:
        return None
    if isinstance(lu, BulletinLu) and lu.lignes:
        lues = _somme(lu, "payer")
    else:
        lues = sum(
            valeur
            for cle, valeur in lu.items()
            if not cle.startswith("_") and ALL_CODES[cle[:6]]["cat"] == "revenu"
        )
    return round(total - lues - lu.get("_rappel_decompte", 0.0), 2)


def ecarts_colonnes(lu: BulletinLu) -> dict[str, float | None]:
    """L'écart de chaque colonne avec son total du pied (None : rien à contrôler).

    - à payer : ecart_totaux ;
    - à déduire : le total des retenues, prélèvement à la source compris. Avec un rappel
      sur décompte, les bulletins de 2019 ne comptaient pas la part de retenues du
      décompte, ceux de 2026 la comptent : l'une ou l'autre somme est juste ;
    - pour information : les cotisations patronales ; celles d'un décompte de rappel n'ont
      pas de ligne sur le bulletin mais entrent dans le total : sans contrôle ces mois-là.
    """
    ecarts: dict[str, float | None] = {"payer": ecart_totaux(lu), "deduire": None, "information": None}
    if not lu.lignes:
        return ecarts
    if lu.total_ret is not None:
        deduire = round(lu.total_ret - _somme(lu, "deduire"), 2)
        if lu.rappel_decompte_ret and round(deduire + lu.rappel_decompte_ret, 2) == 0:
            deduire = 0.0
        ecarts["deduire"] = deduire
    if lu.total_pat is not None and not lu.rappel_decompte:
        ecarts["information"] = round(lu.total_pat - _somme(lu, "information"), 2)
    return ecarts


# ── Décomptes de rappel (bulletins DR) ───────────────────────────────────────

DR_MONTH_FR: dict[str, int] = {
    "JANVIER": 1,
    "FEVRIER": 2,
    "MARS": 3,
    "AVRIL": 4,
    "MAI": 5,
    "JUIN": 6,
    "JUILLET": 7,
    "AOUT": 8,
    "SEPTEMBRE": 9,
    "OCTOBRE": 10,
    "NOVEMBRE": 11,
    "DECEMBRE": 12,
}

# Labels dans le DR → code BP correspondant : les quatre lignes des décomptes relevés,
# puis toute ligne dont le libellé est celui d'un revenu ou d'une retenue de codes.toml
# (une NBI, une indemnité rappelées), sans que les quatre premières soient écrasées.
DR_ROW_CODES: dict[str, str] = {
    **{
        info["libelle"].upper(): code
        for code, info in ALL_CODES.items()
        if info["cat"] in ("revenu", "retenue") and not code.startswith("011")
    },
    "TRAITEMENT BRUT": "101000",
    "RETENUE PC": "101050",
    "INDEMNITE DE RESIDENCE": "102000",
    "SUPP FAMILIAL TRAITEMENT": "104000",
}


def _closest_idx(val: float, positions: list[float]) -> int:
    """Indice de la position la plus proche de val."""
    return min(range(len(positions)), key=lambda i: abs(positions[i] - val))


def extract_dr(pdf_path: str | Path) -> dict[tuple[int, int], dict[str, float]]:
    """Parse un bulletin DR (décompte de rappel, format PAY18E).

    Retourne {(annee, mois): {bp_code: correction}} où :
      correction = abs(DÛ) - abs(PERÇU)
      > 0 : rappel dû à l'agent (sous-payé)
      < 0 : trop perçu (à rembourser)

    La détection repose sur les coordonnées x/y des spans pour être
    robuste face aux colonnes vides (mois avec PERÇU = 0). Chaque page se lit à part, ses
    ordonnées n'ayant de sens que sur elle ; les corrections d'un même mois s'additionnent.
    """
    result: dict[tuple[int, int], dict[str, float]] = {}
    for page in _pages(pdf_path):
        for cle, corrections in _dr_page(page).items():
            cible = result.setdefault(cle, {})
            for code, valeur in corrections.items():
                cible[code] = round(cible.get(code, 0.0) + valeur, 2)
    return result


def _dr_page(all_spans: list[Span]) -> dict[tuple[int, int], dict[str, float]]:
    """Les corrections d'une page de décompte de rappel (extract_dr)."""

    def _norm(t: str) -> str:
        return re.sub(r"\s+", "", t.upper())

    # ── Colonnes DÛ / PERÇU (ligne des en-têtes) ─────────────────────────────
    du_spans = [(x, y) for x, y, t in all_spans if _norm(t) == "DÛ"]
    if not du_spans:
        return {}
    header_y = du_spans[0][1]

    du_cols = sorted(x for x, y in du_spans if abs(y - header_y) < 5)
    percu_cols = sorted(x for x, y, t in all_spans if abs(y - header_y) < 5 and _norm(t) == "PERÇU")

    # ── Mois couverts (ligne des noms de mois, juste au-dessus des en-têtes) ──
    # Les mois sujets sont immédiatement au-dessus de la ligne DÛ/PERÇU (~23 pt),
    # alors que le mois de gestion est bien plus haut dans le header (~90 pt).
    month_y_cands = [
        y
        for x, y, t in all_spans
        if t.strip().upper() in DR_MONTH_FR
        and header_y - 50 < y < header_y  # juste au-dessus, pas le header de gestion
    ]
    if not month_y_cands:
        return {}
    # Prendre la ligne la plus proche de header_y (cas où il y en aurait plusieurs)
    month_y = min(month_y_cands, key=lambda y: header_y - y)

    month_spans = [
        (x, t.strip().upper())
        for x, y, t in all_spans
        if abs(y - month_y) < 5 and t.strip().upper() in DR_MONTH_FR
    ]
    year_spans = [
        (x, int(t.strip()))
        for x, y, t in all_spans
        if abs(y - month_y) < 5 and t.strip().isdigit() and len(t.strip()) == 4
    ]

    # Associer chaque nom de mois à l'année la plus proche (à droite)
    months: list[tuple[float, int, int]] = []  # (x_col, year, month_num)
    for mx, mname in sorted(month_spans):
        yr_candidates = [(abs(yx - mx), yr) for yx, yr in year_spans if yx >= mx]
        if yr_candidates:
            _, yr = min(yr_candidates)
            months.append((mx, yr, DR_MONTH_FR[mname]))

    if not months:
        return {}

    # Associer chaque mois à sa colonne DÛ la plus proche
    col_for_month = [_closest_idx(mx, du_cols) for mx, _, _ in months]

    # ── Lire les lignes de données ────────────────────────────────────────────
    result: dict[tuple[int, int], dict[str, float]] = {}

    for row_label, bp_code in DR_ROW_CODES.items():
        label_ys = [y for x, y, t in all_spans if t.strip() == row_label]
        if not label_ys:
            continue
        row_y = label_ys[0]

        # Valeurs numériques présentes sur cette ligne
        vals_on_row = [
            (x, parse_amount(t))
            for x, y, t in all_spans
            if abs(y - row_y) < 5 and parse_amount(t) is not None
        ]
        if not vals_on_row:
            continue

        for i, (_, yr, mo) in enumerate(months):
            col_idx = col_for_month[i]
            if col_idx >= len(du_cols):
                continue
            du_x = du_cols[col_idx]

            # Valeur DÛ : valeur la plus proche de la colonne DÛ
            du_val_raw = min(vals_on_row, key=lambda v: abs(v[0] - du_x))[1]
            if du_val_raw is None:
                continue
            du_val: float = du_val_raw

            # Valeur PERÇU : uniquement si une valeur se trouve près de percu_cols[col_idx]
            percu_val: float = 0.0
            if col_idx < len(percu_cols):
                percu_x = percu_cols[col_idx]
                nearby = [
                    (abs(vx - percu_x), v)
                    for vx, v in vals_on_row
                    if abs(vx - percu_x) < 40 and v is not None
                ]
                if nearby:
                    raw = min(nearby)[1]
                    percu_val = raw if raw is not None else 0.0

            correction = round(abs(du_val) - abs(percu_val), 2)
            if correction != 0.0:
                result.setdefault((yr, mo), {})[bp_code] = correction

    return result


# ── Recherche des fichiers PDF dans le dossier bulletins ─────────────────────

_BP_PAT = re.compile(r"^(\d{4})_(\d{2})_BP_.+\.pdf$")
_DR_PAT = re.compile(r"^(\d{4})_(\d{2})_DR_.+\.pdf$")


def _scan_pdfs(
    bull_dir: str | Path,
    year: int,
    pattern: re.Pattern,
    agent_siret: str | None,
    label: str,
) -> dict[int, list[Path]]:
    """Balaye bull_dir et ses sous-dossiers directs (un par employeur, par exemple) pour
    trouver les PDF correspondant au pattern et à l'année donnés ; le SIRET écarte ceux
    d'un autre employeur, et un PDF sans texte (un scan) est écarté : ni sa lecture ni son
    SIRET ne se lisent. Retourne {mois: [chemins]}."""
    base = Path(bull_dir)
    dirs = [base, *sorted(d for d in base.iterdir() if d.is_dir())] if base.is_dir() else []
    pdfs: dict[int, list[Path]] = {}
    for dirpath in dirs:
        for fpath in sorted(dirpath.iterdir()):
            m = pattern.match(fpath.name)
            if not m or int(m.group(1)) != year:
                continue
            if not a_du_texte(fpath):
                _log.info("  skip %s %s (sans texte : un scan)", label, fpath.name)
                continue
            if agent_siret and not is_agent_bulletin(fpath, agent_siret):
                _log.info("  skip %s %s (SIRET non correspondant)", label, fpath.name)
                continue
            month = int(m.group(2))
            pdfs.setdefault(month, []).append(fpath)
    return pdfs


def find_pdfs(
    bull_dir: str | Path,
    year: int,
    agent_siret: str | None = None,
) -> dict[int, list[Path]]:
    """Retourne {mois: [chemins_pdf]} pour tous les bulletins BP de l'année."""
    return _scan_pdfs(bull_dir, year, _BP_PAT, agent_siret, "BP")


def find_dr_pdfs(
    bull_dir: str | Path,
    year: int,
    agent_siret: str | None = None,
) -> dict[int, list[Path]]:
    """Retourne {mois_gestion: [chemins_DR_pdf]} pour les décomptes de rappel."""
    return _scan_pdfs(bull_dir, year, _DR_PAT, agent_siret, "DR")
