# bpaye

[![CI](https://github.com/antnardo/bpaye/actions/workflows/ci.yml/badge.svg)](https://github.com/antnardo/bpaye/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Licence MIT](https://img.shields.io/badge/licence-MIT-green)

> **Avertissement.** bpaye est un outil personnel, sans lien avec le ministère de
> l'Éducation nationale, la DGFiP ou tout autre service de l'État. Il reconstitue des
> règles de calcul dispersées dans de nombreux textes, et en partie déduites de bulletins
> réels quand aucun texte lu ne les précise : ses résultats peuvent être incomplets ou
> erronés. Ils n'ont aucune valeur officielle et ne remplacent ni le bulletin de paye
> établi par l'administration, ni les textes applicables, ni l'avis de votre gestionnaire.
> Une réclamation se fonde sur les textes et sur vos bulletins, non sur bpaye. Le logiciel
> est fourni « en l'état », sans garantie d'aucune sorte, et ses auteurs ne peuvent être
> tenus responsables de l'usage qui en est fait (licence MIT, [`LICENSE`](LICENSE)).

Décrivez la carrière d'un enseignant de l'Éducation nationale : bpaye en calcule les
bulletins de paye, mois par mois et ligne par ligne, comme la paie de l'État, puis les
compare aux bulletins PDF réellement reçus.

## Le but

Un bulletin de paye d'enseignant porte vingt à trente lignes : traitement, indemnité de
résidence, supplément familial, ISOE, heures supplémentaires, primes, pension civile,
RAFP, CSG… Vérifier qu'il est juste demande de connaître son indice à la date du mois,
le montant de chaque prime cette année-là et les règles d'arrondi de la paie. Une
promotion payée trois mois en retard, des heures oubliées ou un rappel incompris se
voient mal autrement.

bpaye refait ce calcul à partir de deux fichiers qui décrivent l'agent : sa carrière
(`carriere.toml`) et sa situation (`agent.toml`). Avec l'exemple fictif d'une certifiée
en collège REP, livré dans `examples/college/` :

```python
from bpaye import Paye, load_agent

agente = load_agent("examples/college/agent.toml")
agente.load_carriere("examples/college/carriere.toml")

paye = Paye(agente)
paye.generate(startyear=2026, startmonth=1, n=12)
print(paye(2026, 1))
```

```text
********************************************************************************
janvier 2026 -- Certifié CN (595)     ORS: 18, HSA:1
--------------------------------------------------------------------------------
 [101000] Traitement Brut                                   : 2929.05€
 [101050] Pension civile                                    :           -325.12€
 [102000] Indemnité de résidence                            :   29.29€
 [104000] Supplément familial traitement                    :   98.54€
 [200039] REMBT DOMICILE-TRAVAIL                            :   37.50€
 [200205] Heures Année Enseignement (HSA - 1h)              :  135.44€
 [200364] ISOE Part fixe                                    :  212.50€
 [200576] Majo 1ère HSA                                     :   27.09€
 [201883] Indemnité de sujétion REP                         :  144.50€
 [202209] Indemnité compensatrice CSG                       :   57.55€
 [202321] Prime équipement informatique                     :  176.00€
 [202326] Prime d'attractivité                              :   33.33€
 [202354] Participation PSC                                 :   15.00€
 [202475] Part fonctionnelle (Pacte)                        :  138.89€
 [202566] ISOE Part modulable                               :  124.82€
 [401201] CSG non déductible                                :           -116.57€
 [401301] CSG déductible                                    :           -253.09€
 [401501] CRDS                                              :            -20.09€
 [453000] Réduction cot. heures sup.                        :             15.07€
 [501080] RAFP                                              :            -29.29€
 [558000] Impot Revenu 4.5%                                 :           -143.81€
 [604970] Transfert Prime Point                             :            -32.42€
--------------------------------------------------------------------------------
                                                 BRUT TOTAL : 4159.50€
                                                 CHARGES    :           -761.51€
                                                 Net impos. : 3195.73€
                                                 NET        : 3254.18€
```

bpaye donne chaque bulletin, ses lignes (`code`, `lib`, `valeur`), son net et son net
imposable, pour tous les mois d'une carrière, passés ou à venir. Il ne dit pas ce qu'il
faut réclamer : il montre l'écart avec le bulletin reçu ; à vous de savoir s'il vient
d'une erreur de la paie ou d'un événement que la carrière ne décrit pas encore.

## Les moyens

1. **Tout est daté.** Une grille, un taux, un montant, un échelon ont une valeur à partir
   d'une date ; un bulletin prend celle du dernier jour de son mois. Une carrière se
   rejoue ainsi depuis son début, avec les règles de chaque année.
2. **Les valeurs viennent des textes.** Chaque grille se compose des indices bruts du
   statut, du barème des indices majorés et des hors-échelle, chacun daté et sourcé
   (Légifrance, nomenclature de la DGFiP). Les quelques montants que seuls les bulletins
   donnent sont notés « relevés » ; une valeur ni lue ni relevée est marquée « MANQUANT »,
   et bpaye refuse alors de calculer plutôt que de deviner.
3. **La carrière avance seule.** Les échelons suivent les durées du statut, les
   reclassements de 2017 et de 2023 suivent leurs tableaux ; le fichier ne décrit que ce
   qui s'en écarte : un avancement au choix, une promotion, ce que change chaque rentrée.
4. **Les arrondis sont ceux de la paie.** Les textes ne disent pas où la paie arrondit ;
   bpaye reproduit au centime la règle des bulletins réels (l'assiette de la CSG en deux
   morceaux, tronquée avant février 2026, arrondie depuis).
5. **La lecture des PDF se contrôle elle-même.** Chaque montant est lu dans sa colonne ;
   les montants à payer, à déduire et pour information doivent retomber sur les totaux
   imprimés au pied du bulletin ; sinon, bpaye le signale.

## Installation

bpaye s'installe depuis ce dépôt GitHub (il n'est pas sur PyPI), avec Python 3.11 ou plus
et Git :

```bash
pip install "bpaye[pdf] @ git+https://github.com/antnardo/bpaye"
```

ou, dans un projet géré par uv :

```bash
uv add "bpaye[pdf] @ git+https://github.com/antnardo/bpaye"
```

Le calcul ne demande que la bibliothèque standard ; l'extra `pdf` ajoute pdfplumber, qui
lit les bulletins PDF. Sans lui (`pip install "bpaye @ git+https://github.com/antnardo/bpaye"`),
tout fonctionne sauf cette lecture.

Ces commandes suivent la branche principale ; pour une version fixe, ajoutez son tag :
`git+https://github.com/antnardo/bpaye@v0.2.0`. Les versions et leurs changements sont
dans [`CHANGELOG.md`](CHANGELOG.md).

Les exemples (`examples/`) ne sont pas dans le paquet installé : pour les lancer,
clonez le dépôt.

```bash
git clone https://github.com/antnardo/bpaye
cd bpaye
pip install ".[pdf]"
python examples/bulletins.py college
```

## Décrire un agent

`carriere.toml` donne la grille et l'échelon de départ, les avancements, les promotions
et une entrée par rentrée :

```toml
[depart]
nom        = "Agente Fictive"
grille     = "GRILLE_CERTCN"   # classe normale des certifiés
corps      = "Certifié"
echelon    = 3
anciennete = 0.0
date       = 2008-09-01

[[avancements]]
type = "PPCR"                  # reclassement du 1er septembre 2017

[[changements_corps]]
date   = 2027-09-01
grille = "GRILLE_CERTHC"       # hors classe

[[rentrees]]
year   = 2025
hsa_vs = 1                     # une heure supplémentaire année
education_prioritaire = "REP"
professeur_principal  = "3e"
pacte  = 1                     # une part de Pacte
```

`agent.toml` donne le taux du prélèvement à la source, les enfants, la zone de
résidence, l'abonnement de transport et l'indemnité compensatrice de CSG (le montant du
bulletin, propre à chaque agent). Trois agents fictifs complets sont livrés :

| Dossier | Agent |
| --- | --- |
| `examples/college/` | une certifiée en collège REP, professeure principale, Pacte, puis temps partiel |
| `examples/agrege_cpge/` | un agrégé en classe préparatoire, heures supplémentaires et colles |
| `examples/carriere_longue/` | une professeure des écoles de 2006 à 2026, directrice d'école en REP+ |

`python examples/bulletins.py agrege_cpge` en montre la carrière rejouée, le brut et le
net de chaque année, un bulletin et la paye prévue.

Corps couverts : agrégés (classe normale, hors classe, classe exceptionnelle), chaires
supérieures, et les corps à la grille des certifiés : certifiés (documentalistes
compris), professeurs des écoles (directeurs compris), PLP, PEPS, CPE, psychologues de
l'Éducation nationale. Les grilles remontent à 2005 pour les agrégés, 2006 pour les
certifiés, 2010 pour les chaires supérieures.

## Calculer et prévoir

Une rubrique sur l'année, ou la paye des mois à venir :

```python
print(paye.select(200364, 2026).somme())       # l'ISOE de 2026, part fixe

from bpaye.prevision import nets_prevus

carriere, agent = "examples/college/carriere.toml", "examples/college/agent.toml"
for mois in nets_prevus(carriere, agent, (2026, 8), 3):
    print(mois.annee, mois.mois, mois.net)
```

```text
Somme [200364] réel=—  calcul=2428.56 € (0/12 mois PDF)
2026 8 2755.62
2026 9 2167.01
2026 10 2167.01
```

En septembre 2026, l'agente passe à 80 % : la prévision le montre. Ce que la carrière ne
prévoit pas (une promotion payée en retard, des colles déclarées, une GIPA) se déclare
sur la paye : `paye.retard_indice`, `paye.colle`, `paye.gipa`… (guide,
[section 5](docs/DOC.md#5-calculer)).

## Vérifier ses bulletins

Les bulletins se téléchargent en PDF sur l'ENSAP. Nommés `AAAA_MM_BP_mois.pdf` dans un
dossier, bpaye les lit ligne par ligne, rappels à part (`code_R`). Sur un bulletin fictif
de trois lignes :

```python
from bpaye.pdf import ecart_totaux, extract_bulletin

lu = extract_bulletin("Bulletins/2026_01_BP_janvier.pdf")
print(lu["101000"], lu["200205"], lu["200205_R"])   # traitement, HSA, rappel d'HSA
print(lu["_totaux_mois"], lu["_net_payer"])         # le pied du bulletin
print(ecart_totaux(lu))                             # 0.0 : lecture complète
```

```text
3000.0 300.0 50.0
3350.0 2350.0
0.0
```

`ecart_totaux` vaut zéro quand les lignes lues retombent, au centime, sur le total
imprimé par la paie ; une rubrique que bpaye ne connaît pas est signalée, pas perdue.

`examples/verifier.py` lit les bulletins d'une année et les compare au calcul, mois par
mois et rubrique par rubrique :

```bash
python examples/verifier.py Bulletins/ 2025 examples/college
```

Pour chaque mois, il affiche le net à payer, le contrôle de la lecture et les rappels,
puis chaque rubrique où le calcul et le bulletin diffèrent.

### Lire un bulletin seul

Sans décrire de carrière, `bpaye-lire` reconnaît un bulletin : il en lit l'en-tête
(grade, échelon, indice, enfants, temps partiel, taux du prélèvement à la source), situe
l'indice dans les grilles de bpaye, et dit ce que trahissent les lignes. Sur un bulletin
fictif :

```bash
bpaye-lire Bulletins/2026_08_BP_aout.pdf
```

```text
== 2026_08_BP_aout.pdf — bulletin de 08/2026
   grade imprimé : PROF. AGREGE CN, échelon 4, indice 547
   reconnu : Agrégé CN, 4e échelon (GRILLE_AGCN)
   indemnité de résidence : zone 1
   enfants : 0 à charge (en-tête), 0 payés par le SFT
   prélèvement à la source : 6.20 %
   net à payer 2350.00 €, montant imposable 2600.00 €
   - traitement payé : temps plein
   - professeur principal (ISOE part modulable)
   - second degré (ISOE part fixe)
```

Une incohérence devient une remarque (« ! ») : un indice qui n'est pas celui de
l'échelon imprimé, par exemple, après une promotion pas encore payée. En Python :
`bpaye.reconnaissance.reconnait(chemin)`.

### Partager un bulletin

Un bulletin dont une ligne est inconnue de bpaye aide à l'améliorer. Pour le joindre à une
issue, `scripts/anonymise_bulletin.py` en écrit une copie sans ce qui identifie l'agent
(NIR, nom et adresse, affectation, IBAN, code-barres), en gardant toutes les lignes de
paye, puis vérifie qu'aucun identifiant n'y reste ; l'original n'est jamais modifié :

```bash
uv run scripts/anonymise_bulletin.py 2026_08_BP_aout.pdf
```

Ce qu'il efface, ce qu'il laisse et comment il le vérifie :
[`docs/anonymisation.md`](docs/anonymisation.md).

## Sources

Chaque valeur des tables porte sa source à côté d'elle : texte, article, version lue.
Les relevés complets sont dans [`docs/verification/`](docs/verification/). Les règles
d'arrondi, que les textes ne donnent pas, sont décrites dans [`docs/csg.md`](docs/csg.md)
(CSG et CRDS), [`docs/mgen.md`](docs/mgen.md) (PSC santé) et
[`docs/indexation.md`](docs/indexation.md) (ISOE et IFP indexées sur le point). La lecture des bulletins
PDF, colonne par colonne, est détaillée dans [`docs/lecture_pdf.md`](docs/lecture_pdf.md).
Le guide complet, avec chaque clé des fichiers et chaque rubrique calculée, est dans
[`docs/DOC.md`](docs/DOC.md).

## Limites

- **Les indemnités ponctuelles** (jurys, examens, missions particulières) : la ligne du
  bulletin se lit, mais n'est pas calculée. **La bonification indiciaire des directeurs
  d'école** n'a pas de rubrique connue : sa ligne est signalée comme code inconnu.
- **Les montants qu'aucun texte lu ne donne** : la pension civile avant 2011, le plafond
  de transport avant août 2016, l'indemnité des CPE de 2016 à 2021, les chaires
  supérieures avant 2010… bpaye refuse de calculer ces mois-là (liste dans le
  guide, [« Limites »](docs/DOC.md#9-limites)).
- **Les cotisations patronales**, imprimées « pour information » sur le bulletin : hors du
  sujet de bpaye, qui ne calcule que ce que perçoit l'agent (guide,
  [« Limites »](docs/DOC.md#9-limites)).
- **Les contractuels**, dont l'indice dépend de l'académie, et **l'enseignement privé**,
  qui relève d'autres cotisations.
- **La part solidaire de la PSC santé sous le plafond de la sécurité sociale** : aucun
  bulletin ne la vérifie encore ([`docs/mgen.md`](docs/mgen.md)).
- **Le calendrier de la paie** (l'IFP de septembre payée en octobre, les HSA d'octobre en
  novembre) vient de bulletins réels, non d'un texte.

## Développement

```bash
uv sync --group dev
uv run ruff format src tests scripts examples
uv run ruff check src tests scripts examples
uv run mypy
uv run pytest
```

Le style du code et la règle des sources : [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licence

MIT.
