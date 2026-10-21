# Anonymiser un bulletin de paye

Un bulletin nouveau est ce qui fait avancer bpaye : une ligne que personne ne connaît
encore, une indemnité propre à une académie, un gabarit qui change. Pour le joindre à une
issue sans rien dire de l'agent, le dépôt fournit `scripts/anonymise_bulletin.py`. Il
efface ce qui identifie l'agent et garde tout le reste, lignes inconnues comprises.

Le script est autonome : il n'importe pas bpaye, et peut se lire d'une traite pour
vérifier ce qu'il efface.

## Utiliser le script

Depuis le dépôt, avec [uv](https://docs.astral.sh/uv/) :

```bash
uv run scripts/anonymise_bulletin.py 2026_08_BP_aout.pdf
```

`uv` installe les deux dépendances que le script déclare lui-même (pdfplumber, et
reportlab_layout avec son extra `pdf`), dans un environnement à part. Le script écrit
`2026_08_BP_aout_anonyme.pdf` à côté de l'original, ou dans le fichier donné en second
argument.

- **L'original n'est jamais modifié** : il est seulement lu.
- **Aucun fichier n'est écrasé** : si la sortie existe déjà, le script s'arrête sans rien
  écrire.

Il affiche ce qu'il a effacé, en nombre d'éléments, jamais leur contenu :

```text
2026_08_BP_aout_anonyme.pdf
  effacé : DataMatrix (528 éléments)
  effacé : IBAN et BIC (64 éléments)
  effacé : NIR au pied (24 éléments)
  effacé : NIR et clé (21 éléments)
  effacé : affectation, établissement, SIRET, poste (111 éléments)
  effacé : cumuls de l'année (base SS, montant imposable) (17 éléments)
  effacé : image (IBAN et BIC) (1 éléments)
  effacé : nom et adresse (54 éléments)
  effacé : numéro d'ordre (8 éléments)
Aucun identifiant retrouvé. Relisez la sortie avant de la partager.
```

Trois issues :

- **« Aucun identifiant retrouvé »** : relire la sortie, puis la partager.
- **« ÉCHEC »** : la sortie contient encore un identifiant (sa nature est donnée, pas sa
  valeur). Ne pas la partager, la supprimer, et signaler le cas par une issue sans joindre
  le bulletin.
- **« Attention, rien à effacer dans : … »** : une zone était vide. Soit le bulletin avait
  déjà été nettoyé, soit son gabarit a changé et le nom ou l'affectation sont ailleurs ;
  dans le doute, ne pas partager.

## Ce qui disparaît

Le script efface une **liste noire** de zones, relevées sur 97 bulletins PAY18E de 2022 à
2026 (versions V2.3 à V4.2). Les ordonnées bornent la ligne de base des caractères, en
points depuis le haut de la page (595 × 864).

| Zone | Ligne de base | Abscisse |
| --- | --- | --- |
| numéro d'ordre du bulletin | 15 à 23 | ≥ 500 |
| affectation, établissement, SIRET, poste | 62 à 89 | toute la largeur |
| NIR et sa clé, dans la ligne d'identification | 107 à 121 | 40 à 185 |
| NIR répété au pied | 643 à 654 | < 200 |
| cumuls de l'année : base SS, montant imposable | 677 à 731 | < 100 |
| nom et adresse (fenêtre d'enveloppe) | 687 à 734 | 220 à 480 |
| IBAN et BIC | 819 à 851 | toute la largeur |

S'y ajoutent, où qu'ils soient :

- **le code-barres DataMatrix**, reconnu à sa police : il reprend tout le bulletin, NIR
  compris ;
- **une image qui touche une zone** ; les logos restent ;
- **tout le catalogue du PDF d'origine** : métadonnées, balises, textes de remplacement.

Les **étiquettes du formulaire** (« NUMÉRO », « SIRET », « AFFECTATION »…, en Helvetica de
5 à 6 points) restent, même dans ces zones : la sortie se relit comme un bulletin.

## Ce qui reste, et qu'il faut peser

Le reste du bulletin est intact :

- le service gestionnaire (DDFIP et département) et le comptable ;
- le grade, l'échelon, l'indice, les enfants à charge, le temps partiel ;
- toutes les lignes de paye, le taux du prélèvement à la source, les totaux et les
  montants du mois ;
- le mois payé et la date de mise en paiement.

Pris ensemble, ces éléments peuvent restreindre le nombre d'agents possibles. Une ligne
de paye peut aussi nommer quelqu'un : une opposition, une pension alimentaire. **Relire la
sortie avant de la partager.**

## Comment il fonctionne

Le bulletin n'est pas masqué, il est **filtré**. Un cache noir posé sur un PDF laisse le
texte dessous, que n'importe quel lecteur retrouve, et le catalogue du PDF garde des
métadonnées et des balises. Le script demande donc à reportlab_layout (`redact_pdf`)
d'écrire une copie de la page d'où chaque élément refusé est retiré du flux de contenu :
un glyphe, une image, un tracé. Le reste n'est pas touché : cadres, couleurs, polices,
logos, et l'ordre des caractères, celui dans lequel bpaye les lit.

Le tri tient en une fonction, `raison(élément, hauteur)`, qui dit pourquoi un élément est
effacé, ou rien s'il reste :

1. une image qui touche une zone est effacée, les autres restent ;
2. un tracé (cadre, trait, fond) reste ;
3. un caractère du DataMatrix est effacé ;
4. une étiquette du formulaire reste ;
5. un caractère dont la ligne de base tombe dans une zone est effacé.

Les zones bornent la **ligne de base** plutôt que le haut des caractères : c'est elle que
reportlab_layout mesure sans ambiguïté, quand le haut d'un caractère dépend des métriques
que déclare le PDF lu.

## Le contrôle

Le script relit ensuite la sortie avec pdfplumber, indépendamment du filtrage, et échoue
s'il y trouve :

- un numéro au format d'un NIR (sexe, année, mois, département, commune, ordre, clé) ;
- un numéro au format d'un IBAN (deux lettres, la clé, des groupes de quatre, au moins
  14 chiffres) ;
- un numéro de dix chiffres ou plus, ou un mot de quatre lettres ou plus, lu dans une zone
  effacée de l'original (sauf les mots génériques d'une adresse : « RUE », « AVENUE »…) ;
- un élément encore dans une zone.

Le NIR et l'IBAN sont donc attrapés par leur forme, même si leur zone venait à manquer.
Le nom et l'affectation ne le sont pas : ils ne se reconnaissent qu'à leur place, d'où
l'avertissement quand une zone est vide.

## Limites

- **Le gabarit PAY18E seul**, celui des bulletins de l'ENSAP. Les décomptes de rappel ont
  une autre disposition et ne sont pas prévus.
- **Les zones sont des positions** : un gabarit nouveau qui déplacerait le nom passerait
  sans effacement, l'avertissement de zone vide étant le seul signal.
- **Une image n'est pas masquée par morceaux** : elle part ou reste entière.
- **Une police que reportlab_layout ne sait pas mesurer** (écriture verticale, certaines
  polices composites) le fait refuser plutôt que deviner : le script s'arrête sans sortie.
- **Les sous-ensembles de police embarqués** restent dans le fichier : on sait quels
  caractères existaient, pas où ni dans quel ordre.

## Voir aussi

- [`lecture_pdf.md`](lecture_pdf.md) : comment bpaye lit un bulletin, et ce qu'une sortie
  doit garder pour rester lisible (§ 14).
- Le script lui-même, [`scripts/anonymise_bulletin.py`](../scripts/anonymise_bulletin.py).
