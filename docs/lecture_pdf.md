# La lecture des bulletins PDF dans bpaye

Comment `bpaye.pdf` lit un bulletin de paye PAY18E de l'ENSAP, au niveau du code : ce
qu'il en tire, ce qu'il ignore, et pourquoi. Les montants et l'en-tête cités en exemple
sont fictifs (un agrégé de classe normale au 4e échelon, IM 547, en août 2026).

---

## 1. Ce qu'on lit, en une phrase

Un bulletin PDF de l'ENSAP est lu **comme une suite de morceaux de texte positionnés**
(abscisse, ordonnée, texte), dans l'ordre où le PDF les écrit. Les lignes de paye se
reconnaissent à leur code à six chiffres ; leur montant est le premier nombre qui les
suit ; le pied du bulletin (totaux, net à payer, montant imposable) se lit par **zones de
coordonnées**. Une somme de contrôle vérifie que rien n'a été manqué.

La **colonne** de chaque montant (à payer, à déduire, pour information) se lit à son
abscisse, et chacune des trois colonnes se contrôle sur son total du pied. Le module ne
lit **pas les balises du PDF** (le PDF est pourtant balisé, voir § 13). **L'en-tête**
(grade, échelon, indice, enfants…) est lu par `bpaye.reconnaissance` (§ 16).

---

## 2. Le document PAY18E

### 2.1 Origine

- Produit par la DGFiP (paie des agents de l'État), mis à disposition sur l'ENSAP.
- Métadonnées du PDF : `Creator: OpenText Exstream`, `Title:
  PAY18E__…_bulletin_de_paie_ENSAP`, `Author: Registered to: DGCP`.
- Une page par bulletin (les bulletins lus jusqu'ici n'en ont qu'une).
- Taille de page : 595 × 842 points (A4) ou 595 × 864 ; les coordonnées utiles ne
  dépendent pas de la hauteur, le haut de page servant d'origine.

### 2.2 Deux sortes de documents

| Document | Nommage conseillé | Contenu | Lu par |
| --- | --- | --- | --- |
| Bulletin de paye (BP) | `AAAA_MM_BP_mois.pdf` | les lignes du mois | `extract_bulletin` |
| Décompte de rappel (DR) | `AAAA_MM_DR_mois.pdf` | le détail, mois par mois, d'un rappel sur rémunération principale | `extract_dr` |

Un même mois peut avoir **plusieurs BP** : le bulletin principal et un ou plusieurs
bulletins complémentaires (grade imprimé « INDEMNITAIRE » ou « VACATAIRE »). L'ENSAP les
rend sous le même nom ; c'est le système qui suffixe le second téléchargement (« -1 » sous
macOS, « (1) » dans la plupart des navigateurs). Le
suffixe dépend donc de l'ordre des téléchargements, pas de la nature du bulletin : le
principal se reconnaît à sa ligne 101000 (traitement brut), comme le fait `Paye.select`.

### 2.3 Versions

La version est imprimée **à la verticale**, une lettre par morceau, le long du bord droit
(x ≈ 578, y de 693 à 762) : `P A Y 1 8 E - V 4 . 2 - 1 6 0 3 2 0 2 6`. Le dernier groupe
est une date de version du gabarit (ici 16/03/2026).

| Version | Période observée | Particularité utile à la lecture |
| --- | --- | --- |
| V1.4 | jusqu'à janvier 2018 | non lue : aucun bulletin de test |
| V1.6 | jusqu'à septembre 2018 | non lue : aucun bulletin de test |
| V2.0 | jusqu'à décembre 2018 | non lue : aucun bulletin de test |
| V2.1 | jusqu'à mars 2019 | non lue : aucun bulletin de test |
| V2.3 | d'avril 2019 à janvier 2026 | TOTAUX DU MOIS et total des retenues dans deux morceaux séparés |
| V4.0 | à partir de février 2026 | les deux montants dans un même morceau : `3350,00      1000,00` |
| V4.2 | 2026 | comme V4.0 ; l'espace et la lettre suivante se chevauchent d'environ un point |

`SUPPORTED_VERSIONS = {"V2.3", "V4.0", "V4.2"}` ; une autre version déclenche un
avertissement mais la lecture continue. Les versions d'avant 2019 n'y sont pas faute
de bulletin pour vérifier leur structure ; un bulletin de chacune suffirait à les
ajouter, si la lecture y retrouve TOTAUX DU MOIS.

---

## 3. Cartographie de la page

Coordonnées en points, origine **en haut à gauche** (convention de pdfplumber : `top`).
Relevées sur des bulletins V2.3 à V4.2 ; elles n'ont pas bougé entre versions.

```text
y ≈ 10   BULLETIN DE PAYE                                N° ORDRE
y ≈ 22   AOUT 2026  (« MOIS DE »)                        151,67 H (« TEMPS DE TRAVAIL », x ≈ 521)
y ≈ 50   AFFECTATION (x 88)        LIBELLÉ (x 337)       SIRET (x 528)
y ≈ 60   GESTION / POSTE
y ≈ 89–95  en-têtes de la ligne d'identification (labels sur deux lignes)
y ≈ 106  ligne d'identification : MIN. | NUMÉRO | CLÉ | N°DOS | GRADE | ENFANTS | ÉCH. | INDICE | NBI | TEMPS PARTIEL
y ≈ 125  CODE | ÉLÉMENTS | À PAYER | À DÉDUIRE | POUR INFORMATION
y ≈ 135… lignes de paye, une tous les ≈ 9 points
y ≈ 603  * RAPPELS : VOIR DÉCOMPTE   (montants seulement s'il y a un DR)
y ≈ 629  coût total employeur (x 220) | TOTAUX DU MOIS : à payer (x 374) | à déduire (x 447) | pour information (x 521)
y ≈ 647  NET À PAYER (x 415)                             TOTAL CHARGES PATRONALES
y ≈ 666  BASE SS DE L'ANNÉE | BASE SS DU MOIS
y ≈ 695  MONTANT IMPOSABLE DE L'ANNÉE (x 26) | DU MOIS (x 125), valeurs à y ≈ 713
y ≈ 737  COMPTABLE ASSIGNATAIRE
y ≈ 774  MIS EN PAIEMENT LE   (valeur y ≈ 786 : « 25 AOUT 2026 »)
y ≈ 810  VIRÉ AU COMPTE N°
x ≈ 578, y 693–762 : version, à la verticale
```

### 3.1 La ligne d'identification (y ≈ 106) — non lue aujourd'hui

| Colonne | x du libellé | x de la valeur | Exemple (fictif) | Remarque |
| --- | --- | --- | --- | --- |
| MIN. | 16 | 15 | `206` | ministère (206 : Éducation nationale) |
| NUMÉRO | 85 | 44 | *(effacé)* | **NIR de l'agent : donnée personnelle, ne jamais l'extraire** |
| CLÉ | 167 | 166 | *(effacé)* | clé du NIR |
| N°DOS | 189 | 191 | `00` | numéro de dossier |
| GRADE | 264 | 214 | `PROF. AGREGE CN` | libellé abrégé du grade |
| ENFANTS À CHARGE | 342 | 348 | `00` | |
| ÉCH. | 380 | 380 | `04` | échelon |
| INDICE OU NB. D'HEURES | 417 | 415 | `0547` | indice majoré (ou heures pour un vacataire) |
| TAUX HORAIRE OU NBI | 465 | ≈ 470 | *(vide)* | points de NBI, ou taux horaire |
| TEMPS PARTIEL | 523 | ≈ 525 | *(vide)* | quotité |

Piège : la fusion des caractères en morceaux (§ 4) colle des valeurs voisines. Sur les
bulletins réels on obtient `206  <NIR>` en un seul morceau, ou `00  PROF.CHAIRE SUPER.`.
Lire cette ligne demande donc de **repartir des caractères** et de les ranger par colonne
d'abscisse, pas des morceaux.

La valeur « TEMPS DE TRAVAIL » (x ≈ 521, y ≈ 30) vaut `151,67 H` (temps plein) ou
`+ DE 120 H` sur d'anciens bulletins.

---

## 4. Étape 1 : des caractères aux morceaux (`_pages`)

pdfplumber (licence MIT, extra `pdf`) donne, page par page, la liste des caractères avec
leur boîte (`x0`, `x1`, `top`) **dans l'ordre du flux du PDF**. `_pages` les regroupe en
morceaux :

```python
_DY = 1.5      # même ligne : |Δtop| ≤ 1,5 pt
_ECART = 6.0   # même morceau : écart horizontal entre −3 et +6 pt
```

- Un caractère rejoint le morceau courant s'il est sur la même ligne et le suit à moins
  d'une largeur de caractère. Un **recul** jusqu'à 3 points est toléré : depuis 2026,
  l'espace et la lettre suivante se chevauchent d'environ un point.
- Si l'écart dépasse 1 point, une espace est insérée (le flux n'en contient pas toujours).
- Résultat : `101000 TRAITEMENT BRUT` forme un morceau, le symbole `€` (x ≈ 361) et le
  montant (x ≈ 385 à 457 selon la colonne) en forment d'autres.
- Chaque morceau devient `(x0, top, texte)` (type `Span`).

**On garde l'ordre du flux**, sans trier par position. PAY18E écrit le bulletin ligne de
paye par ligne de paye : code et libellé, puis `€`, puis montant. Un tri par position
mélangerait les colonnes et les lignes voisines dont les `top` diffèrent d'un point (le `€`
est à `top` + 1 par rapport au montant).

---

## 5. Étape 2 : les lignes de paye (`extract_bulletin`)

Tous les morceaux de toutes les pages sont mis bout à bout (`lines`), puis parcourus.

### 5.1 Reconnaître une ligne

`_CODE_RE = r"^\d{6}\s+.+"` : six chiffres, une espace, un libellé. Le code est
`line[:6]`, le libellé `line[7:]`.

### 5.2 Trouver le montant

Dans les **cinq morceaux suivants**, jusqu'à la ligne de paye suivante :

1. on saute `€` et les morceaux vides ;
2. le premier morceau qui a la forme d'un montant (`_AMOUNT_RE = r"^-?[\d][\d\xa0 ]*,\d{1,2}$"`,
   espaces et espaces insécables acceptés) est le montant ;
3. le morceau qui suit le montant est regardé pour une **mention de rappel**.

Un montant se convertit par `parse_amount` : espaces retirées, virgule → point.

**La colonne** se lit à l'abscisse du bord gauche du montant (`colonne(x)`) :

| Colonne | Abscisse relevée | Borne |
| --- | --- | --- |
| à payer (`payer`) | 385,4 | x < 430 |
| à déduire (`deduire`) | 457,4 | 430 ≤ x < 500 |
| pour information (`information`) | 517 à 520 | x ≥ 500 |

Relevé sur des bulletins de 2019 à 2026 (V2.3 à V4.2) : chaque colonne a une
abscisse fixe, et la colonne concorde toujours avec la catégorie de `codes.toml` (revenu à
payer, retenue à déduire, patronal pour information ; les lignes spéciales 558000 et
800001 à déduire, 011100, 011200, 011300 et 200012 pour information).

Un montant hors de la colonne de sa catégorie se compte **en sens inverse** : un
traitement repris « à déduire » diminue le traitement. Les rappels négatifs s'écrivent,
eux, avec un signe moins (`-22,00`), qui est conservé.

### 5.3 Rappels

Un montant est rangé sous `CODE_R` au lieu de `CODE` quand :

- le libellé contient `RAPPEL` (« RAPPEL ANNEE COURANTE », « RAPPEL ANNEES ANTERIEURES »,
  parfois tronqué) ;
- ou le morceau qui suit le montant contient `RAPPEL` (la mention est parfois écrite
  après le montant, sur la même ligne) ;
- ou le code a **déjà été lu** dans ce bulletin et `codes.toml` le déclare rappelable
  (`rappel = true`). Exemple réel : en novembre 2021, les HSA d'octobre suivent celles
  du mois, sans mention.

Plusieurs lignes d'un même code (ou d'un même `CODE_R`) **s'additionnent** : deux rappels
de colles de mois différents, deux indemnités de jury.

### 5.4 Codes inconnus

Un code absent de `codes.toml` n'est **pas** ajouté aux montants : il va dans
`inconnus` (`_unknown`), avec un avertissement `code … inconnu (…), à ajouter à
codes.toml`. Il manquera alors au contrôle des totaux (§ 7), ce qui le rend visible.

Un code recodifié reste à connaître : l'ISOE modulable, 201228 jusqu'en août 2024 puis
202566 d'après INGRES (l'annexe 14 B 2026 dit « Recodifiée en 2566 »), se rencontre encore
sous son ancien code en 2026. Les deux sont dans `codes.toml`.

---

## 6. Étape 3 : le pied du bulletin

Lu **par zones** sur la première page : pour chaque champ, le premier morceau dont le coin
(x0, top) tombe dans la zone, et qui contient un montant.

| Champ (`BulletinLu`) | Clé dict | x | y | Remarque |
| --- | --- | --- | --- | --- |
| `totaux_mois` | `_totaux_mois` | 365–440 | 621–634 | en V4.x, le même morceau porte aussi le total des retenues |
| `total_ret` | `_total_ret` | 438–475 | 621–634 | morceau séparé en V2.3 |
| `total_pat` | `_total_pat` | 510–545 | 621–634 | |
| `net_payer` | `_net_payer` | 395–475 | 638–652 | |
| `rappel_decompte` | `_rappel_decompte` | 365–440 | 595–612 | ligne « * RAPPELS : VOIR DÉCOMPTE », à payer |
| `rappel_decompte_ret` | `_rappel_decompte_ret` | 510–545 | 595–612 | sa part de retenues, négative |
| `montant_imp` | `_montant_imp` | 100–145 | 705–720 | montant imposable **du mois** |
| `total_dupercu` | `_total_dupercu` | — | — | regex `TOTAL DU-PERCU : …` sur tout le texte |

Les montants avec espace de milliers (`2 504,19`) sont lus par la regex `multi_re`, qui
trouve tous les montants d'un morceau.

Non lus : coût total employeur, base SS de l'année et du mois, montant imposable de
l'année, date de mise en paiement, comptable.

---

## 7. Le contrôle de la lecture (`ecart_totaux`, `ecarts_colonnes`)

Chaque colonne se compare au total du pied, au centime. Les lignes de net (011…) ne
comptent dans aucun total ; les codes inconnus ne sont pas comptés, pour que leur
absence se voie.

```text
à payer          : TOTAUX DU MOIS        − montants « à payer »   − rappel sur décompte
à déduire        : total des retenues    − montants « à déduire »  (prélèvement à la source compris)
pour information : total patronal        − montants « pour information »
```

- 0 : la colonne a été lue entièrement.
- Non nul : une ligne a été manquée (code inconnu, montant mal accroché) ou lue deux
  fois. `extract_bulletin` émet un avertissement qui nomme la colonne.
- `None` : rien à contrôler.

Deux nuances, relevées sur les mois de **décompte de rappel** :

- à déduire : en 2019 (V2.3), le total ne comptait pas la part de retenues du décompte ;
  en 2026 (V4.x), il la compte. Les deux sommes sont acceptées ;
- pour information : le total inclut les cotisations patronales du décompte, qui n'ont
  pas de ligne sur le bulletin. Ce contrôle est sauté ces mois-là.

Sur des bulletins réels de 2019 à 2026 : à payer et à déduire nuls partout, pour information
nul partout où il se contrôle.

`ecart_totaux` accepte encore une lecture sous forme de `dict` (ancienne lecture) : il se
rabat alors sur les catégories de `codes.toml`.

---

## 8. Le résultat : `BulletinLu`

`@dataclass(frozen=True, slots=True)`, qui implémente aussi `Mapping[str, Any]` :

| Accès | Contenu |
| --- | --- |
| `lu.montants["101000"]`, `lu["101000"]` | montant du code (positif) |
| `lu["200205_R"]` | rappel de ce code |
| `lu.net_payer`, `lu["_net_payer"]` | pied ; la clé `_…` n'existe que si la valeur a été lue |
| `lu.inconnus`, `lu["_unknown"]` | `(code, libellé, montant)` des codes inconnus |
| `lu.lignes` | chaque ligne imprimée : `LigneLue(code, libelle, colonne, montant, rappel)`, montant au signe imprimé |

Le double accès garde justes les scripts écrits quand la lecture rendait un `dict`, mais
la lecture n'est plus modifiable. Pour sérialiser : `dict(lu)`.

---

## 9. Trouver les fichiers : `find_pdfs`, `find_dr_pdfs`, SIRET

- Nommage attendu : `AAAA_MM_BP_….pdf` et `AAAA_MM_DR_….pdf`.
- Le dossier et ses **sous-dossiers directs** sont parcourus (un sous-dossier par
  employeur, par exemple).
- Avec un SIRET (`siret` d'`agent.toml`), un fichier n'est gardé que si ce SIRET figure
  dans son en-tête (morceaux de 14 chiffres à y < 120) : cela écarte les bulletins d'un
  autre employeur (des vacations payées par un autre établissement, par exemple).
- Rend `{mois: [chemins]}`, triés par nom.

---

## 10. Les décomptes de rappel (`extract_dr`)

Un DR détaille un rappel mois par mois, en colonnes `DÛ` / `PERÇU`.

1. Chaque page se lit à part (ses ordonnées n'ont de sens que sur elle).
2. La ligne d'en-têtes est repérée par le premier morceau `DÛ` ; ses colonnes `DÛ` et
   `PERÇU` sont les morceaux de même ordonnée (± 5 pt).
3. Les mois couverts sont les noms de mois **juste au-dessus** (moins de 50 pt) de cette
   ligne, chacun associé à l'année à 4 chiffres la plus proche à sa droite.
4. Chaque mois est rattaché à la colonne `DÛ` la plus proche.
5. Sont lues (`DR_ROW_CODES`) les quatre lignes des décomptes relevés, TRAITEMENT BRUT
   (101000), RETENUE PC (101050), INDEMNITE DE RESIDENCE (102000), SUPP FAMILIAL
   TRAITEMENT (104000), et toute ligne dont le libellé est celui d'un revenu ou d'une
   retenue de `codes.toml` (NBI, indemnité rappelée).
6. Correction = |DÛ| − |PERÇU| ; un PERÇU absent (colonne vide) vaut 0.
7. Rend `{(année, mois): {code: correction}}`, sommé sur les pages.

Le total à payer d'un DR apparaît aussi sur le BP du mois (ligne « * RAPPELS : VOIR
DÉCOMPTE ») : c'est ce montant que `ecart_totaux` déduit.

---

## 11. Cas particuliers rencontrés

| Cas | Traitement |
| --- | --- |
| Rappel sans mention (HSA d'octobre en novembre 2021) | reprise d'un code rappelable = rappel |
| Mention de rappel après le montant | lue dans le morceau suivant |
| Deux lignes du même code (jurys, colles de deux mois) | additionnées |
| V4.x : TOTAUX et retenues dans un même morceau | deux montants dans le morceau |
| Chevauchement espace/lettre (2026) | recul de 3 pt toléré dans la fusion |
| Bulletin complémentaire du même mois | même lecture ; le principal a une ligne 101000 |
| Code recodifié (201228 → 202566) | les deux doivent être dans `codes.toml` |
| Montant négatif (reprise) | signe moins conservé |
| Montant hors de la colonne de sa catégorie | compté en sens inverse |
| Bulletins homonymes (« -1 » de macOS) | le principal a une ligne 101000 |

---

## 12. Ce que la lecture ignore

- **L'en-tête**, dans `extract_bulletin` : il est lu par `bpaye.reconnaissance` (grade,
  échelon, indice, enfants, NBI, temps partiel, temps de travail, mois, taux du
  prélèvement à la source ; § 16). L'affectation et le libellé de l'établissement ne sont
  lus nulle part.
- Le net social (011300 est lu comme une ligne spéciale, sans usage), la base SS, le
  montant imposable de l'année, le coût employeur, la date de paiement.

---

## 13. Le balisage PDF

Le PDF est **balisé** (`MarkInfo: Marked = true`, `StructTreeRoot` présent). pdfplumber
expose l'arbre (`page.structure_tree`) :

```text
Document > Part > Art >
  Table (en-tête, TR/TD) …
  Table : TR [TH ×5]                       ← CODE | ÉLÉMENTS | À PAYER | À DÉDUIRE | POUR INFO
          TR [TD, TD, TD, TD] × n          ← une ligne de paye : code, libellé, (€), montant
  …
```

Chaque `TD` renvoie à un ou plusieurs *marked content ids* (`mcids`), qui relient les
caractères à la cellule. **bpaye ne s'en sert pas** :

- la lecture par flux et positions marche sur tous les bulletins depuis 2019, y compris
  ceux de V2.3, dont le balisage n'a pas été vérifié ;
- un PDF anonymisé en retirant du texte garde rarement un arbre cohérent, alors que la
  lecture par positions s'en moque.

Faut-il les lire ? Non, à ce stade. Elles apporteraient la colonne de chaque montant et
le découpage de l'en-tête en cellules ; or l'abscisse donne déjà la colonne (§ 5.2), sans
exception sur les bulletins relevés, et l'en-tête se découpe par colonnes de caractères (§ 16). Un
PDF anonymisé, ou réécrit par un autre outil, peut garder un arbre incohérent (des `mcids`
qui ne pointent plus sur le bon texte) : la lecture deviendrait plus fragile pour un gain
nul. Les balises ne serviraient qu'à **vérifier** la lecture par positions sur un PDF
intact, en second avis.

---

## 14. Anonymiser un bulletin de test

La lecture n'a besoin que :

- des morceaux `CODE LIBELLÉ`, `€` et montant de chaque ligne, **dans l'ordre du flux** ;
- des montants du pied à leurs coordonnées (§ 6) ;
- des lettres verticales de la version (§ 2.3) ;
- pour les tests du SIRET, d'un morceau de 14 chiffres en haut de page.

On peut donc effacer sans risque : le NIR et sa clé, l'affectation, le libellé de
l'établissement, le SIRET (sauf test dédié), le compte bancaire, le comptable, la base
SS de l'année. L'arbre de balises n'est pas nécessaire.

L'académie ou le département ne sont pas lus : la zone d'indemnité de résidence se
déduit du montant de la ligne 102000 rapporté au traitement (3 %, 1 % ou 0), pas d'une
adresse. Inutile de les laisser.

Plutôt qu'anonymiser un vrai bulletin, les tests en **écrivent un faux** avec
reportlab_layout (`tests/conftest.py`, `_ecrit_faux_bulletin`) : Courier-Bold 9 pt, code
à x = 16,4, libellé à 53, `€` à 361,4, montant à 385,4, lignes espacées de 9 pt, pied aux
coordonnées du § 6, version à la verticale. Ce PDF fait quelques kilo-octets et ne
contient rien de réel. Un vrai bulletin anonymisé reste utile pour vérifier qu'aucune
version nouvelle ne change la géométrie.

---

## 15. Limites

1. La géométrie (colonnes, zones du pied, ligne d'identification) est celle des versions
   V2.3 à V4.2 : une nouvelle version de PAY18E peut la changer. Un écart dans les
   contrôles du § 7 le signale ; un bulletin de test anonymisé par version le vérifierait.
2. Plusieurs codes sont lus sans être calculés : majorations et indexation outre-mer, HSE
   particulières, vacations de formation, options et prévoyance PSC, ancienne adhésion
   MGEN précomptée (`codes.toml`, notes « non calculé »).
3. Le mois d'un bulletin vient du nom de fichier pour `find_pdfs` ; seule la
   reconnaissance (§ 16) le lit dans le PDF.

---

## 16. Lire un bulletin sans carrière : la reconnaissance

Le module `bpaye.reconnaissance` (voir sa docstring) lit un bulletin seul, sans
`carriere.toml` ni `agent.toml`, et en déduit ce qu'il peut :

- de l'**en-tête** : grade, échelon, indice majoré, enfants, NBI, temps partiel ;
- des **grilles** de bpaye : le corps et la grille dont l'échelon a cet indice au mois du
  bulletin, avec un contrôle de cohérence avec l'échelon imprimé ;
- du **point d'indice** : la quotité (traitement ÷ indice × point) ;
- des **lignes** : zone de résidence, CPGE (IFP), éducation prioritaire, professeur
  principal, heures supplémentaires et colles, Pacte, transport, MGEN, taux du
  prélèvement à la source.

Ligne de commande : `bpaye-lire BULLETIN.pdf [...]` (extra `pdf`).

Vérifié sur des bulletins réels de 2019 à 2026 : grade et échelon reconnus partout où il
y a un traitement ; les bulletins « INDEMNITAIRE » et « VACATAIRE » dits tels ; enfants de
l'en-tête et enfants payés par le SFT concordants. Un indice supérieur à celui de
l'échelon imprimé, comme après une promotion où l'ancien indice est conservé à titre
personnel, devient une remarque.
