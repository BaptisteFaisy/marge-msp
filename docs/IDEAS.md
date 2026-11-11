# 100 pistes pour aller plus loin — Marge

Liste produite le 11 novembre 2026, après le déploiement réel en `eu-west-1`
(compte 710332178565) et la livraison du parcours complet hors ligne. Chaque
piste est numérotée ; les **10 prioritaires** sont justifiées en tête.

Rappel du cadre : échéance de soumission **vendredi 11 décembre 2026, 12h00 PT**,
jugement jusqu'au **22 janvier 2027**, quatre critères à 25 % chacun (mise en
œuvre technique, conception, impact, innovation).

---

## Les 10 prioritaires

| # | Piste | Pourquoi elle est dans le top 10 | Coût |
|---|---|---|---|
| **13** | Activer Bedrock Data Automation et mesurer l'écart IA vs extracteur local sur les 13 contrats | Seul blocage technique du compte. C'est la preuve la plus directe que « le code appelle réellement un service IA AWS » sur de vrais PDF, et elle transforme un repli assumé en comparaison chiffrée | 1 action console + 1 h |
| **37** | Une API « why » : pour n'importe quel chiffre, la chaîne de décomposition jusqu'à la ligne source | Répond à ENF-TRA-01 et neutralise le risque majeur du cahier des charges (« l'agent donne un chiffre faux »). C'est l'argument de confiance du projet, démonstrable en 20 secondes en vidéo | 1 jour |
| **74** | Nightly en Step Functions `Map` parallèle par client | Fait passer ENF-PERF-01 (200 clients < 30 min) d'une hypothèse à une mesure, et supprime le plafond des lots bornés du classifieur | 1 jour |
| **71** | Publier en Parquet compressé au lieu de JSONL | Athena facture au volume scanné : 3 à 5 fois moins cher et plus rapide. Rend crédible le coût de production annoncé au chapitre 18 (critère Impact) | 0,5 jour |
| **61** | Vrai flux Cognito Hosted UI dans le portail | Le mode `dev` lit l'identité dans des en-têtes : acceptable pour une démo sur données fictives, mais un juge qui teste l'URL publique le verra. Le critère Conception se joue là | 1 jour |
| **18** | Journaliser chaque appel modèle (tokens, latence, coût estimé, modèle, décision) | La traçabilité de l'IA est le différenciateur de conception du projet. Sans elle, « l'IA propose, l'humain valide » reste une intention | 0,5 jour |
| **26** | Comparer deux modèles sur le même jeu de 150 interventions et publier le tableau | Preuve d'ingénierie pour le critère technique : on ne subit pas le modèle, on le choisit avec des chiffres | 0,5 jour |
| **19+20** | Compteur de tentatives d'injection + jeu adversarial de 10 tickets pièges | Peu de candidats montrent une défense **mesurée** contre l'injection indirecte (ENF-IA-03). C'est de l'innovation démontrable, pas déclarée | 0,5 jour |
| **28** | Versionnage des recalculs avec diff visible v(n) / v(n-1) | EF-CAL-03 et la recette R9 sont une exigence distinctive : « un changement de coût horaire ne réécrit pas le passé ». Le montrer à l'écran vaut mieux que l'écrire | 1 jour |
| **5+4** | Bouton « judge tour » dans le portail + description Devpost ouvrant sur les 3 chiffres d'impact | Réduit le risque du jour J et aligne le dossier sur le critère Impact, qui exige des gains **mesurés** | 0,5 jour |

Total : environ **7 jours de travail** pour les dix. Le calendrier du chapitre 21
(S3 à S5) les absorbe sans toucher à la vidéo ni à la soumission.

---

## A. Gagner le hackathon (1-12)

1. Vidéo de secours « tout hors ligne », tournée avant le 23 novembre, au cas où Quick Suite n'est pas prêt.
2. Bandeau « données 100 % fictives » visible dans chaque plan (crédibilité et conformité).
3. Schéma d'architecture exporté en PNG depuis le mermaid du HLD, pour le formulaire Devpost.
4. Description Devpost de 300 mots ouvrant sur les trois chiffres d'impact.
5. Bouton « judge tour » : rejoue le parcours de démonstration étape par étape dans le portail.
6. Fiche imprimée des 20 questions de référence avec les réponses attendues, pour le jour du jugement.
7. `DEMO.md` : les six commandes dans l'ordre et leur sortie attendue.
8. Compteur « revue préparée en X minutes » affiché dans la revue elle-même (chiffre d'impact n° 1).
9. Badge généré par `marge eval` dans le README : les quatre mesures visibles sans lire le code.
10. Relecture du HLD par un non-technicien : le récit MSP doit tenir sans jargon.
11. `docs/OPEN-QUESTIONS.md` : les dix points du chapitre 24 avec leur statut et leur repli.
12. Captures d'écran réelles (portail, tableau de bord) dans `docs/img/`, attendues par le HLD.

## B. IA, Bedrock et Quick Suite (13-26)

13. Activer Bedrock Data Automation et comparer l'extraction IA à l'extracteur local sur les 13 contrats.
14. Tester un modèle plus petit et plus rapide que Nova Lite et mesurer l'accord (coût contre qualité).
15. Cache de classement : une intervention déjà classée ne repasse jamais par le modèle.
16. Inférence par lots (batch) pour le traitement nocturne, au lieu d'un appel par intervention.
17. Seuil d'abstention paramétrable, avec suivi du taux d'abstention dans le temps.
18. Journal des appels modèle : tokens, latence, coût estimé, modèle, décision retenue.
19. Compteur et alerte sur les tentatives d'injection détectées dans les tickets.
20. Jeu adversarial de dix tickets pièges intégré au harnais d'évaluation.
21. Bedrock Guardrails en amont du classifieur (filtre de contenu et de sujet).
22. Génération automatique du texte de « cause principale » d'une variation de marge, chiffres fournis par le code.
23. Démonstration réelle de l'agent Quick appelant `get_margin_breakdown` via le serveur MCP.
24. Outil MCP supplémentaire `simulate_price_increase` (les scénarios du chapitre 14.3 côté serveur).
25. Alimenter l'espace de connaissances Quick avec les **clauses** extraites, pas seulement les PDF, pour une citation exacte.
26. Comparaison publiée de deux modèles sur le même jeu de 150 interventions étiquetées.

## C. Calcul et traçabilité (27-38)

27. Invariant comptable testé sur tout le jeu : la somme des lignes égale toujours le total publié.
28. Versionnage des recalculs avec diff lisible entre v(n) et v(n-1).
29. Coût de service par ticket exposé dans la fiche client (déjà calculé, pas encore affiché).
30. Avoirs et refacturations : gérer explicitement les revenus négatifs.
31. Proratisation du contrat au mois (entrée ou sortie de client en cours de mois).
32. Contrats multiples pour un même client (multi-entités, multi-périmètres).
33. Contrôle de qualité de saisie : plus de 24 h pointées sur un jour pour un même ticket = alerte.
34. Notion de marge cible par client et écart à la cible.
35. Poste distinct pour le temps d'astreinte et les heures non productives.
36. Prévision de marge à trois mois par régression simple (cible du chapitre 5.2).
37. API « why » : chaîne de décomposition de n'importe quel chiffre jusqu'à la ligne source.
38. Tests property-based (`hypothesis`) sur le moteur de calcul.

## D. Données et connecteurs (39-50)

39. Connecteur ServiceNow ou Jira Service Management (le plus demandé par les MSP).
40. Connecteurs ConnectWise, Autotask, HaloPSA : les trois PSA leaders du marché.
41. Ingestion native du CUR 2.0 (Cost and Usage Report) au lieu d'un export CSV.
42. Connecteur Xero ou QuickBooks pour les factures émises (EF-SRC-04).
43. Ingestion incrémentale avec checkpoint par source : ne charger que le delta.
44. Validation de schéma des fichiers entrants avec rapport d'erreurs exploitable par l'administrateur.
45. Détection de doublons d'interventions (même ticket pointé deux fois).
46. Correspondance client enrichie par l'usage : les validations humaines nourrissent les propositions suivantes.
47. Score de complétude par client et par mois, affiché sur tous les écrans.
48. Import manuel Excel pour les MSP sans API.
49. Journal d'ingestion consultable dans le portail (quoi, quand, combien de lignes rejetées).
50. Rejeu déterministe d'un chargement à une date antérieure.

## E. Portail et expérience (51-60)

51. Validation en masse : approuver vingt interventions d'un coup avec un motif commun.
52. Fil de révision : ce que le modèle a proposé contre ce que l'humain a corrigé.
53. Diff visuel entre deux versions d'un contrat (avenant).
54. Recherche plein texte dans les clauses validées.
55. Mode sombre et mise en page responsive (les responsables de compte sont en mobilité).
56. Notifications « douze interventions à valider » par courriel ou Slack.
57. Export PDF de la fiche client pour un rendez-vous de renouvellement.
58. Raccourcis clavier sur la file de validation (parcourir, approuver, rejeter).
59. Indicateur d'avancement de la validation mensuelle par responsable de compte.
60. Portail bilingue FR/EN : les juges sont anglophones, les données sont françaises.

## F. Sécurité et conformité (61-70)

61. Flux Cognito Hosted UI réel dans le portail, puis bascule de `dev` à `cognito`.
62. Journal d'audit immuable : S3 Object Lock sur les validations.
63. Chiffrement côté client des contrats avant téléversement S3.
64. Anonymisation réversible des descriptions de tickets avant envoi au modèle.
65. Politique de rétention paramétrable (RGPD) avec purge automatisée.
66. Test de pénétration léger et automatisé du portail (OWASP Top 10).
67. Clés KMS client partout, avec rotation.
68. Un compte AWS par environnement, avec SCP de plafonnement budgétaire.
69. Détection d'accès anormal : un responsable qui consulte un portefeuille qui n'est pas le sien.
70. Formaliser en test l'absence de donnée sociale stockée (ENF-CONF-01 est déjà dans le design).

## G. Performance et coûts AWS (71-80)

71. Parquet compressé au lieu de JSONL : Athena trois à cinq fois moins cher.
72. Partitionner par client en plus du mois, pour les MSP à fort volume.
73. Mesurer le coût réel du cache SPICE de Quick Sight et l'ajuster.
74. Nightly en Step Functions `Map` parallèle par client.
75. Publier le coût mesuré d'une nuit de traitement pour 200 clients.
76. Budgets AWS et alarmes de dépassement sur le compte de démonstration.
77. Plan de démontage daté au 23 janvier 2027, exécuté automatiquement après le jugement.
78. Estimation de coût du déploiement avant application (AWS Pricing API) en `--dry-run`.
79. Compression des PDF de contrats à l'ingestion.
80. Tableau de bord du coût modèle par invocation et par client.

## H. Industrialisation (81-88)

81. Tests d'assertion CDK en CI (ENF-SEC-01, ENF-OBS-01) avec `aws-cdk-lib` installé sur le worker.
82. Pipeline de déploiement OIDC (GitHub Actions vers AWS) au lieu du déploiement local.
83. Environnements dev, staging et prod paramétrés par contexte CDK.
84. Tests de contrat entre le portail JavaScript et l'API, sur le schéma OpenAPI généré.
85. Mesure de couverture de tests avec plancher imposé en CI.
86. Test de charge de l'API : 200 clients, 50 utilisateurs simultanés.
87. Documentation interactive `/docs` de FastAPI exposée derrière CloudFront en mode démo.
88. Veille de dépendances (Dependabot ou Renovate) sur le dépôt.

## I. Produit et après-hackathon (89-100)

89. Offre packagée « Marge en trente jours » pour les partenaires MSP.
90. Tarification à l'usage, par client suivi.
91. Aide au chiffrage d'un nouveau contrat à partir des clients comparables (chapitre 5.2).
92. Prévision de marge à trois mois avec alerte précoce.
93. Benchmark sectoriel anonymisé : marge médiane par secteur.
94. Intégration comptable : export FEC et rapprochement.
95. Module projets au forfait et en régie.
96. Alerte de renouvellement avec dossier chiffré pré-rempli, envoyé au responsable de compte.
97. Application mobile progressive pour la validation en déplacement.
98. Multi-MSP : un partenaire qui l'exploite pour d'autres partenaires.
99. Place de marché de connecteurs PSA.
100. Marque blanche pour les grossistes IT.

---

## Ce que cette liste ne règle pas

Trois points restent hors de notre contrôle et bloquent une partie des pistes :

- **l'activation de Bedrock Data Automation** sur le compte (piste 13) ;
- **le démarrage de l'essai Quick Suite**, à ne pas faire avant le 23 novembre pour
  qu'il couvre la fin du jugement ;
- **la création manuelle dans la console Quick** de l'agent de chat, de l'espace
  des contrats et du flux planifié (l'API ne sait pas les créer).
