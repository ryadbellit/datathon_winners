# AlphaForge AI

Orchestrateur multi-agents (LangGraph) : trois agents analysent une question financière en parallèle (documents, sentiment,
risque selon le persona Prudent / Équilibré / Audacieux), puis un modèle synthétise. Les appels passent par un `ModelRouter` :
**Amazon Bedrock** ou un **mock local** (sans AWS). L'équipe de 5 agents (`analyze`) ajoute un débat contradictoire et un verdict fondé sur les preuves. Ce dépôt ne contient ni frontend, ni calculs financiers, ni modèles ML.

```
question + persona
   ├─ document_analyst ─┐  (Knowledge Base)
   ├─ sentiment ────────┼─► synthèse (+ Guardrail) ─► réponse, sources, tokens, coût
   └─ risk_explainer ───┘  (Knowledge Base)
chaque appel : ModelRouter ─► tâche (agent | orchestration | evaluation) ─► modèle, avec fallback
```

| Fichier (`alphaforge/`) | Rôle |
|---|---|
| `contracts.py` | Formats de données Pydantic et State LangGraph |
| `orchestrator.py`, `agents.py` | Le graphe, et les 3 agents (squelettes, sans calcul financier) |
| `llm.py` | Interface fournisseur, Mock, Bedrock (API Converse), `ModelRouter` (fallback, coût, guardrail) |
| `retrieval.py` | Recherche dans la Knowledge Base Bedrock |
| `storage.py` | Stockage local ou S3 (datasets, rapports, baselines) |
| `observability.py` | Logs JSON (CloudWatch), métriques, suivi des tokens et du coût |
| `evaluation.py` | Règles + juge LLM, détection de régression, MLflow |
| `config.py`, `cli.py` | Configuration (`.env`) et commandes |
| `team/` | **Workflow à 5 agents avec débat** (preuves, événements, portefeuille, avocat du diable, gouvernance) : voir [`alphaforge/team/README.md`](alphaforge/team/README.md) |

## Application (API + interface)

```powershell
pip install -e ".[dev]"
flask --app server.src.main run --port 5000        # API : POST /api/analyze, GET /api/health (MARKET_DATA=yahoo pour de vraies actualités/prix)
cd alphaforge-ai; npm install; npm run dev        # interface (proxy /api -> :5000) ; le chat de « Scenario analysis » interroge les 5 agents
```
`server/src/main.py` traduit profil + portefeuille du front en `AnalysisRequest` ; sans API joignable, le chat retombe sur la réponse simulée locale.

## Installation

```powershell
pip install -e .
copy .env.example .env      # puis éditez .env
```

## Utilisation

```powershell
python -m alphaforge check-routes                      # teste chaque modèle configuré
python -m alphaforge ask "Quels sont les risques d'Alpha Inc. ?" --persona prudent [--doc fichier.txt]
python -m alphaforge analyze "Pourquoi NVIDIA a baissé ?" --ticker NVDA --news n.json --prices p.json --portfolio pf.json   # 5 agents + débat
python -m pytest -q                                    # tests (aucun appel AWS)
python -m alphaforge upload-datasets                   # envoie ./data/datasets vers le stockage configuré (S3)
python -m alphaforge evaluate --dataset golden_v1 --mlflow
python -m alphaforge evaluate --save-baseline          # enregistre la référence
python -m alphaforge evaluate --baseline               # code de sortie 1 si régression
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

**Sans AWS** : laissez `LLM_ROUTES` par défaut (mock) et `STORAGE_BACKEND=local`. Une variable d'environnement qui redéfinit
`LLM_ROUTES` est fusionnée avec celle du `.env` : pour passer en local, modifiez le `.env`.

## Configuration (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `LLM_ROUTES` | mock | `{"tâche": ["fournisseur:model_id", ...]}`, fallback dans l'ordre ; tâches `orchestration`, `agent`, `evaluation`, `arbitration` (avocat du diable + gouvernance ; sans route : reprend `orchestration`, **sans Guardrail**), `default` ; fournisseurs `mock`, `bedrock` |
| `LLM_MAX_TOKENS` | 2048 / 4096 / 2048 / 600 | Limite de sortie par tâche (trop bas = réponses tronquées, événement `truncated`) |
| `LLM_PRICING` | `{}` | `{"model_id": {"input_per_1m": x, "output_per_1m": y}}` en USD ; vide = coût « inconnu » |
| `AWS_REGION` / `AWS_PROFILE` | `us-east-1` / vide | Région ; profil local (sinon chaîne par défaut de boto3 : rôle IAM, variables) |
| `BEDROCK_TIMEOUT_SECONDS`, `BEDROCK_MAX_RETRIES` | `60`, `3` | Délai et nouvelles tentatives |
| `GUARDRAIL_ID`, `GUARDRAIL_VERSION`, `GUARDRAIL_TASKS` | vide, `DRAFT`, `["orchestration"]` | Guardrail Bedrock (jamais sur `evaluation`) |
| `KNOWLEDGE_BASE_ID` | vide | Knowledge Base Bedrock : documents dans S3, **Sync** depuis la console |
| `STORAGE_BACKEND`, `LOCAL_STORAGE_DIR` | `local`, `./data` | `local` ou `s3` |
| `S3_BUCKET`, `S3_PREFIX` | vide, `alphaforge` | Bucket S3 |
| `CLOUDWATCH_LOG_GROUP`, `CLOUDWATCH_RETENTION_DAYS`, `CLOUDWATCH_METRICS` | vide, `14`, `false` | Logs et métriques (EMF) vers CloudWatch |
| `LOG_LEVEL`, `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT` | `INFO`, `sqlite:///mlflow.db`, `alphaforge` | |

Ne jamais mettre d'identifiants dans le code ; le `.env` est ignoré par git. Les jetons d'atelier expirent (`ExpiredToken` : les recopier).
Sous Git Bash, ne pas exporter `/alphaforge/app` en variable d'environnement (converti en chemin Windows) : le mettre dans le `.env`.

## Comportement

- **Fallback** de modèle sur indisponibilité, limite de débit ou délai dépassé (pas sur une requête invalide). Erreurs typées.
- **Résilience** : un agent ou la Knowledge Base en panne ne fait pas échouer la requête (résultat dégradé, événement journalisé).
- **Logs JSON** : `request_id`, `model_call` (modèle, latence, tokens, coût), `agent_error`, `retrieval_error`, `truncated`,
  `guardrail_intervened`, `request_end`. Jamais de prompt, de question ni d'identifiant.
- **Coût** : tokens × `LLM_PRICING` ; `None` si un prix manque (jamais deviné). Estimation, pas la facture AWS.
- **Évaluation** : règles (mots attendus/interdits, promesses interdites) + juge LLM 1-5 ; `evaluate` n'utilise pas la Knowledge Base sauf `--with-kb`.

## Permissions IAM

Rôle de la tâche ECS, ou profil en local (à resserrer à vos ressources) :

```json
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
   "Resource": ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:<ACCOUNT_ID>:inference-profile/*"]},
  {"Effect": "Allow", "Action": ["bedrock:ApplyGuardrail"], "Resource": "arn:aws:bedrock:*:<ACCOUNT_ID>:guardrail/*"},
  {"Effect": "Allow", "Action": ["bedrock:Retrieve"], "Resource": "arn:aws:bedrock:*:<ACCOUNT_ID>:knowledge-base/*"},
  {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": "arn:aws:s3:::<BUCKET>/alphaforge/*"},
  {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::<BUCKET>"},
  {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:PutRetentionPolicy"],
   "Resource": "arn:aws:logs:*:<ACCOUNT_ID>:log-group:/alphaforge/*:*"}
]}
```

`bedrock:InvokeModel` sur un profil d'inférence `global.`/`us.` exige aussi les modèles sous-jacents (d'où `foundation-model/*`).
Les logs CloudWatch n'ont besoin d'un droit applicatif que si `CLOUDWATCH_LOG_GROUP` est défini ; avec le pilote `awslogs` d'ECS,
c'est le rôle d'exécution qui écrit.

## Limites connues

- Les IDs de modèles sont à vérifier sur votre compte (`check-routes`) : tous les modèles Bedrock ne sont pas forcément activés.
- 4 cas d'évaluation seulement ; le juge est stochastique (±0,25 observé) ; la baseline dépend des modèles utilisés.
- Les 3 agents de `ask` sont des squelettes. L'équipe de 5 agents n'a pas de source de données réelle (interfaces `team/interfaces.py` à brancher) et pas de MLflow Tracing.
- Pas d'API ni de frontend.
- Le `Dockerfile` (ECS Fargate) est fourni mais jamais construit ni déployé.
- Tests : `tests/test_team.py` couvre l'équipe de 5 agents (fournisseur scripté). Le reste se vérifie avec `check-routes`, `ask` et `evaluate`.
