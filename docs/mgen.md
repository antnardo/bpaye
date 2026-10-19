# La PSC santé (MGEN) depuis mai 2026, et la part solidaire

Depuis le 1er mai 2026, les personnels de l'Éducation nationale adhèrent au contrat
collectif santé MGEN – CNP Assurances. Le bulletin porte cinq lignes, comme l'annonce le
ministère : la participation employeur, la part forfaitaire de la cotisation, une part
solidaire variable et deux contributions variables (action sociale, aide aux retraités),
les parts variables étant « calculées sur la base de votre rémunération mensuelle »
(<https://www.education.gouv.fr/la-protection-sociale-complementaire-pour-les-personnels-de-l-education-nationale-de-l-enseignement-325214>,
page lue le 17 octobre 2026). bpaye en imprime quatre : la participation employeur (720580), imprimée
« pour information », n'entre que dans l'assiette de la CSG et de la CRDS.

Le contrat qui fixe les formules n'a pas été trouvé en ligne. Les formules de bpaye sont
celles qui retrouvent au centime les bulletins PAY18E V4.2 de 2026 : c'est ce que fait la
paie, pas ce que dit un texte. Les montants de cette page sont fictifs.

## Les cinq lignes

| Code | Ligne | Dans bpaye (`mgen.py`) |
| --- | --- | --- |
| 720576 | part forfaitaire | fixe (20 % × (`taux.toml`, `mgen.base`)) |
| 720577 | part solidaire | variable (30 % (`taux.toml`, `mgen.base`) × coefficient de rémunération (ci-dessous)) |
| 720578 | action sociale | variable (2 % × (720576 + 720577) HT), arrondi |
| 720579 | aide aux retraités | variable (3 % × (720576 + 720577) HT), arrondi |
| 720580 | part employeur | fixe (50 % × (`taux.toml`, `mgen.base)) ; soumise à CSG et CRDS sans abattement |

Les codes et leurs libellés sont ceux de la nomenclature de la DGFiP de janvier 2026
(PSC santé, IR 0976 à 0980 ; `codes.toml`). 720578 et 720579 restent dans le montant
imposable. La part employeur entre dans l'assiette de la CSG sans l'abattement de
1,75 % (`docs/csg.md`). Le taux de taxation permettant d’obtenir le montant
hors-taxe est donné par (`taux.toml`, `mgen.taux_taxe`).

## La part solidaire (720577)

bpaye calcule :

```text
coefficient = (MIN(tb, PMSS + TPP) + TPP) / brut moyen
720577      = arrondi(30 % × (`taux.toml`, `mgen.base`) × coefficient, 2)
```

où `tb` est le traitement brut indiciaire du mois, `PMSS` le plafond mensuel de la
sécurité sociale (4 005 € en 2026), `TPP` le transfert primes-points mensuel (389 / 12 =
32,42 €) et `brut moyen` 3 107 €, relevé sur les bulletins : aucun texte lu ne le donne.

Pour un traitement de 4 100 € :

```text
MIN(4 100,00 ; 4 005 + 32,42) + 32,42 = 4 037,42 + 32,42 = 4 069,84
0,3 × 75,40 × 4 069,84 / 3 107 = 29,629…  → 29,63 €
```

Le TPP y compte deux fois : une fois dans le plafond, une fois ajouté. On attendrait
plutôt un traitement net du TPP, plafonné au PMSS, soit `MIN(tb − TPP, PMSS)`
(29,16 € dans cet exemple) ; aucun texte lu ne tranche.

## Ce qui n'est pas vérifié

La formule n'est vérifiée que pour un traitement au-dessus de PMSS + TPP. Ces bulletins
fixent un seul numérateur, PMSS + 2 × TPP, que plusieurs formules donnent aussi bien. Elles
divergent sous le plafond, là où se trouvent la plupart des enseignants :

| Formule | Traitement de 3 000 € |
| --- | --- |
| `MIN(tb, PMSS + TPP) + TPP` (bpaye) | 3 032,42 |
| `MIN(tb, PMSS) + 2 × TPP` | 3 064,84 |
| `MIN(tb − TPP, PMSS)` | 2 967,58 |

**Sous le plafond, la part solidaire de bpaye n'est vérifiée par aucun bulletin.** Le
bulletin d'un agent dont le traitement est inférieur au PMSS tranchera.

## Si la paie change de formule

Le calcul est dans `bpaye.mgen._part_solidaire`. Une correction se daterait comme les
autres changements : une entrée datée dans `taux.toml` et le choix de la formule selon la
date du bulletin, pour que les bulletins d'avant gardent la leur.
