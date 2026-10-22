# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et la
[gestion sémantique de version](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté

- **Retards de la Défense** : `[defense]` a son propre calendrier dans `academies.toml`
  (HSA et majoration d'octobre et de novembre payées en décembre, IFP à son mois), relevé
  sur des bulletins papier de 2017 et 2018 ; une rubrique peut avoir plusieurs mois en
  retard (`academies.remplace`).
- **Plusieurs bulletins par mois, plusieurs employeurs** : `[[employeur]]` dans
  `agent.toml` (SIRET ou code de gestion du poste, par dates), `pdf.extract_employeur` et
  `bulletins.trouve_bulletins`. Chaque bulletin est lu à part et rattaché à son employeur ;
  le calcul ne se compare qu'à celui de l'employeur du mois, quel que soit le nom du
  fichier. `examples/verifier.py`, `examples/exporter.py` et `Paye.select` lisent ainsi
  tous les bulletins : ceux d'un ancien employeur, écartés jusqu'ici par le SIRET, se
  comparent, et un rappel versé après le départ se lit à part.
- **Export CSV** (`bpaye.export`, `examples/exporter.py`) : un fichier par bulletin, lu
  colonne par colonne avec le calcul en regard, et deux tableaux de tous les mois, une
  ligne par bulletin et une colonne par code, l'un lu, l'autre calculé.
- **Heures de colles lues dans un montant** (`colles.heures_du_montant`,
  `colles.decrit_colles`) : `bpaye-lire` et `examples/verifier.py` disent ce que représente
  le montant de colles d'un bulletin, en heures entières à un code avec le sens du code, ou
  qu'il mêle plusieurs codes ou mois, sans hypothèse.
- **Bulletins PAY18E V1.4, V1.6 et V2.1** (2017 à 2019) lus, totaux et pied vérifiés ;
  codes 200125 (vacations) et 604972 (transfert primes/points de catégorie C) ; lignes
  équivalentes à la comparaison : 202206/202209 (indemnité compensatrice de CSG) et
  604970/604972.
- **Anonymiser un bulletin** (`scripts/anonymise_bulletin.py`, autonome, sans bpaye ;
  `docs/anonymisation.md`) : une copie filtrée par la rédaction de reportlab_layout, qui
  garde tout, lignes inconnues comprises, sauf le NIR, le nom et l'adresse, l'affectation,
  le SIRET, les cumuls de l'année, l'IBAN et le code-barres DataMatrix ; la sortie est
  contrôlée, l'original n'est jamais modifié ni aucun fichier écrasé.
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
- **ISOE part modulable** : indexée sur le point depuis les arrêtés de 2009, 2021 et 2023
  (auparavant refusée avant septembre 2023) ; 201228 et 202566 comparés comme une même
  ligne, la paie portant encore l'ancien code en 2026 (`codes.CODES_EQUIVALENTS`).
- **Option santé et prévoyance de la PSC, ancienne mutuelle** (`[[psc]]` d'`agent.toml`) :
  participations de l'employeur depuis mai 2026, la moitié du coût déclaré de l'option
  dans la limite de 5 € et 7 € pour l'adhésion à la prévoyance, d'après la page du
  ministère ; ancienne adhésion MGEN précomptée sur la paie, aux montants du contrat.
- **HSE d'autres rubriques et vacations** : `paye.hse(…, code=…)` pour le remplacement de
  courte durée (majoré de 25 % dès 2005, décret 2005-1036), la réussite au lycée et les
  HSE des dispositifs recodées 201300 en septembre 2025, exonérées comme les heures
  supplémentaires ; `paye.vacation` pour les vacations de formation (taux fixé par
  l'organisateur dans les fourchettes de l'arrêté du 7 mai 2012) et les actions à
  pilotage national, au taux déclaré.
- **Retards habituels de la paie, par académie** (`academies.toml`) : les HSA d'octobre
  et l'IFP de septembre payées le mois suivant ne sont plus codées en dur ; un défaut
  relevé à Paris, toutes les académies de l'art. R222-2 et les lycées de la Défense.
  `agent.toml` choisit l'académie à chaque date (`[[academie]]`) et ajoute ses propres
  retards (`[[retards]]`, un FMD payé en février par exemple).

### Corrigé

- Des rappels d'une même rubrique versés le même mois s'arrondissent depuis la somme de
  leurs montants exacts (`Ligne.exacte`) : deux neuvièmes d'HSA font 5 484,81 €, non
  2 × 2 742,41 €.
- HSA et majoration : arrondies au centime depuis le taux annuel exact, non depuis le taux
  arrondi (sept HSA de 2018 : 2 132,98 € et non 2 132,99 €) ; 150 mois sur 154 relevés de
  2017 à 2026, les quatre autres étant une erreur de la paie.
- RAFP : la cotisation cumulée de l'année est tronquée au centime, et chaque mois prélève ce
  qui s'y ajoute (39,62 € en janvier et juillet, 39,63 € les autres mois) ; relevé sur tous
  les mois de 2020, 2022, 2024 et 2025.
- Le rappel d'un échelon pris en cours de mois et payé en retard (`retard_indice`,
  `retard_statut`) suit la paie : le mois du changement, les seuls jours rappelés, chaque
  traitement tronqué, et la pension sur chacun ; relevé sur deux décomptes de rappel.
- Un échelon pris en cours de mois est payé par trentièmes des deux traitements, chacun
  tronqué (`point.traitement_indiciaire`), non au prorata de l'indice : relevé sur un
  décompte de rappel de 2018 (3 203,19 € au lieu de 3 203,17 €).
- Contribution exceptionnelle de solidarité (jusqu'en 2017) : assiette nette du transfert
  primes/points, montant tronqué au centime ; relevé sur les bulletins de 2017.
- Code 558001 (montant simulé du prélèvement à la source, bulletins de fin 2018 ; BJ
  janvier 2026), hors de tout total du pied : `pdf.HORS_TOTAUX`.
- `find_pdfs` et `find_dr_pdfs` écartent un PDF sans texte (un scan) : il était pris pour
  un bulletin vectoriel, et lu vide.
- **Contribution de solidarité** (jusqu'en 2017) selon le code du travail, L5423-27 et
  L5423-32 : assiette hors remboursements de frais, plafonnée à 4 PMSS, exonération sous le
  traitement de l'IM 285 ; le taux de 1 % est sourcé.
- **Indemnité de fonction d'un détachement à la Défense** (201150) : montant individuel de
  la décision du ministre (décret 2003-745), déclaré dans `[[detachements]]`
  (`indemnite_fonction`), au lieu d'un montant relevé appliqué à tous.
- **Ancienneté en chaire supérieure** : conservée quand le décret 68-503, art. 5, le prévoit
  (gain d'indice inférieur à une promotion d'échelon, agrégé au 11e échelon).
- **IFP** : l'écart de 0,07 % entre la paie, que bpaye suit, et les 6 270 F de l'arrêté de
  1999 est désormais noté dans le code et le guide.
- **Heures de surveillance** : `paye.surveillance` (code 200216) paie un trente-sixième du
  taux annuel réduit de 50 %, comme le dit le décret 50-1253, art. 5 ; `paye.ds`, qui
  payait 0,375 du trente-sixième sous le code des HSE sans source, disparaît.
- **Plafond d'exonération des heures supplémentaires** : 7 500 € nets (8 037 € bruts) pour
  les heures faites depuis le 1er janvier 2022, d'après la loi 2022-1157, art. 4 (et non
  la loi 2022-1158) ; bpaye ne l'appliquait qu'en 2023, comme certaines paies.
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
