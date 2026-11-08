# La PSC santé (MGEN) depuis mai 2026, et la part solidaire

Depuis le 1er mai 2026, les personnels de l'Éducation nationale adhèrent au contrat
collectif santé MGEN – CNP Assurances. Le bulletin porte cinq lignes, comme l'annonce le
ministère : la participation employeur, la part forfaitaire de la cotisation, une part
solidaire variable et deux contributions variables (action sociale, aide aux retraités),
les parts variables étant « calculées sur la base de votre rémunération mensuelle »
(<https://www.education.gouv.fr/la-protection-sociale-complementaire-pour-les-personnels-de-l-education-nationale-de-l-enseignement-325214>,
page lue le 17 octobre 2026). bpaye en imprime quatre : la participation employeur (720580), imprimée
« pour information », n'entre que dans l'assiette de la CSG et de la CRDS.

Le contrat de l'Éducation nationale n'a pas été trouvé en ligne. La part solidaire suit
la règle que donne la FAQ du contrat collectif santé MGEN de même construction, celui du
ministère de l'Europe et des Affaires étrangères (ci-dessous) ; les autres parts sont
celles qui retrouvent au centime les bulletins PAY18E V4.2 de 2026. Les montants de cette
page sont fictifs.

## Les cinq lignes

| Code | Ligne | Dans bpaye (`mgen.py`) |
| --- | --- | --- |
| 720576 | part forfaitaire | fixe (20 % × (`taux.toml`, `mgen.base`)) |
| 720577 | part solidaire | variable (30 % (`taux.toml`, `mgen.base`) × coefficient de rémunération (ci-dessous)) |
| 720578 | action sociale | variable (2 % × (720576 + 720577) HT), arrondi |
| 720579 | aide aux retraités | variable (3 % × (720576 + 720577) HT), arrondi |
| 720580 | part employeur | fixe (50 % × (`taux.toml`, `mgen.base`)) ; soumise à CSG et CRDS sans abattement |

Les codes et leurs libellés sont ceux de la nomenclature de la DGFiP de janvier 2026
(PSC santé, IR 0976 à 0980 ; `codes.toml`). 720578 et 720579 restent dans le montant
imposable. La part employeur entre dans l'assiette de la CSG sans l'abattement de
1,75 % (`docs/csg.md`). Le taux de taxation permettant d’obtenir le montant
hors-taxe est donné par (`taux.toml`, `mgen.taux_taxe`).

## La part solidaire (720577)

La FAQ des agents du contrat collectif MGEN du ministère des Affaires étrangères (MGEN,
octobre 2025, question 71,
<https://www.mgen.fr/sites/default/files/2025-10/MEAE_AEFE_FAQ_Sant%C3%A9_Agents.pdf>)
dit de la part solidaire qu'elle s'obtient « en appliquant un taux à l'assiette de sa
rémunération soumise à CSG-CRDS dans la limite d'un plafond mensuel de Sécurité sociale »,
primes et heures supplémentaires comprises (questions 77, 78 et 81). Le contrat de
l'Éducation nationale a la même structure (cotisation d'équilibre partagée 50/20/30) ;
qu'il ait la même assiette est plausible, non vérifié sur son texte.

bpaye calcule donc :

```text
coefficient = MIN(brut - TPP, PMSS) / brut moyen
720577      = arrondi(30 % × (`taux.toml`, `mgen.base`) × coefficient, 2)
```

où `brut` est la rémunération brute du mois (les éléments à payer, hors remboursements de
frais), `brut − TPP` l'assiette de la CSG avant abattement (`docs/csg.md`), `PMSS` le
plafond mensuel de la sécurité sociale (4 005 € en 2026), `TPP` le transfert primes-points
mensuel (389 / 12 = 32,42 €) et `brut moyen` le brut mensuel moyen des agents de l'EN
(3 107 € en 2024, valeur utilisée pour 2026), obtenu de source syndicale : aucun texte lu
ne le donne.

Pour une rémunération brute de 4 100 € :

```text
MIN(4 100,00 - 32,42 ; 4 005) = 4 005,00
0,3 × 75,40 × 4 005,00 / 3 107 = 29,157…  → 29,16 €
```

### Ce que fait la paie

Les bulletins PAY18E V4.2 de 2026 suivent une autre formule, qui les retrouve au centime :

```text
coefficient = (MIN(brut - TPP, PMSS + TPP) + TPP) / brut moyen
```

Le TPP y compte deux fois : une fois dans le plafond, une fois ajouté. Sous le plafond,
l'assiette est le brut, TPP compris (0,24 € de trop par mois) ; au-delà, le plafond est
relevé de deux TPP (29,63 € au lieu de 29,16 € dans l'exemple, 0,47 € de trop). bpaye
calcule le dû : la comparaison au bulletin montre cet écart sur 720577, et les retenues
qui en dépendent (720578, 720579, impôt) suivent.

Ce qui est attendu, ce qui est observé sur les bulletins et les lectures possibles :
[`mgen_part_solidaire.md`](mgen_part_solidaire.md).

## Si la paie change de formule

Le calcul est dans `bpaye.mgen._part_solidaire`. Une correction se daterait comme les
autres changements : une entrée datée dans `taux.toml` et le choix de la formule selon la
date du bulletin, pour que les bulletins d'avant gardent la leur.
