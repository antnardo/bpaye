# CSG et CRDS : la règle de calcul des bulletins

Les textes fixent les taux et l'assiette : CSG de 9,2 % sur les revenus d'activité (code
de la sécurité sociale, L136-8), dont 6,8 points déductibles de l'impôt (code général des
impôts, art. 154 quinquies) ; réduction de 1,75 % pour frais professionnels sous quatre
fois le plafond de la sécurité sociale (L136-2) ; CRDS de 0,5 % sur la même assiette
(ordonnance 96-50, art. 14 et 19). Ils ne disent pas comment la paie de l'État découpe
l'assiette ni où elle arrondit. bpaye reproduit la règle que suivent les bulletins PAY18E, vérifiée au
centime sur des bulletins de 2019 à 2026 ; ses limites sont en fin de page. Tous
les montants de cette page sont fictifs.

## La règle

L'assiette se construit en quatre temps :

1. **Assiette brute** : les revenus soumis du bulletin, rappels compris (traitement brut
   101000, indemnité de résidence 102000, SFT 104000, ISOE, IFP, indemnité compensatrice
   de CSG, primes, heures supplémentaires et colles), moins le transfert primes-points
   (604970). Les remboursements de frais (domicile-travail 200039, forfait mobilités
   durables 200041) n'y entrent pas.
2. **Heures supplémentaires exonérées d'impôt** : HSA, majoration, colles, HSE (celles de
   suppléance, de remplacement et des dispositifs comprises), toutes du décret 50-1253
   (décret 2019-133, art. 1, 2°), et parts fonctionnelles du Pacte (même article, 29°), dans la
   limite d'un plafond annuel (5 000 € nets, soit 5 358 € bruts ; 7 500 € nets, soit
   8 037 € bruts, pour les heures faites depuis le 1er janvier 2022 : loi 2022-1157,
   art. 4). Le plafond se consomme dans l'ordre de l'année
   civile : toutes les heures de janvier, celles de février jusqu'au plafond, plus rien
   ensuite.
3. **Abattement de 1,75 %**, sous le seuil de `taux.toml`, séparément sur le salaire hors
   heures exonérées et sur les heures exonérées, chacun ramené au centime : **tronqué**
   jusqu'en janvier 2026, **arrondi** depuis février 2026, quand le logiciel de paie
   change (bulletins PAY18E V2.3, puis V4.0 et V4.2).
4. **Part employeur de la complémentaire santé** (MGEN, code 720580, 37,70 € depuis mai
   2026) : elle s'ajoute **sans abattement**.

Avec `S` le salaire abattu hors heures exonérées, `H` les heures exonérées abattues, `M`
la part employeur, et un arrondi au centime, la moitié vers le haut :

| Retenue | Code | Calcul |
| --- | --- | --- |
| CSG déductible | 401301 | arrondi(6,8 % × S) **+** arrondi(6,8 % × M) |
| CSG non déductible | 401201 | arrondi(2,4 % × (S + H + M)) **+** arrondi(6,8 % × H) |
| CRDS | 401501 | arrondi(0,5 % × (S + H + M)) |

Trois principes :

- **La CSG des heures exonérées n'est pas déductible** : sa part à 6,8 % passe de la CSG
  déductible à la CSG non déductible. Le total de CSG ne change pas.
- **Deux arrondis pour la CSG déductible** depuis mai 2026 : un sur le salaire, un sur la
  part employeur. Sans part employeur, c'est un simple arrondi. Un arrondi unique du
  total, ou une troncature, s'écarte d'un centime dans certains mois (exemples
  ci-dessous).
- **Chaque morceau d'assiette se ramène au centime avant le taux**, par troncature ou
  par arrondi selon le logiciel de paie.

Le bulletin donne aussi les heures exonérées nettes (011200) = heures exonérées ×
0,93319 (= 1 − 98,25 % × 6,8 %), tronqué. Le montant imposable en retire ce 011200 et la
CSG basculée.

## Pourquoi la CSG non déductible de janvier est si forte

En janvier et en février, mois où le plafond d'exonération se consomme, la CSG non
déductible est deux à trois fois plus forte qu'aux autres mois. Divisée par 2,4 % ×
98,25 %, elle donne une assiette apparente `a_impl` plus grande que l'assiette réelle
`a`, avec `X` les heures exonérées :

```text
CSG non déductible = 2,4 % × 98,25 % × a + 6,8 % × 98,25 % × X
a_impl = a + (6,8 / 2,4) × X = (a − X) + (1 + 6,8 / 2,4) × X
```

Les heures exonérées comptent donc 1 + 6,8 / 2,4 = 9,2 / 2,4 ≈ 3,83 fois : toute leur
CSG (9,2 %) est non déductible, au lieu de 2,4 %.

## Exemples

Ce sont ceux de `tests/test_charges.py` et de `tests/test_charges_impots.py`.

### Le cas courant

Assiette brute 4 000,00 € (sans part employeur ni heures exonérées) :

```text
salaire abattu      4 000,00 × 0,9825 = 3 930,00
CSG déductible      6,8 % × 3 930,00  = 267,24
CSG non déductible  2,4 % × 3 930,00  = 94,32
CRDS                0,5 % × 3 930,00  = 19,65
```

### Ancien et nouveau logiciel de paie

Assiette brute 5 007,00 € :

```text
salaire abattu      5 007,00 × 0,9825 = 4 919,3775
jusqu'en janvier 2026 (troncature)    → 4 919,37 ; CSG non déductible 118,0649 → 118,06
depuis février 2026   (arrondi)       → 4 919,38 ; CSG non déductible 118,0651 → 118,07
```

### Quand un arrondi unique se trompe

Assiette brute 4 005,00 €, part employeur 37,70 € (2026) :

```text
salaire abattu      4 005,00 × 0,9825 = 3 934,9125 → 3 934,91
CSG déductible      6,8 % × 3 934,91 = 267,5739 → 267,57
                  + 6,8 % ×    37,70 =   2,5636 →   2,56
                                                  = 270,13   ← bulletin
arrondi unique      6,8 % × 3 972,61 = 270,1375 → 270,14   ✗
```

Les deux morceaux s'arrondissent vers le bas et perdent ensemble un peu plus d'un
demi-centime : leur somme reste à 270,13 quand le total arrondi monte à 270,14.

### Quand une troncature se trompe

Assiette brute 4 020,00 €, part employeur 37,70 € (2026) :

```text
salaire abattu      4 020,00 × 0,9825 = 3 949,65
CSG déductible      6,8 % × 3 949,65 = 268,5762 → 268,58
                  + 6,8 % ×    37,70 =   2,5636 →   2,56
                                                  = 271,14   ← bulletin
troncature          6,8 % × 3 987,35 = 271,1398 → 271,13   ✗
```

### Un mois à heures exonérées

Assiette brute 6 000,00 €, dont 2 000,00 € d'heures supplémentaires exonérées :

```text
salaire abattu      4 000,00 × 0,9825 = 3 930,00   (S)
heures abattues     2 000,00 × 0,9825 = 1 965,00   (H)
CSG déductible      6,8 % × 3 930,00 = 267,24
CSG non déductible  2,4 % × 5 895,00 = 141,48
                  + 6,8 % × 1 965,00 = 133,62   = 275,10
total               267,24 + 275,10 = 542,34 = 9,2 % × 5 895,00
```

## Limites

- **La consommation du plafond d'exonération** n'est pas toujours celle décrite au point
  2 : en 2021 et en 2022, la paie a exonéré plus d'heures que le plafond annuel n'en
  laissait, puis plus rien (en 2022 : tout jusqu'en mars, au-delà de 5 000 €, rien dès
  avril, avant 7 500 €) ; l'attestation fiscale régularise. bpaye calcule le dû : ces
  mois-là s'écartent du bulletin.
- **Une assiette qui ne se reconstitue pas** (la CRDS du bulletin ne tombe pas juste)
  signale un élément versé par un document à part, comme un décompte de rappel : la
  vérification écarte ces bulletins.

## Vérifier sur ses bulletins

Avec l'extra `pdf`, depuis le dépôt :

```bash
python scripts/verifie_csg.py DOSSIER_DES_BULLETINS agent.toml
```

Le script reconstitue l'assiette de chaque bulletin à partir de ses propres lignes,
rappels compris, cumule les heures exonérées sur l'année civile, puis compare au bulletin
la CSG et la CRDS que calcule bpaye ; la CRDS, que l'exonération ne touche pas, valide
l'assiette. Pour les mois sans heures exonérées, il compare aussi les règles simples
(troncature, arrondi unique). Les montants ne s'affichent qu'à l'écran.

## Dans bpaye

- `charges.NOUVEAU_LOGICIEL_PAIE`, `charges._assiettes` : les deux morceaux d'assiette,
  abattus et ramenés au centime selon le logiciel de paie.
- `charges.csg`, `charges.csg_nonded`, `charges.crds`, `charges.csg_basculee` : les
  retenues ; `supplement_hors_abat` reçoit la part employeur
  (`mgen.mgen_part_employeur`), `hs_exonerees` les heures exonérées du mois.
- `charges_impots.ExonerationHS` : le plafond annuel, consommé bulletin par bulletin et
  partagé par les bulletins d'une `Paye` ; `Bulletin.hs_exonerees`,
  `Bulletin.hs_exa_net` (011200) et `Bulletin.net_imposable` s'en servent.
- `tests/test_charges.py`, `tests/test_charges_impots.py` : les exemples ci-dessus.
