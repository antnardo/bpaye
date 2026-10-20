# Relevés de vérification

Relevés faits le 17 octobre 2026 sur Légifrance (versions consolidées datées) et dans
les nomenclatures de la DGFiP (copies publiées par l'AMUE). Chaque valeur y porte son
texte, son article et la version lue ; ce qui n'a pas pu être lu est marqué MANQUANT.

| Fichier | Contenu | Utilisé par |
| --- | --- | --- |
| `indices_bruts.toml` | indices bruts par grade et par date | `scripts/genere_grilles.py` |
| `bareme.toml` | barème IB → IM, valeur du point, hors-échelle | `genere_grilles.py`, `taux.toml` |
| `durees_reclassements.toml` | durées d'échelon, tableaux de reclassement, règles de classement | `genere_grilles.py`, `reclassements.toml` |
| `primes.toml` | primes, indemnités, ORS, heures supplémentaires, retenues | `taux.toml`, `ors.py`, `hsa.py` |
| `codes.toml` | codes de rubrique du bulletin | `codes.toml` du paquet |
| `temps_partiel_nbi_pacte_gipa.toml` | temps partiel, surcotisation, NBI, Pacte, GIPA | `temps_partiel.py`, `point.py`, `indemnites.py`, `gipa.py`, `taux.toml` |
| `indemnites_et_manques.toml` | indemnités des CPE, PsyEN, documentalistes, directeurs d'école ; barèmes 2005–2006, PsyEN 2017–2023, chevrons, transport, ICSG | `bareme.toml`, `indices_bruts.toml`, `taux.toml` |
| `csg_crds.toml` | réduction, taux et part déductible de la CSG, CRDS, plafond mensuel de la sécurité sociale (2001–2026, relevé du 18 octobre 2026) | `taux.toml`, `charges.py` |
| `codes_indemnites_corps.toml` | codes DGFiP des indemnités des CPE, PsyEN, documentalistes, directeurs d'école | `codes.toml` du paquet |
| `academies.toml` | académies (code de l'éducation, R222-2, versions 2017 et 2021) et lycées de la Défense (relevé du 20 octobre 2026) | `academies.toml` du paquet |

Après une nouvelle lecture des textes, mettre à jour le relevé, puis :

```bash
uv run python scripts/genere_grilles.py
```
