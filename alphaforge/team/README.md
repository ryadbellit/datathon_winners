# Équipe de 5 agents (`alphaforge/team/`)

Question type : *« Pourquoi l'action NVIDIA a-t-elle baissé et quel impact sur mon portefeuille ? »*
Le système répond avec des **preuves citées**, un **débat borné**, un **verdict prudent** et des **limites explicites**.
Chaque agent a son fichier : **chacun peut reprendre un agent sans toucher aux autres.**

```
question + profil + portefeuille
        │
   1. research ──(aucune preuve ? → direct à la gouvernance)
        ├───────────────┐   en parallèle : ils ne dépendent que des preuves
   2. event_hunter   3. portfolio_storyteller
        └───────┬───────┘
   4. devils_advocate ──(objection sérieuse ? sinon on saute le tour 2)
        │  tour 2 : seuls les agents objectés répondent (en parallèle, avec des preuves EXISTANTES)
   5. governance  ──► verdict : supported | partially_supported | insufficient_evidence
        │
   synthèse finale (6 sections, Guardrail) ──► TeamReport
```

## Les agents

| # | Fichier | Mission | Sortie (extrait) | Modèle (tâche) |
|---|---|---|---|---|
| 1 | `research.py` | Rassembler les preuves (Knowledge Base, documents, actualités, prix), les dater et les sourcer | `evidence`, `key_facts`, `data_as_of`, `missing_information` | agent (économique) |
| 2 | `events.py` | Identifier les événements du marché et les classer, sans affirmer de cause | `identified_events`, `event_timeline`, `alternative_explanations` | agent |
| 3 | `portfolio.py` | Expliquer l'impact sur **le** portefeuille et vulgariser les notions | `direct_exposure`, `indirect_exposure`, `educational_explanation` | agent |
| 4 | `devil.py` | Contester l'interprétation (objections ciblées) | `challenged_claims`, `alternative_hypotheses`, `evidence_needed` | arbitration (fort) |
| 5 | `governance.py` | Arbitrer : valider/rejeter, plafonner le verdict | `validated_claims`, `rejected_claims`, `final_assessment` | arbitration (fort) |

Autres fichiers : `base.py` (preuves, sortie typée, appel LLM JSON, règles communes), `graph.py` (graphe LangGraph, débat, synthèse,
`TeamOrchestrator`), `interfaces.py` (ce que les autres équipes doivent brancher).

## Règles qui s'appliquent à tous (déjà codées, à conserver)

- **Les preuves sont créées par le code** (`E1`, `E2`…), jamais par le LLM. Un agent ne peut que **citer** un ID existant ; un ID inconnu est supprimé.
- **Aucun chiffre non étayé** : un fait dont un chiffre n'apparaît pas dans les preuves citées est retiré (`numbers_supported`).
- **Pas de causalité sans preuve** : un événement n'est `verified` que s'il cite une preuve datée et sourcée ; sa date vient de la preuve, pas du LLM.
- **Pas de donnée → on le dit** : sans preuve, sans actualité ou sans portefeuille, l'agent l'écrit (et ne fait **aucun appel LLM** quand il n'a rien à analyser).
- **Un échec d'agent est visible** (`status="failed"`, `error=...`) : jamais remplacé par une sortie inventée.
- **La gouvernance ne peut que durcir** : le verdict est plafonné par le code (pas de fait validé → `insufficient_evidence` ; désaccord non résolu,
  agent en échec ou partiel → au plus `partially_supported`).
- Pas de conseil d'achat/vente, pas de calcul financier ici (voir `interfaces.py`).

## Débat (max. 2 tours, pas de boucle)

1. **Tour 1** : agents 1-3, puis l'avocat du diable contre-attaque (`severity` : high / medium / low).
2. **Tour 2** seulement s'il existe une objection `high`/`medium` adressée à un agent qui a produit quelque chose : cet agent répond avec des preuves
   existantes, ou indique ce qui manque (`missing_evidence`), ou concède. Aucun nouveau tour ensuite.
3. **Arbitrage** par la gouvernance. Une objection `high` sans réponse étayée reste « non levée » dans le verdict.

## Reprendre un agent : mode d'emploi

1. Ouvrez **son fichier uniquement** : `role` (prompt système), `SCHEMA` (JSON demandé), classe `...Output` (contrat Pydantic), `run(...)`.
2. Gardez la signature de `run` et les **noms des champs de sortie** (les autres agents les lisent). Pour ajouter un champ : ajoutez-le avec une valeur par défaut.
3. Ne mettez **jamais d'ID de modèle** dans le code : seul `task` (`"agent"` ou `"arbitration"`) choisit le modèle via `LLM_ROUTES`.
4. Toute donnée externe passe par `interfaces.py` (ne rien inventer, ne pas appeler d'API directement dans un agent).
5. Lancez les tests (ci-dessous). Un test par comportement que vous ajoutez, avec le fournisseur scripté de `tests/test_team.py` (aucun appel AWS).

Idées d'évolution par agent : **1** vraies sources (API de news, filings), score de fiabilité des sources ; **2** classification plus fine, détection d'événements
macro ; **3** brancher le module quantitatif (volatilité, corrélations, stress tests) via `QuantMetrics` ; **4** objections plus ciblées (hypothèses déjà intégrées au prix) ;
**5** règles de conformité plus fines (adéquation profil/horizon).

## Interfaces à brancher (équipes finance/ML et frontend)

| Interface (`interfaces.py`) | Rôle | Sans elle |
|---|---|---|
| `MarketData.news(query, tickers)`, `.prices(ticker)` | Actualités et prix datés | on utilise `request.news` / `request.prices` s'ils sont fournis, sinon « aucune donnée » |
| `PortfolioProvider.get(user_id)` | Profil et portefeuille structurés (`Portfolio`) | `request.portfolio` ou analyse générale seulement |
| `QuantMetrics.observations(portfolio, tickers)` | Métriques chiffrées (`Observation`) | aucune métrique chiffrée, limite signalée |

Le frontend appelle `TeamOrchestrator(llm, kb, market, quant, portfolios).run(AnalysisRequest(...))` et reçoit un `TeamReport` : `answer` (Markdown, 6 sections),
`assessment`, `evidence`, `sources`, les sorties de chaque agent, `rebuttals`, `governance`, `usage`, `estimated_cost_usd`, `failures`.

## Lancer

```powershell
pip install -e ".[dev]"
python -m pytest -q                                   # 25 tests, fournisseur scripté, aucun appel AWS
python -m alphaforge analyze "Pourquoi NVIDIA a baissé ?" --ticker NVDA --persona prudent `
    --news news.json --prices prices.json --portfolio portfolio.json --as-of 2025-01-28
python -m alphaforge evaluate --team --dataset golden_team_v1 --mlflow
```

Avec les routes mock par défaut le workflow tourne sans AWS (réponses vides mais contrat respecté). Avec Bedrock : une analyse complète coûte environ
7 appels (3 agents économiques, 1 réponse de débat, avocat + gouvernance + synthèse sur le modèle fort) — env. 0,1 $ avec Sonnet 5.5/Haiku 5.5.

## Observabilité

Chaque agent journalise `agent_end` (statut, tour de débat, `prompt_version`, modèle, tokens, coût, durée, IDs de preuves) ; chaque appel `model_call`
(avec `agent`) ; la requête `request_end` (verdict, tours, nombre de preuves, échecs). Ce sont des **logs structurés** (CloudWatch) : **MLflow Tracing n'est pas branché**,
seule l'évaluation (`evaluate --mlflow`) est suivie dans MLflow.
