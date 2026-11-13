# Déploiement réel — Marge sur AWS

**Compte** `710332178565` · **Région** `eu-west-1` (Irlande) · **Environnement** `dev`
État vérifié le **11 novembre 2026**. Aucune machine : tout est serverless.

## 0. Procédure de déploiement (13 novembre 2026)

Une seule commande, rejouable :

```bash
AWS_REGION=eu-west-1 MARGE_AUTH_MODE=cognito bash scripts/deploy.sh
```

Elle enchaîne la construction des paquets Lambda, la synthèse CDK, le
déploiement des huit stacks et le chargement du jeu de démonstration. Les
deux variables d'environnement ne sont pas facultatives :

| Variable | Pourquoi |
|---|---|
| `AWS_REGION` | la CLI CDK ne lit pas `CDK_DEFAULT_REGION` : sans elle, elle **défaut sur us-east-1** et crée les stacks dans la mauvaise région |
| `MARGE_AUTH_MODE=cognito` | `infra/cdk/app.py` lit cette variable : sans elle, le portail déployé revient au mode `dev` (identité dans les en-têtes `X-Actor-*`), c'est-à-dire aucune authentification |

Le jeu de démonstration se charge aussi seul, sans redéploiement :

```bash
python3 -m marge.cli load-demo --backend dynamo \
  --table marge-validations --region eu-west-1 \
  --publish-s3 margedatalake-margedevcurated4fd643b0-fp6unqp88h0e
```

La commande est **rejouable** : chaque ligne est écrite sur sa clé naturelle,
donc la recharger ne duplique rien.

Les identifiants des juges ne sont jamais dans le dépôt : ils sont générés et
conservés dans AWS Secrets Manager.

```bash
python3 scripts/create_judge_account.py --region eu-west-1 --rotate-demo-users
aws secretsmanager get-secret-value --secret-id marge/demo/credentials \
  --region eu-west-1 --query SecretString --output text
```

Et pour tout supprimer :

```bash
bash scripts/teardown.sh        # les stacks et les ressources conservées (RETAIN)
bash scripts/teardown.sh --data # le jeu de démonstration seulement
```

## 1. Ce qui est déployé (8 stacks CloudFormation)

| Stack | Contenu | État |
|---|---|---|
| `MargeDataLake` | 2 buckets S3 (raw, curated), base Glue `marge`, workgroup Athena `marge` (plafond 10 Go/requête), rôles au moindre privilège | `CREATE_COMPLETE` |
| `MargePortal` | CloudFront, API Gateway REST, Lambda portail, Cognito (5 groupes de rôles), **table DynamoDB `marge-validations`** (pk/sk + 3 GSI, on-demand, chiffrée, PITR) | `CREATE_COMPLETE` |
| `MargeContractsAi` | Blueprint + projet Bedrock Data Automation, Lambda classifieur, Lambda extracteur de contrats | `CREATE_COMPLETE` |
| `MargeMcp` | AgentCore Gateway + Lambda MCP | `CREATE_COMPLETE` |
| `MargeOrchestration` | 4 Lambda de jobs + Step Functions `marge-dev-nightly` + 3 plannifications EventBridge | `CREATE_COMPLETE` |
| `MargeObservability` | 4 alarmes CloudWatch, tableau de bord `marge-dev-supervision`, sujet SNS | `CREATE_COMPLETE` |
| `MargeQuickSight` | Bucket d'actifs + rôle de service Quick Sight (**aucun abonnement créé**) | `CREATE_COMPLETE` |
| `MargeBudget` | Budget AWS mensuel (5 $) + sujet SNS d'alerte à 80 % | `CREATE_COMPLETE` |

## 2. URL et points d'entrée

| Objet | Valeur |
|---|---|
| **Portail public** (juges) | `https://d3n1e2aqabg966.cloudfront.net` — HTTP 200, sert `portal/index.html` |
| API (via CloudFront, même origine) | `https://d3n1e2aqabg966.cloudfront.net/v1/...` |
| API (directe) | `https://or7doe7fbj.execute-api.eu-west-1.amazonaws.com/prod/v1/...` |
| Bucket brut (contrats PDF) | `margedatalake-margedevraw1382fb15-joyakwyqz8u4` |
| Bucket curaté (tables analytiques) | `margedatalake-margedevcurated4fd643b0-fp6unqp88h0e` |
| Base Glue / workgroup Athena | `marge` / `marge` |
| Table DynamoDB | `marge-validations` |
| Cognito | pool `eu-west-1_gsR5Mjwsj` |

Les six familles de routes du chapitre 16 répondent **200** derrière CloudFront
(`contracts`, `coverage`, `rates`, `matches`, `classifications`,
`allocation-rules`) et `POST /v1/recalculate` renvoie 200.

## 3. Données chargées et vérifiées

- **DynamoDB** : 12 clients, 13 versions de contrat, 3 922 interventions, 84 lignes
  de coûts AWS, 78 factures, 5 tarifs, 5 outils.
- **S3 curaté** : les 5 tables de l'annexe A en JSON Lines partitionné
  (`analytical/<table>/month=AAAA-MM/part-0.jsonl`), 5 024 lignes, 20 fichiers.
- **Athena** : tables externes créées par le DDL généré par
  `marge.store.athena` (serde JSON natif, types conservés), partitions réparées
  par `MSCK REPAIR TABLE`. Requêtes de contrôle exécutées :

| mois | clients | marge totale | taux moyen |
|---|---|---|---|
| 2026-05 | 12 | 10 965,70 | 22,0 % |
| 2026-08 | 12 | 7 841,50 | 15,5 % |
| 2026-10 | 12 | 7 148,60 | 13,6 % |

Clients les moins rentables en octobre : Marchand Distribution −31,7 %,
Blanchard Chimie −30,8 %, Girard BTP 9,3 %, Leroy Logistique 14,9 %,
**Durand Industries 19,4 %** — ce dernier reproduit exactement l'annexe D.

## 4. Appels réels à un service IA AWS (exigence du ch. 20.1)

**Classifieur — fonctionne.** Invocation réelle de Bedrock depuis la Lambda,
modèle `eu.amazon.nova-lite-v1:0` :

```
wl-003273 -> IN_SCOPE  (confiance 0.95)  clause « Gestion des accès et des comptes »
wl-003275 -> IN_SCOPE  (confiance 0.95)  clause « Gestion des incidents d'infrastructure »
```

Les classements sont écrits dans DynamoDB avec la clause citée et le motif.
Le même appel a été vérifié en local sur un cas hors périmètre : la clause
d'exclusion est citée mot pour mot et les heures restent recopiées du pointage.

**Bedrock Data Automation — bloqué au niveau du compte.** Le blueprint et le
projet sont créés (`arn:aws:bedrock:eu-west-1:710332178565:data-automation-project/1f1f9bebc409`,
étape LIVE), mais `InvokeDataAutomationAsync` répond :

```
AccessDeniedException: User: 710332178565 is not authorized to access this resource
```

**y compris avec les credentials racine** : ce n'est pas un trou IAM, c'est
l'activation du service qui manque sur ce compte. À faire dans la console
(Bedrock → Data Automation). En attendant, l'extracteur bascule sur
l'extracteur local déterministe et **le dit** dans sa réponse
(`"engine": "local-fallback"`) ; `MARGE_BDA_FALLBACK=0` rend l'échec bruyant.

Conséquence à connaître : l'extracteur local lit du **texte**. Sur les PDF il ne
retrouve que 8 champs sur 16 ; sur les `.txt` companions il retrouve les 16
(100 % de réussite mesurée par `marge eval`). Pour la démonstration, extraire
depuis les `.txt`, ou activer Data Automation pour les PDF.

## 5. Orchestration

Trois plannifications EventBridge **ENABLED** (fuseau Europe/Paris) :
`marge-dev-nightly` (02:00), `marge-dev-weeklyreport` (lundi 07:00),
`marge-dev-monthly` (le 3 à 08:00). La machine Step Functions
`marge-dev-nightly` enchaîne classification → recalcul → publication → file
hebdomadaire, avec repli sur un état d'échec et tracing X-Ray.

## 6. Coût

Aucune instance, aucun conteneur, aucun GPU. S3, DynamoDB on-demand, Lambda,
API Gateway, CloudFront, Step Functions, EventBridge, Athena : facturation à
l'usage, quelques centimes pour ce volume. Deux postes à surveiller :

- **Athena** : 5 $/To analysé — le workgroup plafonne à 10 Go par requête.
- **Bedrock** : à l'invocation. Le classifieur traite par lots bornés
  (`MARGE_CLASSIFY_BATCH`, 50 par défaut) : 3 922 interventions ≈ 79 invocations
  de Lambda, quelques centimes avec Nova Lite.
- **Quick Sight / Quick Suite** : non activé volontairement (voir §7).

## 7. Ce qui reste à faire, et par qui

| # | Action | Qui | Pourquoi |
|---|---|---|---|
| 1 | **Activer Bedrock Data Automation** dans la console | Baptiste | Seul blocage côté AWS ; débloque la lecture des PDF par l'IA |
| 2 | **Démarrer l'essai Quick Suite le 23 novembre** | Baptiste | 30 jours gratuits ; démarré plus tôt il expirerait avant la fin du jugement (22 janvier) |
| 3 | Créer les 3 éléments Quick non automatisables (agent de chat, espace contrats, flux planifié) | Baptiste, procédure `docs/RUNBOOK.md` §4 | L'API ne sait pas les créer |
| 4 | Créer les utilisateurs Cognito de démonstration | Baptiste | EF-ADM-03, identifiants pour les juges |
| 5 | Basculer `MARGE_AUTH_MODE` de `dev` à `cognito` | après (4) | Le mode `dev` lit l'identité dans les en-têtes : acceptable pour une démo sur données fictives, pas pour la production |
| 6 | Tourner la vidéo | Baptiste | `docs/VIDEO-SCRIPT.md` est prêt, plan par plan |
| 7 | Soumettre sur Devpost + partager le dépôt | Baptiste | `testing@devpost.com`, `aws-msp@amazon.com` |

## 8. Commandes de reproduction

```bash
cd infra/cdk
python3 -m venv /tmp/cdk-venv && /tmp/cdk-venv/bin/pip install -r requirements.txt
bash ../../scripts/build-lambda-package.sh        # paquets Lambda (portal, jobs)
export CDK_DEFAULT_ACCOUNT=710332178565 CDK_DEFAULT_REGION=eu-west-1
cdk bootstrap aws://710332178565/eu-west-1 --app "/tmp/cdk-venv/bin/python app.py"
cdk deploy --all --app "/tmp/cdk-venv/bin/python app.py" --region eu-west-1 --require-approval never
```

Puis, côté données :

```bash
python3 -m marge.cli generate --out data/generated
python3 -m marge.cli demo --data data/generated --db marge.sqlite3 --auto-validate --review
python3 -m marge.cli publish --db marge.sqlite3 --s3 <bucket-curaté> --prefix analytical
python3 -m marge.cli eval --data data/generated
```
