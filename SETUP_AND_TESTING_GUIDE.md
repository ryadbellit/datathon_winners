# AlphaForge Setup & Testing Guide

Complete guide for setting up, testing, and debugging the 6-agent AlphaForge system.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 22+
- AWS credentials with Bedrock access (or use mock mode)

### Installation

```powershell
# Backend
cd server
uv sync

# Frontend
cd alphaforge-ai
npm install
```

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
# For local development with mock LLM (no AWS)
LLM_ROUTES='{"default": ["mock:mock-model"]}'

# For production with AWS Bedrock
LLM_ROUTES='{"orchestration": ["bedrock:global.anthropic.claude-sonnet-5-5"], "agent": ["bedrock:global.anthropic.claude-haiku-5-5"]}'
AWS_REGION=us-east-1
KNOWLEDGE_BASE_ID=your-kb-id
MARKET_DATA=yahoo
```

Full configuration options in `.env.example`.

## Running the Application

### Development (Local)

**Terminal 1 - API:**
```powershell
cd C:\Users\Ryad\datathon_winners
server\.venv\Scripts\python.exe -m flask --app server.src.main run --port 5000
```

**Terminal 2 - Frontend:**
```powershell
cd alphaforge-ai
npm run dev
```

Open http://localhost:5173

### Testing

**All tests (no AWS calls):**
```powershell
server\.venv\Scripts\python.exe -m pytest -q
```

**Test specific agent:**
```powershell
server\.venv\Scripts\python.exe -m pytest -q tests/test_team.py::test_conspiracy_theories_are_unproven_and_cannot_invent_numbers_or_evidence
```

**Check Bedrock connectivity:**
```powershell
server\.venv\Scripts\python.exe -m alphaforge check-routes
```

### Command Line Usage

**6-agent analysis with debate:**
```powershell
python -m alphaforge analyze "Why did NVIDIA drop?" --ticker NVDA --persona prudent `
    --news examples\team\news.json --prices examples\team\prices.json --portfolio examples\team\portfolio.json --as-of 2025-01-28
```

**Simple 3-agent analysis:**
```powershell
python -m alphaforge ask "What are the risks of Alpha Inc.?" --persona prudent --doc document.txt
```

## Admin Debug View

### Accessing the Debug View

1. Go to http://localhost:5173/scenarios
2. Ask a question (e.g., "Why did NVIDIA drop?")
3. Wait ~90-110 seconds for analysis
4. Click the **bug icon (🐛)** in top-right of answer
5. Debug view opens with complete agent reasoning

### Debug View Features

**Agents Tab:**
- Sidebar lists all 6 agents with status badges
- Click any agent to see full JSON output
- Status indicators: ok, partial, failed, skipped, no_evidence

**Debate Tab:**
- Devil's Advocate challenges (target, severity, objection)
- Agent rebuttals with evidence citations
- Conspiracy theory governance review
- Alternative hypotheses

**Evidence Tab:**
- All evidence gathered (E1, E2, E3...)
- Validation status (verified/undated)
- Source, date, claim, excerpt

### Troubleshooting Debug View

**If "No analysis to debug" appears:**
1. Check browser console for logs
2. Verify API returned agent data: look for "Analysis complete" log
3. Check sessionStorage: `sessionStorage.getItem('debugReport')`
4. Restart Flask server to reload code changes

**Expected agent statuses:**
- Research: `ok` (always has evidence)
- Event Hunter: `ok` or `partial` (depends on news)
- Portfolio Storyteller: `ok` if holdings provided
- Conspiracy Theorist: `ok` (generates 2-3 theories)
- Devil's Advocate: `ok` or `failed` (can hit token limits)
- Governance: `ok` (always runs)

## Conspiracy Agent Details

### How It Works

The conspiracy theorist agent proposes 2-3 alternative interpretations suggesting government/regulator manipulation. This serves as a "stress test" - the system must address wild theories before presenting conclusions.

**Key behaviors:**
- Confidence floor: minimum 40% when theories generated
- Must propose at least 2 theories even with weak evidence
- Can only cite existing evidence (no fabrication)
- Governance reviews each theory (rejected/unproven, never validated)

### Testing Conspiracy Agent

**After modifying the prompt, restart Flask:**
```powershell
# Ctrl+C to stop Flask, then restart:
server\.venv\Scripts\python.exe -m flask --app server.src.main run --port 5000
```

**Expected output:**
```json
{
  "confidence": 0.4-0.8,
  "theories": [
    {
      "text": "Le gouvernement pourrait avoir orchestré...",
      "suspected_actor": "gouvernement",
      "alleged_motive": "Justifier une intervention réglementaire",
      "evidence_ids": ["E1", "E2"],
      "would_prove_it": "Un document gouvernemental préalable..."
    }
  ],
  "status": "ok"
}
```

**If still getting 0 theories:**
1. Check evidence in debug view (need at least 1-2 items)
2. Use specific questions with real tickers
3. Check Flask logs for truncation (stop_reason: max_tokens)

## AWS Setup (Production)

### Required Resources

**Bedrock Models:**
- Claude Haiku 5.5: `global.anthropic.claude-haiku-5-5` (agents)
- Claude Sonnet 5.5: `global.anthropic.claude-sonnet-5-5` (synthesis, governance)

**Optional:**
- Knowledge Base (RAG for documents)
- Guardrail (content filtering)
- S3 bucket (for datasets/reports)
- CloudWatch log group (structured logging)

### IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:*:ACCOUNT_ID:inference-profile/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve"],
      "Resource": "arn:aws:bedrock:*:ACCOUNT_ID:knowledge-base/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::BUCKET/alphaforge/*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:ACCOUNT_ID:log-group:/alphaforge/*"
    }
  ]
}
```

### Known Issues & Fixes

**JSON Truncation (InvalidOutputError):**
- Symptom: Agents fail with truncated JSON
- Cause: Token limits too low for verbose models
- Fix: Set in `.env`:
  ```
  LLM_MAX_TOKENS='{"orchestration": 8192, "agent": 4096, "arbitration": 6000}'
  ```

**Git Bash Path Mangling:**
- Symptom: AWS CLI fails with log group path
- Fix: Prefix commands with `MSYS_NO_PATHCONV=1`

**Missing arch Package:**
- Symptom: ImportError for GARCH models
- Fix: Already declared in `server/pyproject.toml`

## Cost & Performance

**Typical analysis:**
- Duration: 85-110 seconds
- API calls: 8-11 Bedrock calls
- Cost: ~$0.10-0.15 (with pricing configured)
- Tokens: ~20-25k input, ~15-20k output

**Optimization tips:**
- Use Haiku for research/events/portfolio (fast, cheap)
- Use Sonnet only for synthesis/governance (quality)
- Set max_tokens appropriately (don't over-allocate)

## Project Structure

```
├── alphaforge/              # Python backend
│   ├── team/               # 6-agent system
│   │   ├── research.py     # Evidence gathering
│   │   ├── events.py       # Market event detection
│   │   ├── portfolio.py    # Portfolio impact
│   │   ├── conspiracy.py   # Alternative theories
│   │   ├── devil.py        # Devil's advocate
│   │   └── governance.py   # Final validation
│   ├── agents.py           # Old 3-agent system (still used by /ask)
│   ├── llm.py              # Bedrock + mock providers
│   └── cli.py              # Command line interface
├── alphaforge-ai/          # React frontend
│   └── src/
│       ├── features/
│       │   ├── scenarios/  # Chat interface
│       │   └── debug/      # Admin debug view
│       └── api/            # API client
├── server/                 # Flask API
│   └── src/
│       ├── main.py         # /api/analyze endpoint
│       └── risk/           # GARCH models
├── tests/                  # Test suite
└── examples/               # Example data files
```

## Further Reading

- Main README: Project overview, architecture, deployment
- Team README: `alphaforge/team/README.md` - Agent details
- Frontend README: `alphaforge-ai/README.md` - UI components
- .env.example: All configuration options
