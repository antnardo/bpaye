# La part solidaire MGEN (720577) : la paie contre le contrat

Depuis mai 2026, le bulletin porte la part solidaire de la PSC santé (720577), une
cotisation qui suit la rémunération. bpaye ne suit plus la formule qui retrouve les
bulletins : celle-ci compte le transfert primes-points (TPP) deux fois. Cette page dit ce
qu'on attend, ce qu'on observe, et ce qu'on peut en conclure. La formule et les autres
lignes sont décrites dans [`mgen.md`](mgen.md).

Notations (valeurs de 2026) :

| | Valeur | Source |
| --- | --- | --- |
| `base` | 30 % × 75,40 € = 22,62 € | cotisation d'équilibre ; ministère et sources syndicales (`taux.toml`) |
| `PMSS` | 4 005 € | plafond mensuel de la sécurité sociale (`taux.toml`) |
| `TPP` | 389 / 12 = 32,42 € | transfert primes-points mensuel (`taux.toml`) |
| `brut moyen` | 3 107 € | source syndicale, aucun texte lu |
| `brut` | | total des éléments à payer du mois, hors remboursements de frais |

`720577 = arrondi(base × assiette / brut moyen, 2)` : seule l'assiette est en question.

## Ce qui est attendu

Le contrat collectif de l'Éducation nationale n'a pas été trouvé en ligne. Celui du
ministère de l'Europe et des Affaires étrangères, porté par la MGEN avec la même
construction (cotisation d'équilibre partagée 50 / 20 / 30), a une FAQ publiée (MGEN,
octobre 2025,
<https://www.mgen.fr/sites/default/files/2025-10/MEAE_AEFE_FAQ_Sant%C3%A9_Agents.pdf>) :

- la part solidaire s'obtient « en appliquant un taux à l'assiette de sa rémunération
  soumise à CSG-CRDS dans la limite d'un plafond mensuel de Sécurité sociale » (question
  71) ;
- primes, heures supplémentaires et éléments variables y entrent (questions 77, 78, 81).

L'assiette attendue est donc la rémunération soumise à CSG, plafonnée au PMSS. Pour un
agent de l'Éducation nationale, c'est `brut − TPP` : le TPP est retenu sur les primes
avant la CSG ([`csg.md`](csg.md)). Le plafond de l'assiette est le PMSS, ni plus ni moins.

## Ce qui est observé

Sept bulletins PAY18E V4.2 de 2026, de deux agents :

| Bulletins | Rémunération | 720577 observée | Ce qu'elle donne |
| --- | --- | --- | --- |
| mai à octobre 2026, un agent | au-dessus du plafond | 29,63 € chaque mois | assiette = 4 069,84 € = `PMSS + 2 × TPP` |
| août 2026, un autre agent | `brut` = 3 403,54 € | 24,78 € | assiette = 3 403,54 € = `brut`, TPP compris |

- **Au-dessus du plafond**, la part est constante, comme attendu, mais l'assiette
  plafonnée vaut 4 069,84 €. C'est 64,84 € (deux TPP) au-dessus du PMSS :
  22,62 × 4 069,84 / 3 107 = 29,629… → 29,63 €, alors que le PMSS donne 29,16 €.
- **Sous le plafond**, l'assiette est le brut entier, sans en retirer le TPP :
  22,62 × 3 403,54 / 3 107 = 24,779… → 24,78 €. Avec `brut − TPP`, on aurait 24,54 €.

Une seule formule retrouve les sept bulletins au centime :

```text
assiette de la paie = MIN(brut − TPP ; PMSS + TPP) + TPP = MIN(brut ; PMSS + 2 × TPP)
```

## Interprétation

La forme `MIN(brut − TPP ; PMSS + TPP) + TPP` laisse voir un calcul fait sur
l'assiette de la CSG (`brut − TPP`), mais dont le plafond a été relevé d'un TPP et le
résultat augmenté d'un second. Trois lectures sont possibles :

| Lecture | Assiette voulue | Écart de la paie sous le plafond | Au-dessus |
| --- | --- | --- | --- |
| 1. rémunération soumise à CSG (FAQ) | `MIN(brut − TPP ; PMSS)` | +0,24 € par mois | +0,47 € par mois |
| 2. rémunération brute, TPP compris | `MIN(brut ; PMSS)` | aucun | +0,47 € par mois |
| 3. soumise à CSG, part employeur MGEN comprise (720580, 37,70 €) | `MIN(brut − TPP + 37,70 ; PMSS)` | −0,04 € par mois | +0,47 € par mois |

- **Au-dessus du plafond, la paie se trompe dans toutes les lectures.** Aucune ne
  plafonne l'assiette au-delà du PMSS. L'agent paie 22,62 × 64,84 / 3 107 = 0,47 € de
  trop par mois, soit 5,66 € par an, plus l'action sociale et l'aide aux retraités qui en
  dépendent (720578 et 720579, un centime chacune). L'impôt baisse de quelques centimes,
  car ces deux lignes sont imposables.
- **Sous le plafond, la lecture décide.** La FAQ (« soumise à CSG-CRDS ») désigne la
  lecture 1 : la paie prélève alors 0,24 € de trop par mois. La lecture 2 donne raison à
  la paie. La lecture 3 lui donne un tort de 4 centimes dans l'autre sens.
- **Le brut moyen** pèse sur tout le calcul. On ne sait pas s'il a été calculé avec ou
  sans le TPP. S'il l'a été sur l'assiette de la CSG, la lecture 1 est la seule
  cohérente : on diviserait des assiettes nettes du TPP par une moyenne nette du TPP.

bpaye calcule la lecture 1, celle du seul texte lu. L'écart au bulletin (720577 −0,47 €
au-dessus du plafond, −0,24 € en deçà) signale donc une erreur de la paie, pas de bpaye.
La lecture 1 reste une déduction tirée du contrat d'un autre ministère.

## Ce qui trancherait

- Le contrat collectif santé de l'Éducation nationale (convention MGEN – CNP Assurances),
  ou son cahier des charges : la définition de l'assiette et celle du brut moyen.
- Un bulletin sous le plafond avec un remboursement domicile-travail (200039) : il dirait
  si les frais sortent de l'assiette, comme bpaye le suppose.
- Une réponse de la DGFiP ou de la commission paritaire de suivi du contrat sur le
  plafond : `PMSS + 2 × TPP` n'apparaît dans aucun texte.

Si la paie change de formule, le changement se date dans `taux.toml` ([`mgen.md`](mgen.md),
« Si la paie change de formule »).
