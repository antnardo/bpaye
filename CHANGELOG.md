# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et la
[gestion sémantique de version](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté

- **Lire un bulletin seul** : `bpaye-lire` et `bpaye.reconnaissance.reconnait` lisent
  l'en-tête d'un bulletin (grade, échelon, indice, enfants, temps partiel, taux du
  prélèvement à la source), situent l'indice dans les grilles, et en déduisent la
  fraction de traitement payée, la zone de résidence, les enfants payés par le SFT et les
  situations que trahissent les lignes, sans carrière ni `agent.toml`.
- **Lecture des PDF** : la colonne de chaque montant (à payer, à déduire, pour information),
  lue à son abscisse, avec un contrôle des trois totaux du pied (`ecarts_colonnes`) ; un
  montant hors de la colonne de sa catégorie se compte en moins. `BulletinLu.lignes`
  garde chaque ligne imprimée. Les décomptes de rappel sont lus pour tout code connu.
- **Codes** signalés par Bruno Pagani (outre-mer, HSE particulières, vacations de
  formation, actions à pilotage national, options et prévoyance PSC, ancienne adhésion
  MGEN) : lus, non calculés.
- **ISOE et IFP indexées sur le point** (type de barème `IndexePoint`), proposé par Bruno
  Pagani : chaque montant d'arrêté suit le point, au centime du mois d'avant ; les
  montants relevés sur les bulletins deviennent des montants calculés, datés de la hausse
  du point (juillet 2016 et juillet 2023, et non septembre).
- **Options et prévoyance de la PSC, ancienne mutuelle** (`[[psc]]` d'`agent.toml`) :
  participations de l'employeur aux options et à la prévoyance, cotisation de
  prévoyance, ancienne adhésion MGEN précomptée, aux montants du contrat de l'agent.
- **HSE d'autres rubriques et vacations** : `paye.hse(…, code=…)` pour le remplacement de
  courte durée et la réussite au lycée ; `paye.vacation` pour les vacations de formation
  et les actions à pilotage national, au taux déclaré.
- **Retards habituels de la paie, par académie** (`academies.toml`) : les HSA d'octobre
  et l'IFP de septembre payées le mois suivant ne sont plus codées en dur ; un défaut
  relevé à Paris, toutes les académies de l'art. R222-2 et les lycées de la Défense.
  `agent.toml` choisit l'académie à chaque date (`[[academie]]`) et ajoute ses propres
  retards (`[[retards]]`, un FMD payé en février par exemple).

### Corrigé

- **MGEN** (contribution de Bruno Pagani) : part solidaire (720577) calculée sur la
  rémunération brute du mois et non sur le seul traitement, vérifiée sous le plafond sur un
  bulletin réel ; action sociale et aide aux retraités (720578, 720579) à 2 % et 3 %
  de la cotisation hors taxe de solidarité additionnelle (13,27 %, code de la sécurité
  sociale, L862-4) ; les parts calculées depuis la cotisation d'équilibre (75,40 € en 2026,
  78,70 € en 2027 et 82,43 € en 2028, de source syndicale).
- **201228**, ancien code de l'ISOE modulable encore porté en 2026 : il sortait de la
  lecture.

## [0.2.0] - 2026-10-19

Première version publiée, sur GitHub seulement (pas sur PyPI) : le code y est depuis le
18 octobre 2026.

### Ajouté

- **Carrière** : grilles indiciaires datées des agrégés (classe normale, hors classe,
  classe exceptionnelle), des chaires supérieures et des corps à la grille des certifiés
  (certifiés, professeurs des écoles, PLP, PEPS, CPE, PsyEN), composées des indices
  bruts, du barème des indices majorés et des hors-échelle, depuis 2005 ; avancements à
  l'ancienneté, au choix et au grand choix, accélérations ; reclassements par tables
  (2017, 2023) ; promotions de grade et de corps ; rentrées (CPGE et ORS, éducation
  prioritaire, professeur principal, temps partiel, NBI, Pacte, fonctions).
- **Bulletin** : traitement, NBI, indemnité de résidence, SFT, ISOE ou ISAE, prime
  d'attractivité, REP et REP+, IFP des CPGE, Pacte, heures supplémentaires et colles,
  indemnités des CPE, des PsyEN, des documentalistes et des directeurs d'école, pension
  civile (surcotisation à temps partiel comprise), RAFP, CSG et CRDS, transfert
  primes-points, PSC santé, prélèvement à la source, GIPA ; règles d'arrondi des
  bulletins réels.
- **Événements** : promotion payée en retard, colles déclarées, heures supplémentaires
  effectives, erreur reprise, GIPA (`Paye.retard_indice`, `Paye.colle`, `Paye.hse`,
  `Paye.erreur`, `Paye.gipa`).
- **Point d'entrée** : `agente = load_agent("agent.toml")`, puis
  `agente.load_carriere("carriere.toml")` ; `Paye(agente)` en calcule les bulletins.
- **Prévision** : la paye des mois à venir, colles prévues comprises
  (`prevision.nets_prevus`).
- **Lecture des bulletins PDF** (extra `pdf`, pdfplumber) : lignes, rappels, pied du
  bulletin, décomptes de rappel ; contrôle de chaque lecture sur TOTAUX DU MOIS
  (`pdf.ecart_totaux`) ; comparaison au calcul (`Paye.select`, `examples/verifier.py`).
- **Barème explicite** (`config.Bareme`) : calculer avec d'autres valeurs que celles du
  paquet, sans le modifier.
- **Sources** : chaque valeur réglementaire avec son texte, relevés dans
  `docs/verification/`.
- **Documentation** : `docs/DOC.md`, `docs/csg.md`, `docs/mgen.md`, trois exemples
  fictifs (`examples/`).

### Corrigé

Depuis la mise en ligne du 18 octobre 2026 :

- **RAFP** : l'assiette du mois est ce que le cumul de l'année (primes dans la limite des
  plafonds) ajoute aux mois précédents ; elle repart au 1er janvier. Sous le plafond, les
  primes cotisaient sur un cumul croissant.
- **Valeurs non vérifiées** : avant la première date d'un barème, bpaye refuse de calculer
  au lieu d'en prendre la première valeur (pension civile avant 2011, plafond de transport
  avant août 2016, RAFP avant 2005…). Une indemnité créée plus tard (PSC, ISAE, prime
  d'équipement, indemnité compensatrice de CSG) est nulle avant sa création, et un
  enfant, un abonnement ou un forfait mobilités déclaré dans `agent.toml` ne compte qu'à
  partir de sa date.
- **Heures supplémentaires** : réduction de cotisations et exonération d'impôt depuis 2019
  seulement (loi 2018-1213), aucune d'août 2012 à 2018 (loi 2012-958), refus avant
  (régime de 2007 non relu).
- **Troncature** : le centime n'est plus perdu quand le produit flottant tombe juste sous la
  valeur exacte (traitement de l'IM 480 au 1/10/2008 : 2 193,90 €).
- **Plafonds de transport** : les montants officiels de chaque 1er janvier de 2023 à 2026.
- **Heures supplémentaires et majoration** arrondies au centime le plus proche.
- **Lignes ajoutées** : une charge ajoutée (`addligne`, `erreur_montant`) survit au
  recalcul ; un rappel de promotion (`retard_indice`) suit la quotité et la NBI.
- **Lecture des PDF** : un trop-perçu garde son signe ; `select` d'une fonction ne masque
  plus ses erreurs ; `siret` d'`agent.toml` trie les bulletins ; un sous-dossier par
  employeur est lu.
- **Dates** : un départ le 29, le 30 ou le 31 ne fait plus planter l'avancement ; un
  bulletin d'avant l'entrée dans la carrière est refusé.

[Non publié]: https://github.com/antnardo/bpaye/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/antnardo/bpaye/releases/tag/v0.2.0
