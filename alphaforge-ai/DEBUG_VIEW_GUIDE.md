# Agent Debug View Guide

## Overview
The Agent Debug View provides detailed visibility into the reasoning and outputs of all 6 agents in the multi-agent system.

## How to Access

1. **From the Scenario Chat:**
   - Ask a question in the Scenario analysis chat (http://localhost:5173/scenarios)
   - Wait for the analysis to complete
   - Click the **bug icon** (🐛) in the top-right corner of the answer box
   - This opens the debug view with full agent details

2. **Direct URL:**
   - Navigate to http://localhost:5173/debug

## Features

### 1. **Agents Tab** (Default View)
- **Left Sidebar:** List of all 6 agents with status badges
  - ✅ `ok` - Agent completed successfully
  - ⚠️ `partial` - Agent completed with limitations
  - ❌ `failed` - Agent encountered an error
  - ⏸️ `skipped` - Agent was not needed
  - 📭 `no_evidence` - Agent had no data to process

- **Main Panel:** Complete output for the selected agent
  - Status and confidence score
  - Full JSON output with all fields
  - Error messages (if any)

### 2. **Debate Tab**
Shows the complete debate flow between agents:

- **Challenges:** Devil's Advocate objections to other agents
  - Target agent
  - Severity (high/medium/low)
  - Claim being challenged
  - Objection reasoning
  - Evidence cited

- **Rebuttals:** Agents' responses to challenges
  - Which agent is responding
  - Their response
  - Evidence cited in defense
  - Whether they concede
  - Missing evidence noted

- **Conspiracy Theory Review:** Governance verdict on each conspiracy theory
  - Theory text
  - Verdict (rejected/unproven)
  - Reasoning

- **Alternative Hypotheses:** Other possible interpretations from Devil's Advocate

### 3. **Evidence Tab**
All evidence gathered and validated by the research agent:
- Evidence ID (e.g., E1, E2...)
- Type (news, price, document, knowledge_base)
- Validation status (verified/undated)
- Claim and excerpt
- Source and reference
- Date and value (if applicable)

## Agent List

1. **Research** - Gathers and validates evidence from multiple sources
2. **Event Hunter** - Identifies and categorizes market events
3. **Portfolio Storyteller** - Explains impact on the specific portfolio
4. **Conspiracy Theorist** - Proposes alternative interpretations (stress test)
5. **Devil's Advocate** - Challenges assumptions and identifies weaknesses
6. **Governance** - Final arbitration and validation of claims

## Use Cases

### For Development
- Debug agent failures and errors
- Understand why certain evidence was accepted/rejected
- See the complete reasoning chain
- Verify debate rounds are working correctly

### For Demo/Presentation
- Show the multi-agent collaboration in action
- Explain how conspiracy theories are evaluated
- Demonstrate evidence validation
- Show the debate mechanism

### For Analysis Quality
- Check which evidence each agent used
- See confidence scores
- Understand why certain claims were rejected
- Verify the governance review

## Technical Details

- The debug view receives the full `TeamReport` from the API
- Report data is passed via URL query parameter (JSON encoded)
- All 6 agents' outputs are displayed with their complete structure
- The view is read-only (no actions modify the analysis)

## Example Workflow

1. Ask: "Why did NVIDIA drop and what's the impact on my portfolio?"
2. Wait ~110 seconds for the 6-agent analysis
3. Click the bug icon in the answer box
4. Review each agent's reasoning in the Agents tab
5. Check the Debate tab to see challenges and responses
6. View all Evidence to understand what data was used
