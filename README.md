# AlphaForge AI : orchestrateur multi-agents (MVP)

Orchestrateur LangGraph qui répond à une question financière avec trois agents spécialisés (analyse de document, sentiment,
explication du risque selon le persona Prudent / Équilibré / Audacieux), puis synthétise. Les appels LLM passent par un
`ModelRouter` : **Amazon Bedrock** (Claude Haiku 5.5, Sonnet 5.5…) ou un **mock local**.

Ce dépôt ne contient ni frontend, ni calculs financiers, ni modèles ML (parties d'autres membres de l'équipe).
Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour l'architecture, le routage, l'IAM et le déploiement.

## Installation

```powershell
pip install -e ".[dev]"
copy .env.example .env      # puis éditez .env si besoin
```

## Local, sans AWS (par défaut)

Aucun identifiant requis : tout passe par le provider `mock` et le dossier `./data`.

```powershell
python -m pytest                                              # 64 tests, aucun appel AWS, aucun coût
python -m alphaforge ask "Qu'est-ce qu'un FNB obligataire ?" --persona prudent
python -m alphaforge evaluate --dataset golden_v1 --mlflow
mlflow ui --backend-store-uri sqlite:///mlflow.db             # consulter les runs
```

## Avec AWS Bedrock

1. **Identifiants** (jamais dans le code ni dans git) : rôle IAM, ou profil (`AWS_PROFILE`), ou, pour un atelier,
   les variables `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` dans votre `.env` local (ignoré par git).
   Ces jetons d'atelier expirent : en cas d'`ExpiredToken`, recopiez-en de nouveaux.
2. **Routes** : dans `.env`, décommentez/adaptez `LLM_ROUTES` (exemple dans `.env.example`).
3. **Vérifier** chaque modèle configuré (petit appel réel, coût négligeable) :
   ```powershell
   python -m alphaforge check-routes
   ```
4. **Lancer** :
   ```powershell
   python -m alphaforge ask "Ce FNB est-il adapté à un profil prudent ?" --persona prudent --doc rapport.txt
   python -m alphaforge evaluate --dataset golden_v1 --mlflow --save-baseline   # première fois
   python -m alphaforge evaluate --dataset golden_v1 --baseline                 # détecte les régressions (code 1)
   python -m pytest -m aws -s                                                   # tests réels (coûtent quelques centimes)
   ```

## Stockage S3

Dans `.env` : `STORAGE_BACKEND=s3` et `S3_BUCKET=<votre-bucket>` (préfixe `alphaforge/` par défaut). Puis :

```powershell
python -m alphaforge upload-datasets      # envoie ./data/datasets vers S3
python -m alphaforge evaluate --dataset golden_v1 --save-baseline   # lit le dataset depuis S3, y écrit rapports et baseline
```

## CloudWatch

Dans `.env` (en PowerShell ou via `.env`, pas via `export` sous Git Bash qui transforme `/alphaforge/app` en chemin Windows) :

```
CLOUDWATCH_LOG_GROUP=/alphaforge/app
CLOUDWATCH_METRICS=true
```

Le groupe est créé au besoin (rétention 14 jours). Chaque exécution écrit dans son propre flux ; les événements sont des JSON
(`request_start`, `agent_run`, `model_call`, `request_end`, `agent_error`, `truncated`). Avec `CLOUDWATCH_METRICS=true`, chaque
`model_call` produit aussi des métriques (espace de noms `AlphaForge`, dimensions `task` et `model_id` : `latency_ms`,
`input_tokens`, `output_tokens`, `estimated_cost_usd` si le prix est configuré). Si CloudWatch est inaccessible, l'application
continue avec les logs locaux. Sur ECS Fargate : laisser `CLOUDWATCH_LOG_GROUP` vide et utiliser le pilote `awslogs`.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `LLM_ROUTES` | `{"default": ["mock:mock-model"]}` | JSON `{"tâche": ["fournisseur:model_id", ...]}` ; tâches : `orchestration`, `agent`, `evaluation`, `default` ; fournisseurs : `mock`, `bedrock` |
| `LLM_MAX_TOKENS` | `{"default": 2048, "orchestration": 4096, "agent": 2048, "evaluation": 600}` | Limite de tokens de sortie par tâche |
| `LLM_PRICING` | `{}` | Prix USD / 1M tokens par modèle. Vide = coût « inconnu » (jamais deviné) |
| `AWS_REGION` | `us-east-1` | Région Bedrock / S3 |
| `AWS_PROFILE` | (vide) | Profil AWS pour le développement local |
| `BEDROCK_TIMEOUT_SECONDS` / `BEDROCK_MAX_RETRIES` | `60` / `3` | Délai et nouvelles tentatives (botocore, mode adaptatif) |
| `STORAGE_BACKEND` | `local` | `local` ou `s3` |
| `LOCAL_STORAGE_DIR` | `./data` | Racine du stockage local |
| `S3_BUCKET`, `S3_PREFIX` | (vide), `alphaforge` | Bucket et préfixe S3 |
| `CLOUDWATCH_LOG_GROUP`, `CLOUDWATCH_RETENTION_DAYS`, `CLOUDWATCH_METRICS` | (vide), `14`, `false` | Envoi des logs / métriques vers CloudWatch |
| `LOG_LEVEL`, `LOG_PROMPTS` | `INFO`, `false` | Niveau de logs ; aperçu de prompt (débogage uniquement) |
| `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT` | `sqlite:///mlflow.db`, `alphaforge` | Suivi MLflow |

## Permissions IAM

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#permissions-iam-requises) : `bedrock:InvokeModel`, `s3:GetObject/PutObject/ListBucket`.

## Limites connues et prérequis

- **Modèles** : tous les modèles Bedrock ne sont pas forcément activés sur votre compte. Les IDs sont configurables et à vérifier avec `check-routes` ; en cas d'indisponibilité, le routeur passe au modèle suivant de la route.
- **Coût** : `estimated_cost_usd` vaut `None` tant que `LLM_PRICING` n'est pas renseigné (prix Bedrock à copier depuis la page de tarification AWS).
- **Évaluation** : 4 cas seulement ; le juge LLM est stochastique (±0,25 observé) et le baseline dépend des modèles utilisés.
- **Agents** : ce sont des squelettes qui appellent le LLM ; les données de marché et les calculs viendront des autres membres.
- **ECS Fargate** : `Dockerfile` fourni mais **rien n'est déployé** ; pas de serveur HTTP dans ce MVP.
- **MLflow** : base SQLite locale (`mlflow.db`, ignorée par git) ; le backend « fichiers » est déprécié.
- **Tests S3** : simulés avec `moto` (aucun appel AWS). L'adaptateur S3 n'a pas été testé sur un vrai bucket.
- Python 3.11+ (testé avec 3.14).

## Scripts d'exemple

`scripts/` : `check_aws_identity.py` (identité AWS), `example_converse.py` (API Converse avec Nova et Sonnet),
`example_anthropic_bedrock.py` (SDK Anthropic sur Bedrock).
