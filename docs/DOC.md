# bpaye : le guide

bpaye refait les bulletins de paye d'un enseignant comme les fait la paie de l'État, mois
par mois, à partir de sa carrière. Il sert à vérifier ses bulletins, à comprendre un
rappel, à prévoir les mois à venir.

Les extraits de ce guide viennent des trois agents fictifs d'`examples/`, présentés à la
section 2 ; chacun se lance ainsi :

```bash
python examples/bulletins.py college
python examples/bulletins.py agrege_cpge
python examples/bulletins.py carriere_longue
```

## 1. Le principe

Tout est daté. Une grille, un taux, un montant, un échelon, un nombre d'enfants ont une
valeur à partir d'une date, jusqu'à la suivante. Un bulletin prend, pour chaque élément,
la valeur en vigueur le dernier jour de son mois (un échelon pris en cours de mois est payé
au prorata des jours ; pour le reste, enfant, zone, quotité, cette règle est supposée,
aucun texte lu ne la donne). bpaye peut ainsi rejouer une carrière
entière : les durées d'échelon de 2010 pour un avancement de 2010, le reclassement du
1er septembre 2017, la grille de 2024 pour un bulletin de 2024.

Deux fichiers décrivent l'agent :

- `carriere.toml` : ce qui fait le traitement et le service (grille, échelons,
  promotions, rentrées) ;
- `agent.toml` : ce qui lui est propre (prélèvement à la source, enfants, résidence,
  transport, indemnité compensatrice de CSG).

## 2. Trois exemples

### Une certifiée en collège (`examples/college/`)

Entrée en 2008 au 3e échelon de la classe normale, reclassée au 1er septembre 2017,
elle est depuis la rentrée 2024 professeure principale de troisième dans un collège REP,
avec une heure supplémentaire. Elle prend une part de Pacte en 2025, passe à 80 % à la
rentrée 2026 en surcotisant pour la retraite, et la hors classe est prévue en 2027 :

```toml
[[rentrees]]
year   = 2025
hsa_vs = 1
education_prioritaire = "REP"
professeur_principal  = "3e"
pacte  = 1                      # 1 250 € versés d'octobre à juin

[[rentrees]]
year          = 2026
education_prioritaire = "REP"
professeur_principal  = "3e"
temps_partiel = 0.8             # payée 6/7 d'un temps plein
surcotisation = true            # retraite cotisée comme à temps plein
```

Son bulletin de janvier 2026 porte l'ISOE (part fixe et part modulable de professeure
principale), l'indemnité REP, la prime d'attractivité du 9e échelon, l'heure
supplémentaire et sa majoration, la part de Pacte. À partir de septembre 2026, traitement,
résidence, SFT et primes sont réduits aux six septièmes (sauf l'indemnité compensatrice
de CSG) ; la retenue pour pension, elle,
est prise sur le traitement d'un temps plein, à un taux plus élevé.

### Un agrégé en classe préparatoire (`examples/agrege_cpge/`)

Recruté en 2012, promu au grand choix au 5e échelon, reclassé en 2017, il gagne un an au
6e échelon (l'accélération d'après 2017). En seconde année de classe préparatoire
scientifique depuis 2019, son ORS dépend de l'effectif ; il fait quatre heures
supplémentaires et colle dans sa classe :

```toml
[[avancements]]
echelon = 5
type    = "GC"                  # grand choix, avant 2017

[[avancements]]
type = "PPCR"

[[avancements]]
echelon = 7
type    = "C"                   # depuis 2017 : un an de moins au 6e échelon

[[rentrees]]
year     = 2025
annee    = 2
effectif = 42                   # plus de 35 élèves : 8 heures
type_classe = "sciences"
hsa_vs   = 4
colles       = { 161 = 3.0 }
colles_debut = 2025-09-22
colles_fin   = 2026-04-10
```

Ses bulletins portent l'IFP et des heures supplémentaires calculées sur son ORS de
8 heures ; la paye prévue de l'année 2025-2026 montre les colles, payées après coup, à
partir de novembre. La hors classe est prévue en 2028, après deux ans au 9e échelon.

### Une professeure des écoles, de 2006 à 2026 (`examples/carriere_longue/`)

Une carrière de vingt ans, rejouée depuis 2006, bulletin par bulletin depuis 2011 : grand choix au
6e échelon, reclassement de 2017, accélération au 8e, trois enfants nés en cours de
route (le SFT suit), direction d'une école de six classes en REP+ depuis 2019 (ISS
majorée de moitié), hors classe en 2023, une année à 80 % avec une demi-part de Pacte :

```toml
[depart]
grille = "GRILLE_CERTCN"        # la grille des certifiés, commune aux professeurs des écoles
corps  = "PE"                   # d'où l'ISAE au lieu de l'ISOE, et 24 heures de service
date   = 2006-09-01

[[rentrees]]
year = 2019
education_prioritaire = "REP+"
direction_ecole       = 6
```

`examples/bulletins.py` en donne le brut et le net de chaque année : on y voit l'effet
de chaque échelon, de l'ISAE en 2013 et 2016, de la direction d'école, du temps partiel.

## 3. `carriere.toml`

### Le départ

```toml
[depart]
nom        = "Agente Fictive"
grille     = "GRILLE_CERTCN"
corps      = "Certifié"        # facultatif, voir ci-dessous
echelon    = 3
anciennete = 0.0               # années déjà passées dans l'échelon
date       = 2008-09-01
zone_vacances = "B"            # facultatif, C par défaut : pour les colles prévues
```

Les grilles :

| Grille | Corps et grade |
| --- | --- |
| `GRILLE_AGCN`, `GRILLE_AGHC`, `GRILLE_AGCE` | agrégés : classe normale, hors classe, classe exceptionnelle |
| `GRILLE_CERTCN`, `GRILLE_CERTHC`, `GRILLE_CERTCE` | certifiés, PE, PLP, PEPS, CPE, PsyEN : mêmes indices |
| `GRILLE_CHSUP` | chaires supérieures |

`corps` dit lequel des six corps quand la grille est partagée : « Certifié », « PE »,
« PLP », « PEPS », « CPE », « PsyEN ». Il décide de l'ORS hors CPGE, de l'ISOE (second
degré) ou de l'ISAE (PE), et de la grille de référence des heures supplémentaires.

Les grilles commencent au 1er juillet 2005 (agrégés), au 1er janvier 2006 (certifiés et
corps à la même grille), au 1er septembre 2010 (chaires supérieures, dont l'échelonnement
antérieur n'est pas publié) et au 1er septembre 2017 (classes exceptionnelles, créées ce
jour-là).

### Les avancements

bpaye avance l'agent à l'ancienneté. Une liste d'avancements précise les autres :

```toml
[[avancements]]
echelon = 5
type    = "GC"         # grand choix (avant le 1er septembre 2017)

[[avancements]]
type = "PPCR"          # reclassement du 1er septembre 2017

[[avancements]]
echelon = 9
type    = "C"          # choix avant 2017 ; depuis, l'accélération d'un an aux 6e et 8e

[[avancements]]
type = "reclassement"  # un autre reclassement de reclassements.toml
date = 2023-08-06
```

Les avancements s'appliquent dans l'ordre chronologique, quel que soit leur ordre dans le
fichier. `echelon` est l'échelon atteint plus tôt : `echelon = 9, type = "C"` raccourcit
le temps passé au 8e (avant 2017, la durée « au choix » ; depuis, l'accélération d'un an,
aux 6e et 8e échelons seulement).

Le reclassement suit le tableau du décret pour la grille de l'agent ce jour-là
(`reclassements.toml`) : échelon d'arrivée, ancienneté conservée, perdue ou majorée,
dans la limite de la durée du nouvel échelon. Une promotion selon l'ancien statut qui
tombe le jour même passe avant (règle du décret 2017-786).

### Les changements de grade ou de corps

```toml
[[changements_corps]]
date   = 2027-09-01
grille = "GRILLE_CERTHC"
# echelon_depart = 1   facultatif : sinon le 1er échelon d'indice égal ou supérieur
# corps = "Certifié"   facultatif, comme au départ
```

L'ancienneté repart de zéro à la date du changement ; les échelons suivants tombent à son
jour du mois. Un changement de grade dans une grille partagée garde le corps (un PE promu
à la hors classe reste PE) ; un changement vers la grille d'un autre corps (agrégation,
chaire supérieure) prend le corps de la nouvelle grille, sauf `corps` explicite.

### Les rentrées

Une entrée par année scolaire : ses éléments valent jusqu'à la rentrée suivante, qui doit
redonner tout ce qui continue (une clé absente vaut zéro : pas d'heures, pas de REP, temps
plein). Avant la première rentrée déclarée, l'agent a le service ordinaire de son corps :
ni CPGE, ni heures supplémentaires, ni éducation prioritaire, ni temps partiel.

```toml
[[rentrees]]
year   = 2024          # rentrée 2024, année 2024-2025
hsa_vs = 2             # heures supplémentaires année, à l'état VS
education_prioritaire = "REP"     # facultatif : « REP » ou « REP+ »
professeur_principal  = "3e"      # facultatif : niveau de la classe
```

Niveaux de professeur principal : « 6e-5e-4e », « 3e », « cap », « bac-pro », « 2nde »,
« autres-lp », « 1re-terminale », « 1re-terminale-referent ». Les montants ne sont connus
que depuis le 1er septembre 2023.

**En CPGE**, la rentrée donne l'année de la classe et son effectif, qui fixent l'ORS
(décret 50-581) ; l'IFP est versée, et les heures supplémentaires se calculent sur la
classe normale des agrégés (sauf chaire supérieure) :

```toml
[[rentrees]]
year     = 2025
annee    = 2           # seconde année
effectif = 45          # plus de 35, de 20 à 35, moins de 20
type_classe = "sciences"          # « sciences » (défaut), « lettres », « autres »
hsa_vs   = 6
```

Hors CPGE, l'ORS est celle du corps : 15 heures pour un agrégé, 18 pour un certifié ou un
PLP, 20 pour un PEPS (décret 2014-940), 24 pour un professeur des écoles (décret
2008-775) ; `ors = 21` l'impose dans tous les cas (un PE en SEGPA, par exemple).

**Temps partiel, NBI, Pacte**, pour l'année scolaire :

```toml
temps_partiel  = 0.8           # quotité ; ou heures_service = 15 (quotité = heures / ORS)
surcotisation  = true          # retenue pour pension sur un temps plein (« anterieure » : choix d'avant février 2024)
nbi            = 30            # points de nouvelle bonification indiciaire
pacte          = 1             # parts fonctionnelles de l'ISOE ou de l'ISAE (0.5 : une demi-part)
```

**CPE, PsyEN, documentalistes, directeurs d'école** : le corps (« CPE », « PsyEN ») se
donne au départ ; à la rentrée :

```toml
specialite      = "EDO"        # PsyEN : « EDA » ou « EDO »
documentaliste  = true         # professeur documentaliste : pas d'ISOE, son indemnité propre
direction_ecole = 5            # directeur d'une école de 5 classes (majorée en REP, REP+)
```

Un CPE ou un PsyEN n'a pas d'ORS : ni heures supplémentaires ni colles.

À 80 % et 90 %, l'agent perçoit 6/7 et 32/35 ; pour une quotité aménagée entre les deux,
la fraction vaut (quotité × 4/7 + 40) % (décret 82-624, art. 1). Le traitement, la NBI, l'indemnité de
résidence et les primes suivent cette fraction ; le SFT aussi, sauf l'élément fixe d'un
enfant et sans descendre sous le minimum d'un temps plein ; la prime d'équipement
informatique reste entière (`temps_partiel.py`), comme l'indemnité compensatrice de CSG,
propre à l'agent (un changement de quotité ne la modifie pas : décret 2017-1889, art. 5). Le Pacte se verse par neuvième ; ses
mois, d'octobre à juin, sont supposés.

**Les colles prévues** (pour la paye à venir) :

```toml
colles        = { 161 = 4.0 }  # heures par semaine, par code de colle
colles_debut  = 2025-09-22
colles_fin    = 2026-04-10     # au plus tard : 20 semaines de colles comptées
colles_classe = 7.0            # budget hebdomadaire de sa classe : reliquat en fin d'année

[[rentrees.colles_externes]]   # colles dans un autre établissement, payées à part
etablissement = "Lycée voisin"
zone          = "A"
colles        = { 1 = 2.0 }
colles_debut  = 2025-09-22
colles_fin    = 2026-04-10
```

Le taux d'une colle est celui du code déclaré par le lycée (161, 6, 7, 8 pour un agrégé ;
157, 1, 90 pour une chaire supérieure), pas celui du colleur.

### Le détachement

```toml
[[detachements]]
date    = 2008-09-01
detache = false
```

## 4. `agent.toml`

```toml
siret = "19750000000000"       # facultatif : seuls les bulletins de ce gestionnaire sont lus

[ir]                           # seule section obligatoire
type   = "Taux"
values = [{ date = 2019-01-01, valeur = 0.045 }]

[[enfants]]
date   = 2018-03-01
nombre = 2

[[residence]]                  # zone de l'indemnité de résidence : 1 (3 %), 2 (1 %), 3 (0)
date = 2008-09-01
zone = 2

[[transport]]                  # abonnement domicile-travail, coût annuel
date              = 2016-09-01
abonnement_annuel = 600

[[fmd]]                        # forfait mobilités durables : niveau 1, 2 ou 3
date   = 2023-01-01
niveau = 1

[ic_csg]                       # indemnité compensatrice de CSG, relevée sur les bulletins
type   = "Fixe"
unite  = "mensuel"
values = [{ date = 2025-01-01, valeur = 30.00 }]

[[academie]]                   # facultatif : ses retards habituels de paie
date = 2019-09-01
nom  = "paris"                 # une clé de academies.toml, ou "defense"

[[retards]]                    # facultatif : les retards habituels propres à l'agent
code = 200041                  # le FMD, dû en janvier,
du   = 1
paye = 2                       # payé en février

[[psc]]                        # facultatif : ancienne mutuelle précomptée sur la paie
date              = 2019-09-01
mutuelle_adherent = 45.00      # 700678, montants du contrat
mutuelle_enfants  = 12.00      # 700671

[[psc]]                        # depuis la PSC : ce que le barème ne peut connaître
date        = 2026-05-01
cout_option = 7.24             # prix de l'option santé choisie
prevoyance  = true             # adhésion au socle de prévoyance
```

Sans enfants, résidence, transport ou détachement déclarés, bpaye compte zéro enfant, la
zone 3, pas de transport, pas de détachement. Un enfant, un abonnement, un forfait ou un
détachement déclaré ne vaut qu'à partir de sa date ; la zone déclarée vaut depuis
l'entrée dans la carrière. L'indemnité compensatrice de CSG déclarée (`[ic_csg]`) doit
couvrir tous les mois calculés depuis 2018 : avant son premier montant, bpaye refuse.
Sans `[ic_csg]`, bpaye refuse les mois depuis 2018 : le montant est propre à chaque agent.

bpaye calcule chaque ligne au mois où elle est due. Certains retards sont pourtant
l'usage de la paie, chaque année les mêmes : le neuvième d'octobre des HSA payé en
novembre, l'IFP de septembre en octobre. `academies.toml`, dans le paquet, les donne par
académie (code de l'éducation, R222-2, et lycées de la Défense ; relevé dans
`docs/verification/academies.toml`) : un défaut, relevé sur des bulletins de Paris, dont
chaque académie hérite tant que les siens ne sont pas relevés. `[[academie]]` choisit
celle de l'agent à chaque date (le défaut avant la première) ; `[[retards]]` ajoute les
siens, qui remplacent ceux de l'académie pour le même code (`depuis`, facultatif, en fixe
le premier mois dû). Un retard s'applique comme `Paye.retard_paiement` : la ligne reste
due son mois et arrive en rappel le mois de paiement. Un retard ponctuel reste un
événement (`paye.retard_paiement`, section 5).

`[[psc]]` déclare ce que le barème ne peut connaître de la complémentaire de l'agent.
Chaque entrée vaut à partir de sa date et remplace la précédente ; une clé absente vaut
zéro. Depuis la PSC (mai 2026), le bulletin porte, outre les cinq lignes de la PSC santé
(`docs/mgen.md`), les participations de l'employeur aux garanties facultatives, que bpaye
calcule (`taux.toml`) : la moitié du coût de l'option santé, dans la limite de 5 €
(202483), et 7 € pour l'adhésion au socle de prévoyance (202510). Les cotisations de
l'option, des ayants droit et de la prévoyance ne sont pas sur le bulletin : la MGEN les
prélève sur le compte. Avant la PSC, l'ancienne mutuelle était précomptée sur la paie
(700678, 700671), à des montants propres au contrat ; ils restent dans le net imposable,
supposé : une adhésion facultative n'est pas un contrat collectif obligatoire, seul
déductible (CGI, art. 83, 1° quater).

## 5. Calculer

```python
from bpaye import Paye, load_agent

agente = load_agent("agent.toml")
agente.load_carriere("carriere.toml")
paye = Paye(agente)
paye.generate(startyear=2025, startmonth=1, n=12)
```

`load_agent` crée l'agent à partir d'`agent.toml`, et `load_carriere` y ajoute sa
carrière ; chacune rend l'agent, et l'ordre est libre (`Fonctionnaire().load_carriere(…)`
pour une carrière seule). Ce qu'aucun des deux fichiers ne donne prend sa valeur par
défaut (section 4).

Générer depuis janvier : la RAFP se plafonne sur l'année civile, comme l'exonération des
heures supplémentaires. `paye(2025, 3)` est le bulletin de mars ; ses lignes (`code`,
`lib`, `valeur`) s'itèrent, et il a `net`, `net_imposable`, `brut`, `revenus`.

### Ce que la carrière ne prévoit pas

```python
paye.retard_indice((2025, 9), (2025, 11), indice=562)   # promotion payée en novembre
paye.retard_paiement((2025, 3), 200205)                  # les HSA de mars payées en mai
paye.colle((2025, 10), {161: 6.0})                       # colles déclarées en octobre
paye.hse((2025, 11), 3)                                  # heures supplémentaires effectives
paye.hse((2025, 11), 2, code=201241)                     # HSE de remplacement de courte durée
paye.vacation((2025, 12), 6, 42.0)                       # 6 h de vacations de formation à 42 €
paye.erreur((2025, 4), (2025, 6), 50.0, 200364)          # un trop-versé repris deux mois après
paye.gipa(2023, (2025, 12))                              # la GIPA de 2023, versée en décembre 2025
```

`hse` paie au taux de l'HSE ; `code` choisit la rubrique : 201241 (remplacement de
courte durée), 201717 puis 201300 (réussite scolaire au lycée), au même taux, supposé.
`vacation` paie des heures au taux que fixe la formation (201339, par défaut) ou l'action
à pilotage national (`code=201856`).

`retard_indice` reçoit l'indice payé en attendant (562 ici, celui d'avant la
promotion) : les bulletins de septembre et d'octobre le portent, et novembre rappelle
l'écart.

### Comparer au réel

Il faut l'extra `pdf` (`pip install "bpaye[pdf] @ git+https://github.com/antnardo/bpaye"`)
et les bulletins de l'ENSAP, nommés `AAAA_MM_BP_mois.pdf`, dans un dossier :

```python
paye.bull_dir = "Bulletins"
selection = paye.select(101000, 2025)          # le traitement brut de 2025
selection.somme().calcul, selection.somme().reel
```

`reel` vient des bulletins, rappels compris ; un avertissement dit quand des mois manquent.
`paye.select(lambda b: b.net_imposable, 2025)` somme une grandeur calculée, sans lecture.

Comparer mois par mois et rubrique par rubrique, c'est ce que fait
`examples/verifier.py` (voir le README) : les écarts restants désignent ce que la carrière
ne dit pas encore (une colle déclarée, une promotion payée en retard : section
précédente), ou une erreur de la paie.

### Un autre barème

Les taux, montants et barèmes viennent de `taux.toml`, dans le paquet. Pour calculer avec
d'autres valeurs (une hausse du point annoncée, un montant que bpaye n'a pas encore), un
fichier au même format remplace les sections qu'il donne, et `Paye` le reçoit :

```toml
# mon_bareme.toml : le point au 1er janvier 2027, hypothèse
[point]
type   = "Fixe"
unite  = "annuel"
values = [
  { date = 2023-07-01, valeur = 59.0734 },
  { date = 2027-01-01, valeur = 60.0 },
]
```

```python
from bpaye.config import Bareme

paye = Paye(agente, bareme=Bareme.depuis_fichiers("mon_bareme.toml"))
```

`nets_prevus(…, bareme=…)` le prend aussi. Une section remplace celle du paquet en
entier : y recopier ses valeurs passées.

## 6. Prévoir

```python
from bpaye.prevision import nets_prevus

for mois in nets_prevus("carriere.toml", "agent.toml", (2025, 9), 12):
    print(mois.annee, mois.mois, mois.net, mois.colles, mois.net_colles_externes)
```

Colles prévues comprises ; les événements de la section 5 n'y sont pas. Les colles
prévues n'entrent que dans la prévision : dans `Paye`, une colle se déclare avec
`paye.colle`.

## 7. Lire des bulletins

```python
from bpaye.pdf import extract_bulletin, extract_dr, find_pdfs

lu = extract_bulletin("Bulletins/2025_03_BP_mars.pdf")
lu["101000"], lu.get("200205_R"), lu["_net_payer"]
```

Un code suivi de `_R` est un rappel : une ligne marquée « RAPPEL ANNEE COURANTE » ou
« RAPPEL ANNEES ANTERIEURES », ou la reprise d'un code qui peut être rappelé. Les lignes
d'un même code s'additionnent (deux mois de colles rattrapés, deux indemnités de jury).
Les clés `_net_payer`, `_montant_imp`, `_totaux_mois`, `_total_ret`, `_total_pat`
viennent du pied du bulletin ; `_rappel_decompte` est le rappel sur rémunération
principale (« * RAPPELS : VOIR DÉCOMPTE »), détaillé par un décompte à part. Un code
absent de `codes.toml` est signalé par un avertissement et rangé dans `_unknown`.

Chaque montant est lu dans sa colonne (à payer, à déduire, pour information), à son
abscisse : un montant hors de la colonne de sa catégorie, comme un traitement repris « à
déduire », se compte en moins. `lu.lignes` garde chaque ligne imprimée, avec sa colonne.

La lecture se contrôle elle-même : chaque colonne doit retomber, au centime, sur son
total du pied (`ecarts_colonnes(lu)` ; `ecart_totaux(lu)` pour TOTAUX DU MOIS, rappel sur
décompte compris). Un écart, signe d'une ligne manquée, déclenche un avertissement. Les
cotisations patronales d'un mois de décompte de rappel ne se contrôlent pas : celles du
décompte entrent dans le total sans ligne sur le bulletin. `extract_dr` lit un décompte
de rappel, ligne par ligne pour chaque code connu ; `find_pdfs(dossier, année, siret)`
trouve les bulletins principaux d'une année, ceux d'un autre gestionnaire écartés par le
SIRET. Le détail de la lecture : [`lecture_pdf.md`](lecture_pdf.md).

### Reconnaître un bulletin sans carrière

`bpaye-lire BULLETIN.pdf [...]` (ou `bpaye.reconnaissance.reconnait`) n'a besoin ni de
`carriere.toml` ni d'`agent.toml`. Il lit l'en-tête du bulletin, caractère par caractère
et colonne par colonne (le numéro de sécurité sociale n'est jamais lu), puis :

- cherche le grade imprimé dans les grilles de bpaye, et vérifie que l'indice est celui
  de l'échelon imprimé au mois du bulletin ;
- calcule la fraction de traitement payée (traitement ÷ traitement d'un temps plein à cet
  indice), la zone d'indemnité de résidence, et le nombre d'enfants que paie le SFT ;
- relève ce que les lignes trahissent : CPGE, éducation prioritaire, professeur principal,
  heures supplémentaires, colles, Pacte, NBI, transport, PSC.

Ce qui ne se déduit pas devient une remarque, jamais une valeur devinée. Les bulletins
« INDEMNITAIRE » (complémentaires) et « VACATAIRE » (jurys, examens) n'ont pas de grille.

## 8. Ce qui est calculé

| Code | Rubrique | Règle | Texte |
| --- | --- | --- | --- |
| 101000 | traitement brut | indice majoré × point / 12, tronqué ; prorata au trentième d'un échelon pris en cours de mois ; fraction d'un temps partiel | décret 85-1148, art. 3 ; CGFP, L612-5 |
| 101070 | NBI | points × point / 12, à la fraction d'un temps partiel | décret 91-1229 ; décret 93-522, art. 3 |
| 102000 | indemnité de résidence | 3 %, 1 % ou rien du traitement, avec un indice plancher daté | décret 85-1148, art. 9 |
| 104000 | supplément familial | fixe + part du traitement selon les enfants | décret 85-1148, art. 10 bis |
| 200039 | transport | 50 %, puis 75 % depuis le 1/9/2023, plafonné | décret 2010-676, art. 3 |
| 200041 | forfait mobilités durables | 100, 200 ou 300 € en janvier | décret 2020-543 |
| 200205, 200576 | HSA, majoration de la 1re | neuvièmes d'octobre à juin ; classe normale du corps, +10 % HC/CE, +20 % sur une heure | décret 50-1253, art. 2 et 3 |
| 200207 | heures d'interrogation (colles) | 1/36 du taux annuel × 0,75, au code déclaré | décret 50-1253, art. 3 |
| 200215 | HSE | 1/36 × 1,25 (1,15 avant 2008) | décret 50-1253, art. 5 |
| 201241, 201717, 201300 | HSE de remplacement, de réussite au lycée | `paye.hse(…, code=…)`, au taux de l'HSE (supposé) | |
| 201339, 201856 | vacations de formation, actions à pilotage national | `paye.vacation`, au taux déclaré | décret 2010-235 ; décret 2014-1394 |
| 200364 | ISOE part fixe | second degré | décret 93-55 ; arrêté du 15/01/1993 |
| 201228, 202566 | ISOE part modulable | professeur principal, par niveau | arrêté du 15/01/1993, art. 2 |
| 200597 | IFP | CPGE seulement | décret 99-886 |
| 201914 | ISAE | professeurs des écoles | décret 2013-790 |
| 201883, 201882 | REP, REP+ (part fixe) | rentrée en éducation prioritaire | décret 2015-1087 |
| 202326 | prime d'attractivité | échelon de classe normale ; ni HC, ni CE, ni chaire supérieure | décret 2021-276 |
| 202209 | indemnité compensatrice de CSG | relevée sur les bulletins (`agent.toml`) | décret 2017-1889 |
| 200414 | CPE, indemnité forfaitaire | depuis le 1/9/2015, sauf de juillet 2016 à mars 2021 (indexée sur le point, montants non publiés) | décret 91-468 ; arrêté du 24/11/2015 |
| 202205 | PsyEN, indemnité de fonctions | selon la spécialité, depuis le 1/9/2017 | décret 2017-1552 ; arrêté du 10/11/2017 |
| 200413 | documentalistes, sujétions particulières | depuis le 1/9/2017 | décret 91-467 ; arrêté du 14/5/1991 |
| 202217, 202568 | directeurs d'école, ISS | part principale + part variable selon les classes, +20 % REP, +50 % REP+ ; depuis le 1/9/2018 | décret 83-644 ; arrêté du 12/9/2008 |
| 202475, 202476 | Pacte (part fonctionnelle ISOE, ISAE) | 1 250 € la part, par neuvième ; régime des heures supplémentaires | décret 93-55, art. 6 ; décret 2019-133, art. 1 |
| 201480 | GIPA | `Paye.gipa` ; années 2008 à 2023 | décret 2008-539, art. 3 et 10 |
| 202321 | équipement informatique | 176 € en janvier | décret 2020-1524 |
| 202354 | PSC (15 €) | jusqu'en avril 2026 | décret 2021-1164 |
| 202483, 202510 | participations de l'employeur à l'option santé et à la prévoyance | 50 % du coût déclaré de l'option, 5 € au plus ; 7 € (`agent.toml`, `[[psc]]`) | page du ministère sur la PSC |
| 700678, 700671 | ancienne mutuelle précomptée, avant la PSC | montants déclarés (`agent.toml`, `[[psc]]`) | |
| 101050 | pension civile | taux daté × traitement ; avec surcotisation, taux de l'art. D5 × traitement d'un temps plein | décret 2010-1749 ; code des pensions, L11 bis et D5 |
| 501080 | RAFP | 5 % des primes, dans la limite de 20 % du traitement de l'année | décret 2004-569 |
| 401201, 401301, 401501 | CSG, CRDS | `docs/csg.md` | CSS, L136-2 et L136-8 ; CGI, art. 154 quinquies ; ordonnance 96-50 |
| 453000, 011200 | heures supplémentaires : réduction de cotisations, exonération | `charges_impots.py` | |
| 604970 | transfert primes-points | 389 € par an depuis 2019 | décret 2016-588 |
| 720576 à 720580 | PSC santé MGEN | `docs/mgen.md` | |
| 558000 | prélèvement à la source | taux de l'agent × net imposable | |

Chaque montant est dans `taux.toml` avec sa source ; chaque indice et chaque durée dans
`grilles.toml`.

## 9. Limites

- **Les cotisations patronales**, que le bulletin imprime « pour information » (part
  employeur de la pension, de la RAFP, des cotisations maladie, famille…), sont hors du
  sujet de bpaye : elles ne changent pas ce que perçoit l'agent. La lecture des PDF les
  range à part (catégorie `patronal` de `codes.toml`, total `_total_pat`), sans les
  calculer, et la comparaison au calcul les écarte. Seule exception, la participation
  employeur à la PSC santé (720580) est calculée : elle entre dans l'assiette de la CSG
  et de la RAFP, et dans le net imposable.

- Directeurs d'école : ni la bonification indiciaire (décret 83-50), sans rubrique DGFiP
  trouvée, ni l'ISS avant septembre 2018, dont la rubrique n'est pas identifiée.
- Temps partiel : la réduction de la prime d'attractivité, des indemnités REP et de l'ISOE
  suit la règle générale, faute de clause propre ; la surcotisation n'est connue que
  depuis 2024 ; le transport, la PSC, le FMD et le Pacte sont versés entiers, aucune
  règle de temps partiel n'ayant été lue pour eux.
- GIPA : ni l'éligibilité (trois ans sur quatre, indice sommital), ni sa RAFP hors du
  plafond de 20 % ne sont calculées.
- Pas de contractuels ni d'enseignement privé.
- Deux règles de calendrier sont relevées sur des bulletins, aucun texte ne les donne :
  les HSA d'octobre et l'IFP de septembre payées le mois suivant (`academies.toml`,
  relevé à Paris et prêté aux autres académies), et le passage, en février 2026, d'une assiette de CSG
  tronquée à une assiette arrondie (`charges.NOUVEAU_LOGICIEL_PAIE`).
- La part solidaire de la PSC santé n'est vérifiée qu'au-dessus du plafond de la
  sécurité sociale.
- Les données marquées MANQUANT dans `docs/verification/` : chaires supérieures avant
  2010 ; texte de l'arrêté de 1957 sur la durée des chevrons (1 an, lu dans une décision
  du Conseil d'État qui le cite) ; plafonds de transport avant août 2016 ; taux de la
  pension civile avant 2011 ; réduction et exonération des heures supplémentaires du
  régime de 2007 (jusqu'en août 2012). bpaye refuse de calculer ces mois-là.
