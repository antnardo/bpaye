"""Registre des codes de rubrique du bulletin (codes.toml) : libellé, rappel, catégorie, source.

Chaque code porte la référence du document de la DGFiP qui l'atteste (nomenclature PAY
de janvier 2026). La catégorie (revenu, retenue, patronal, special) est celle de
bpaye : elle range les lignes du bulletin pour la lecture des PDF et leur affichage.
"""

import tomllib
from pathlib import Path

__all__ = [
    "ALL_CODES",
    "CATEGORIES",
    "CODES_EQUIVALENTS",
    "CODES_TOML",
    "equivalents",
    "load_codes",
]

CODES_TOML = Path(__file__).parent / "codes.toml"


def load_codes(path: Path = CODES_TOML) -> dict[str, dict]:
    """Retourne {code: {libelle, has_rappel, cat, libelle_officiel, imposable, source}}."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return {
        c["code"]: {
            "libelle": c["libelle"],
            "has_rappel": c["rappel"],
            "cat": c["categorie"],
            "libelle_officiel": c.get("libelle_officiel", c["libelle"]),
            "imposable": c.get("imposable"),
            "source": c["source"],
        }
        for c in data["code"]
    }


ALL_CODES = load_codes()
with CODES_TOML.open("rb") as _f:
    CATEGORIES: dict[str, str] = tomllib.load(_f)["categories"]


# Codes d'une même ligne, que la paie emploie l'un pour l'autre : la comparaison au calcul
# les additionne, l'écart de montant restant visible.
# - ISOE modulable, recodée 202566 au 1/9/2024 d'après INGRES, encore portée sous 201228 par
#   un bulletin d'agrégé d'août 2026 ;
# - indemnité compensatrice de CSG : 202206 pour un agent en activité au 31/12/2017, 202209
#   pour un agent recruté ou réintégré depuis (annexe 14 B ; décret 2017-1889) ; bpaye émet
#   202209, le montant venant d'agent.toml ;
# - transfert primes/points : 604970 en catégorie A, 604972 en catégorie C, que la paie a
#   appliqué à un agrégé en 2019 (BJ janvier 2026).
CODES_EQUIVALENTS: tuple[frozenset[str], ...] = (
    frozenset({"201228", "202566"}),
    frozenset({"202206", "202209"}),
    frozenset({"604970", "604972"}),
)


def equivalents(code: str) -> frozenset[str]:
    """Les codes de la même ligne que ``code`` (lui compris)."""
    for groupe in CODES_EQUIVALENTS:
        if code in groupe:
            return groupe
    return frozenset({code})
