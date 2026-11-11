# Plan de continuité — Marge

**Date : 11 novembre 2026.** Échéance de soumission : **vendredi 11 décembre 2026, 12h00 PT**
(21h00 à Paris). Fin du jugement : 22 janvier 2027 — la démo doit rester en ligne jusque-là.

Ce plan distingue ce qui est **fait**, ce qui **reste et ne dépend que du code**, et ce qui
**exige le compte AWS ou une décision humaine**. Il est volontairement daté : le planning du
cahier des charges (ch. 21) est respecté, avec de l'avance sur S1/S2.

---

## 1. Ce qui est fait et vérifié

| Bloc | Preuve |
|---|---|
| Modèle de calcul (ch. 12) | smoke annexe D exact : 4 620 / 3 725 / **895 € = 19,4 %**, 9 h = **990 €** |
| Persistance | `SqliteStore` (migrations, cache) + `DynamoStore` (boto3 lazy) derrière un seul Protocol |
| Ingestion | tickets/temps, coûts AWS + conversion de devises, factures, contrats ; PII supprimée à l'entrée |
| Correspondance clients | propositions + confiance, validation humaine obligatoire (97,3 % proposé juste) |
| Lecture des contrats | plan de champs annexe B, extracteur local (prose **et** tableau, 13/13 contrats) + Bedrock Data Automation |
| Classement du travail | prompt clôturé anti-injection, sortie annexe C, règle de prudence, seuil 15 min, mémoire de décisions |
| Portail de validation | API FastAPI, les 14 routes du ch. 16, auth dev/Cognito, filtrage par ligne, audit |
| Serveur MCP | JSON-RPC stdio, les 3 outils du ch. 14.3 et leurs garde-fous |
| Revue mensuelle | agrégats + trame annexe E, narration contrôlée, repli SES/S3 |
| Actifs Quick | bundle JSON : 5 datasets, topic (12 métriques, 11 synonymes), 6 dashboards, 2 règles RLS, 2 scénarios, agent, flux |
| Jeu de démonstration | 12 clients, 6 mois, 3 922 interventions, 13 versions de contrat (PDF), 150 étiquetages, 20 questions |
| Mesures IA (§13.3) | clauses **100 %**, classement **100 %** (0 faux hors-périmètre), correspondance **97,3 %**, agent **100 %** |
| CI / Mergify / agents | 4 workers r630 dédiés, `ci` en 1 min 21, budget 5 min gardé, file Mergify (rebase), **agent de conflits InferHub `combo/cheap` prouvé sur la PR #29**, gate Hermes en dry-run |
| Tests | **568 tests offline** verts en ~16 s, ruff, garde <500 lignes/fichier et <50 lignes/fonction |

---

## 2. Ce qui manque vraiment (audit du 11 novembre, vérifié dans le code)

### 2.1 Bloquant pour la démo sur AWS

| # | Trou | Où | Conséquence si on ne le fait pas |
|---|---|---|---|
| G1 | **Les corps des 3 fonctions Lambda sont des placeholders** (11 lignes, `return {"routes": [...]}`) | `infra/cdk/portal.py` (`_API_BODY`), `contracts_ai.py`, `mcp.py` | Le portail déployé répond un stub : les juges ne voient rien |
| G2 | **Rien ne publie les 5 tables analytiques vers S3** | `store/athena.py` génère le DDL mais aucune écriture de données | Athena et Quick Sight n'ont aucune donnée à lire → aucun tableau de bord |
| G3 | **Aucune orchestration nocturne dans l'infra** (ni EventBridge Scheduler ni Step Functions) | `infra/cdk/` | Le parcours « chaque nuit » (spec 8.2) n'existe qu'en CLI locale |
| G4 | **Le portail statique n'est pas servi par l'API** | `src/marge/api/app.py` ne monte pas `StaticFiles` | L'URL publique n'affiche pas l'interface de validation |
| G5 | **Région non tranchée** : Bedrock Data Automation **n'existe pas à Paris** (`eu-west-3`) | `infra/cdk/app.py` (défaut `eu-west-3`), confirmé au `cdk synth` + doc AWS | Le stack `ContractsAi` échoue au déploiement |

### 2.2 Qualité / preuves

| # | Trou | Conséquence |
|---|---|---|
| G6 | `ENF-PERF-01` (recalcul < 30 min pour 200 clients) non prouvé — le jeu de démo n'a que 12 clients | Un critère non fonctionnel sans preuve |
| G7 | `ENF-SEC-01` et `ENF-OBS-01` sans test d'assertion CDK | Le chiffrement et les alarmes ne sont vérifiés qu'au déploiement |
| G8 | Matrice d'acceptation §9 périmée (annonce `dynamo_store.py` manquant alors qu'il est mergé) | Document de soumission inexact |
| G9 | **Vidéo de 3 minutes** : ni script ni tournage | Livrable obligatoire de la soumission |

### 2.3 Hors périmètre assumé

- `EF-SRC-05` (connecteurs du marché) : priorité **C** dans le cahier des charges → après le hackathon.
- `EF-SRC-04` (factures émises) : implémenté en CSV, le connecteur outil de facturation reste à écrire chez un vrai MSP.

---

## 3. Plan daté

### Lot 0 — 11 novembre, **aucun besoin d'AWS** (je peux tout faire seul)

| Tâche | Livre | Trou clos |
|---|---|---|
| Monter `portal/` en `StaticFiles` sur l'API + test | `marge serve` sert l'UI et le JSON | G4 |
| `marge publish` : écrire les 5 tables analytiques en CSV partitionné (`s3://…/marge/<table>/year=…/month=…/`) + appliquer les DDL | la chaîne Store → S3 → Athena → Quick | G2 |
| Vrais handlers Lambda : packaging `marge` en couche + 3 handlers fins qui importent le vrai code | plus aucun placeholder | G1 |
| EventBridge Scheduler + Step Functions (nightly / weekly / monthly) dans le CDK | le parcours 8.2/8.3/8.4 déployé | G3 |
| Tests d'assertion CDK (chiffrement, alarmes, rôles) | preuves ENF-SEC-01 / ENF-OBS-01 | G7 |
| Test de charge à 200 clients (marqué `slow`, hors PR) | mesure ENF-PERF-01 | G6 |
| Rafraîchir la matrice §9 | doc exacte | G8 |
| `docs/VIDEO-SCRIPT.md` : plan de tournage shot-by-shot + voix off anglaise | la vidéo devient filmable en une séance | G9 (partiel) |

### Lot 1 — dès que le compte AWS est accessible (12-16 novembre)

**Décision requise : la région.** Recommandation **`eu-west-1` (Irlande)** — Bedrock Data
Automation, Bedrock runtime, Agents for Bedrock et Quick Sight y sont disponibles ensemble, et
les données restent en UE (ch. 17 : les descriptions de tickets ne sortent pas de la région).
Alternative `us-east-1` si tu préfères la région où les fonctions Quick sortent en premier.

1. `aws login` (ou `aws sso login`) dans **ton** terminal — je ne saisis jamais d'identifiants.
2. `cdk bootstrap` puis `cdk deploy --all` sur les 6 stacks. **Aucune machine ne démarre** : S3, Glue, Athena, DynamoDB, Lambda, API Gateway, CloudFront, Cognito, Step Functions, EventBridge, CloudWatch, SNS.
3. Activer l'accès aux modèles Bedrock dans la console (1 clic par modèle).
4. Charger le jeu de démo : `generate` → `demo` → `publish`.
5. Déployer les actifs Quick : `marge assets` puis le plan de `quicksight/deploy.py`.
6. Créer **à la main** (non créable par API, risque assumé du ch. 22) : l'agent de chat, l'espace des contrats, le flux planifié — procédure pas à pas dans `docs/RUNBOOK.md` §4.

### Lot 2 — 23 au 29 novembre

- **Démarrer l'essai Quick Suite le 23 novembre** (30 jours gratuits, soit jusqu'au 23 décembre).
  Le démarrer plus tôt le ferait expirer avant la fin du jugement (22 janvier) : le cahier des
  charges a déjà tranché, je recommande de tenir cette date. Budget post-essai ~330 $.
- Recette complète **R1 à R15** sur le compte réel, corrections au fil de l'eau.

### Lot 3 — 30 novembre au 6 décembre

- Tournage de la vidéo (3 min, anglais, sans marque ni musique tierce) selon `docs/VIDEO-SCRIPT.md`.
- Schéma d'architecture final + HLD relus en anglais.
- Description Devpost et instructions de test (identifiants de démo du portail **et** de Quick).

### Lot 4 — 7 au 11 décembre

- **Soumission le 10 décembre au soir** (un jour de marge sur l'échéance du 11 à 12h00 PT).
- Partager le dépôt privé avec `testing@devpost.com` et `aws-msp@amazon.com`.
- Vérifier que tout reste en ligne jusqu'au 22 janvier (Quick, portail, données).

---

## 4. Ce qui exige une décision ou une action de ta part

| Quand | Action | Pourquoi moi je ne peux pas |
|---|---|---|
| Maintenant | **Choisir la région** (`eu-west-1` recommandé) | Décision de conformité / coût |
| Maintenant | **`aws login`** dans ton terminal | Je ne saisis jamais d'identifiants dans un navigateur ou un terminal sans demande explicite |
| Maintenant | Accepter ou non le **déploiement** (aucune machine, coûts en centimes hors Quick) | Engage ton compte |
| 23 novembre | **Démarrer l'essai Quick Suite** | Abonnement payant après 30 jours |
| Avant le 11 décembre | **Tourner la vidéo** et **remplir le formulaire Devpost** | Compte YouTube, compte Devpost, organisation APN |
| Sans objet | **GaiaSG94 doit accepter l'invitation** (permission write) | Seul le compte invité peut accepter |

Points du chapitre 24 encore ouverts : inscription APN de ton organisation (n° 1), application
des crédits du hackathon aux abonnements Quick (n° 3), position du passage source rendue par
Bedrock Data Automation (n° 4), citation exacte de clause via une base de connaissances Quick
(n° 5), couverture des scénarios Quick (n° 6), destinataires multiples d'un flux planifié (n° 7),
licence requise pour un agent de chat (n° 8). Chacun se vérifie en moins d'une heure sur le
compte réel, et chacun a déjà un repli écrit dans le code.

---

## 5. Ordre d'exécution recommandé

1. **Lot 0 maintenant** (parallélisable, zéro risque, zéro coût) — je le lance.
2. **Région + `aws login`** dès que tu peux : c'est le seul vrai point bloquant du calendrier.
3. Lot 1 dans la foulée, puis recette R1..R15.
4. Vidéo en dernier : elle se tourne sur un environnement stable, jamais sur un chantier.
