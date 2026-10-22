# ISOE et IFP : des montants indexés sur le point

Trois indemnités des enseignants ont un montant annuel « indexé sur la valeur du point
indiciaire de la fonction publique » : la part fixe de l'ISOE (200364), sa part modulable
(201228, puis 202566) et l'IFP des CPGE (200597). Leurs arrêtés fixent un montant à une
date ; entre deux arrêtés, aucun texte n'écrit le montant revalorisé après une hausse du
point. bpaye le calcule, avec la règle qui retrouve les bulletins. Les montants de cette
page sont ceux des barèmes, les mêmes pour tous les agents.

## Les textes

| Indemnité | Indexation | Montants fixés par arrêté |
| --- | --- | --- |
| ISOE, part fixe | décret 93-55, art. 4 | arrêté du 15/01/1993, art. 1 : 6 426 F (1992), 1 183,68 € (1/1/2009), 1 213,56 € (1/9/2021), 2 550 € (1/9/2023) |
| ISOE, part modulable | décret 93-55, art. 4 | même arrêté, art. 2 : par niveau de classe, en 2009, 2021 et 2023 |
| IFP des CPGE | décret 99-886, art. 3 | arrêté du 19/10/1999, art. 1 : 6 270 F au 1/9/1999, jamais converti en euros |

Les textes ne disent ni quel point sert de base, ni comment arrondir.

## La règle

À chaque hausse du point, la paie applique le rapport des points au **montant mensuel du
mois d'avant, déjà arrondi au centime**, et non au montant de l'arrêté :

```text
mensuel(hausse) = arrondi(mensuel(veille) × point nouveau / point ancien, 2)
```

Un nouvel arrêté remet la chaîne à son montant (divisé par 12, arrondi au centime).

Exemple, l'IFP en juillet 2016 (point annuel de 55,5635 à 55,8969 €) :

```text
depuis le mois d'avant      87,62 × 55,8969 / 55,5635        = 88,146 → 88,15 €   ← bulletin
depuis la référence de 2008 1 034,76 / 12 × 55,8969 / 54,6834 = 88,144 → 88,14 €   ✗
```

L'écart n'est que d'un centime, mais il départage les deux règles, et la règle chaînée
retrouve tous les bulletins relevés. Elle explique même un arrêté : l'ISOE de 2007
(97,85 € par mois), indexée ainsi sur les hausses de 2008, donne 98,64 € par mois, soit
les 1 183,68 € par an que fixe l'arrêté de 2009. Pour la part modulable, la chaîne partie
de 2009 retombe exactement sur les arrêtés de 2021 et de 2023 (6e-5e-4e : 1 215 € →
1 245,84 € → 1 308,72 €).

## Les montants de bpaye

Par mois, à temps plein :

| Depuis | ISOE, part fixe | ISOE modulable, 6e-5e-4e | IFP |
| --- | --- | --- | --- |
| 2008-03 | 98,34 | — | 86,23 |
| 2009-01 | 98,64 | 101,25 | 86,49 |
| 2010-07 | 99,93 | 102,58 | 87,62 |
| 2016-07 | 100,53 | 103,20 | 88,15 |
| 2017-02 | 101,13 | 103,82 | 88,68 |
| 2022-07 | 104,67 | 107,45 | 91,78 |
| 2023-07 | 106,24 | 109,06 | 93,16 |
| 2023-09 | 212,50 | 109,06 | 93,16 |

## L'IFP : la paie, et non le texte

C'est le seul écart au texte que bpaye choisit.

L'arrêté du 19/10/1999 dit toujours 6 270 F au 1er septembre 1999. Convertis
(6 270 / 6,55957 = 955,86 €) et indexés par la même règle depuis le point de 1999, ils
donnent **0,07 % de moins** que ce que verse la paie, à toute date :

| Depuis | Texte (6 270 F indexés) | Paie (bulletins) |
| --- | --- | --- |
| 2008-03 | 86,16 | 86,23 |
| 2016-07 | 88,08 | 88,15 |
| 2017-02 | 88,61 | 88,68 |
| 2022-07 | 91,71 | 91,78 |
| 2023-07 | 93,09 | 93,16 |

Aucune variante ne retombe sur la paie : recalcul depuis la référence au lieu de la chaîne,
arrondi au centime, troncature ou arrondi par excès, montant en francs indexé et arrondi
au franc jusqu'en 2002 puis converti. La conversion qu'a faite la paie n'est écrite dans
aucun texte lu.

Comme le décret 99-886 ne fixe ni la base ni l'arrondi de l'indexation, le texte ne permet
pas de dire que la paie se trompe : bpaye part donc du premier montant payé relevé,
1 034,76 € par an en mars 2008, qui redonne tous les bulletins depuis. Cet écart est noté
là où il s'applique : `taux.toml` (`ifp_cpge`), `indemnites.indemnite_fonctions_part_cpge`
et les limites du guide.

L'ISOE n'a pas ce problème depuis 2009 : bpaye part de ses arrêtés en euros. Avant 2009,
il faudrait le point du 1/9/1992 pour indexer les 6 426 F, et bpaye refuse ces mois.

## Dans bpaye

- `taux.toml` : `[isoe]`, `[isoe_modulable."<niveau>"]` et `[ifp_cpge]`, de type
  `IndexePoint`, avec les montants des arrêtés (et, pour l'IFP et l'ISOE de 2007, le
  relevé qui sert de référence).
- `config.Bareme._load_indexe` : la règle chaînée, montant de référence par montant de
  référence, à chaque hausse de `[point]`.
- `indemnites.indemnite_isoe`, `indemnites.isoe_part_modulable`,
  `indemnites.indemnite_fonctions_part_cpge` : les lignes du bulletin.
- `tests/test_config.py` : les montants de cette page.
