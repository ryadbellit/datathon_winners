# AlphaForge AI

Multi-agent financial analysis system with adversarial debate. 6 AI agents argue with each other before reaching conclusions.

**Demo:** https://d21ksxcxsl84gd.cloudfront.net

## What It Does

Ask: *"Why did NVIDIA drop and what does it mean for my portfolio?"*

Get: Evidence-backed analysis with complete transparency. See every agent's reasoning in the debug view.

### The 6 Agents

1. **Research** - Gathers evidence (news, prices, knowledge base). Every fact tagged with source + date.
2. **Event Hunter** - Identifies market events, distinguishes verified from speculation.
3. **Portfolio Storyteller** - Explains impact on YOUR portfolio. Integrates GARCH volatility models.
4. **Conspiracy Theorist** - Proposes wild theories (stress test). Always marked "unproven".
5. **Devil's Advocate** - Challenges every claim. Agents must defend or concede.
6. **Governance** - Validates evidence, rejects unsupported claims, caps verdict quality.

**Flow:** Research → (Events ‖ Portfolio ‖ Conspiracy) → Devil's Advocate → Rebuttals → Governance → Synthesis

## Quick Setup

### Prerequisites
- Python 3.11+
- Node.js 22+
- AWS credentials (optional - works with mock LLM)

### Install

```bash
# Backend
cd server
uv sync

# Frontend
cd alphaforge-ai
npm install

# Config
cp .env.example .env
# Edit .env: Set LLM_ROUTES (mock or bedrock)
```

### Run

**Terminal 1 - API:**
```bash
server\.venv\Scripts\python.exe -m flask --app server.src.main run --port 5000
```

**Terminal 2 - Frontend:**
```bash
cd alphaforge-ai
npm run dev
```

Open http://localhost:5173

## Configuration

**Mock mode (no AWS):**
```bash
LLM_ROUTES='{"default": ["mock:mock-model"]}'
```

**Bedrock mode:**
```bash
LLM_ROUTES='{"orchestration": ["bedrock:global.anthropic.claude-sonnet-5-5"], "agent": ["bedrock:global.anthropic.claude-haiku-5-5"]}'
LLM_MAX_TOKENS='{"orchestration": 8192, "agent": 4096}'
AWS_REGION=us-east-1
KNOWLEDGE_BASE_ID=your-kb-id
MARKET_DATA=yahoo
```

See `.env.example` for all options.

## Testing

```bash
# All tests (no AWS calls)
server\.venv\Scripts\python.exe -m pytest -q

# Check Bedrock connectivity
server\.venv\Scripts\python.exe -m alphaforge check-routes

# CLI analysis
python -m alphaforge analyze "Why did NVIDIA drop?" --ticker NVDA \
  --news examples\team\news.json --prices examples\team\prices.json \
  --portfolio examples\team\portfolio.json --as-of 2025-01-28
```

## Debug View

See complete agent reasoning:

1. Ask a question in Scenario chat
2. Wait ~90 seconds for analysis
3. Click 🐛 icon on the answer
4. Explore: agent outputs, debate flow, evidence validation

**What you see:**
- Full JSON from each agent
- Devil's Advocate challenges + rebuttals
- Conspiracy theories + governance review
- Evidence with validation status
- Confidence scores, token usage

## Project Structure

```
alphaforge/              # Python backend
├── team/               # 6-agent debate system
│   ├── research.py     # Evidence gathering
│   ├── events.py       # Market events
│   ├── portfolio.py    # Portfolio impact
│   ├── conspiracy.py   # Stress test theories
│   ├── devil.py        # Challenges claims
│   └── governance.py   # Final validation
├── llm.py             # Bedrock + mock providers
├── cli.py             # Commands: ask, analyze, evaluate
└── contracts.py       # Pydantic schemas

alphaforge-ai/          # React frontend
├── features/
│   ├── scenarios/     # Chat interface
│   └── debug/         # Admin debug view
└── api/               # API client

server/                 # Flask API
├── src/
│   ├── main.py        # /api/analyze endpoint
│   └── risk/          # GARCH volatility models
└── pyproject.toml

tests/                  # 46 tests, 6 skipped
examples/team/          # Sample data files
```

## Key Features

✅ **Zero hallucinations** - Evidence created by code, strict validation  
✅ **Adversarial debate** - Agents genuinely challenge each other  
✅ **Complete transparency** - Debug view shows all reasoning  
✅ **Production ready** - Rate limiting, cost tracking, graceful degradation  
✅ **Real risk models** - GARCH + Monte Carlo simulation  

## Architecture

**Backend:** Python + LangGraph + AWS Bedrock (Claude Haiku/Sonnet) + Flask  
**Frontend:** React + TypeScript + Vite  
**Models:** Haiku for speed (research, events), Sonnet for quality (governance, synthesis)  
**Evidence:** Created by code (E1, E2...), never by LLM. Agents only cite IDs.  
**Validation:** Numbers, causality, dates all checked against cited sources.  

**Typical analysis:**
- Duration: 85-110 seconds
- API calls: 8-11 Bedrock calls
- Cost: ~$0.10-0.15
- Tokens: ~20-25k input, ~15-20k output

## AWS Resources

- **Bedrock Models:** Claude Haiku 5.5 (agents) + Sonnet 5.5 (synthesis, governance)
- **Knowledge Base:** RAG for documents (optional)
- **Guardrail:** Content filtering (optional)
- **S3:** Datasets, reports archive
- **CloudWatch:** Structured logging

See `.env.example` for IAM permissions.

## Documentation

- **SETUP_AND_TESTING_GUIDE.md** - Detailed setup, troubleshooting, AWS config
- **alphaforge/team/README.md** - Agent architecture, debate flow
- **CLEANUP_SUMMARY.md** - Recent code cleanup details

## Troubleshooting

**JSON truncation errors:** Increase token limits in `.env`  
**0 conspiracy theories:** Restart Flask after prompt changes  
**TypeScript errors:** Run `npm run typecheck` in `alphaforge-ai`  
**Tests fail:** Check `server/.venv` has all dependencies (`uv sync`)

## Tech Stack

Python · React · TypeScript · AWS Bedrock · LangGraph · Flask · Pydantic · GARCH · yfinance

---

Built for Datathon PolyFinances 2026. Simulation only - not financial advice.
