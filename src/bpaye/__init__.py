"""Bulletins de paye d'un enseignant : calcul mois par mois, prévision, lecture des PDF.

Le calcul rejoue une carrière depuis son début (grilles datées, avancements,
reclassements) et refait chaque bulletin, ligne par ligne, avec les règles d'arrondi
des bulletins réels : il se compare ainsi au centime aux bulletins PDF (pdf.py).
"""

from bpaye.colles import Colles
from bpaye.fonctionnaire import Fonctionnaire, charge_agent, charge_dossier, load_agent
from bpaye.grille import GRILLE_AGCN, GRILLE_CHSUP
from bpaye.hsa import compile_hs
from bpaye.paye import Paye
from bpaye.point import POINT
from bpaye.reclassement import reclasse

__version__ = "0.2.0"

__all__ = [
    "GRILLE_AGCN",
    "GRILLE_CHSUP",
    "POINT",
    "Colles",
    "Fonctionnaire",
    "Paye",
    "__version__",
    "charge_agent",
    "charge_dossier",
    "compile_hs",
    "load_agent",
    "reclasse",
]
