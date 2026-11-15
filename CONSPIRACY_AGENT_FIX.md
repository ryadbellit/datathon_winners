# Conspiracy Agent Fix - Generating More Theories

## Problem
The conspiracy theorist agent was running successfully (status: "ok") but not generating any theories:
```json
{
  "confidence": 0.05,
  "theories": [],
  "status": "ok"
}
```

## Root Cause
The agent's prompt was too cautious and didn't encourage theory generation strongly enough. The model was being conservative and needed clearer direction to generate conspiracy theories.

## Changes Made

### 1. **More Aggressive Prompt** (`alphaforge/team/conspiracy.py`)
- Changed from passive "propose des théories" to **"Tu DOIS proposer 2 à 3 théories"**
- Added emphasis: **"PROFONDÉMENT convaincu"**, **"RIEN n'arrive par hasard"**, **"CHAQUE mouvement"**
- Added concrete examples of typical conspiracy theories:
  - Government orchestrating events to justify regulation
  - Central banks coordinating to control prices
  - Regulators timing announcements to advantage certain actors
  - Insider information leaks

### 2. **Explicit Schema Instructions**
Added to the schema prompt:
```
IMPORTANT: Tu DOIS proposer au moins 2 théories même si les preuves semblent insuffisantes. 
Sois créatif dans tes interprétations complotistes.
```

### 3. **Confidence Floor**
```python
# Confidence floor: a conspiracy theorist should be confident even with weak evidence
raw_confidence = data.get("confidence", 0.5)
confidence = max(0.4, raw_confidence) if theories else raw_confidence
```
- Minimum 40% confidence when theories are generated
- Default confidence increased from 0.3 to 0.5

## Testing the Fix

### Quick Test (Mock LLM)
```powershell
cd C:\Users\Ryad\datathon_winners
server\.venv\Scripts\python.exe -m pytest -q tests/test_team.py::test_conspiracy_theories_are_unproven_and_cannot_invent_numbers_or_evidence
```
Expected: ✅ Test passes (verifies structure)

### Full Test (Real Bedrock)

1. **Restart the API** (to load the new prompt):
   ```powershell
   # Stop the current Flask server (Ctrl+C)
   # Then restart:
   cd C:\Users\Ryad\datathon_winners
   server\.venv\Scripts\python.exe -m flask --app server.src.main run --port 5000
   ```

2. **Ask a question** in the Scenario chat that has evidence:
   - Good: "Why did NVIDIA drop?" (with real ticker, yfinance provides data)
   - Good: "What caused the market volatility recently?"
   - Bad: "What do you think?" (too vague, no evidence)

3. **Wait for analysis** (~90-110 seconds)

4. **Click the bug icon (🐛)** to open debug view

5. **Check Conspiracy Theorist output:**
   ```json
   {
     "confidence": 0.4-0.8,  // Should be higher now
     "theories": [
       {
         "text": "...",
         "suspected_actor": "gouvernement",
         "alleged_motive": "...",
         "evidence_ids": ["E1", "E2"],
         "would_prove_it": "..."
       },
       // Should have 2-3 theories
     ],
     "status": "ok"
   }
   ```

6. **Check the Debate tab:**
   - Scroll to "Conspiracy Theory Review"
   - Should show 2-3 theories with governance verdicts (rejected/unproven)

## Expected Behavior

### Before Fix
- Status: "ok"
- Theories: `[]` (empty)
- Confidence: 0.05 (5%)

### After Fix
- Status: "ok"
- Theories: 2-3 theories
- Confidence: 0.4+ (40%+)
- Each theory should have:
  - Clear text describing the conspiracy
  - Suspected actor (government, central bank, regulator, etc.)
  - Alleged motive
  - Evidence IDs cited
  - What would prove/disprove it

## Example Theory Output

```json
{
  "text": "Le gouvernement pourrait avoir orchestré cette baisse pour justifier une nouvelle régulation du secteur tech, en utilisant le timing de l'annonce pour amplifier l'impact.",
  "suspected_actor": "gouvernement",
  "alleged_motive": "Justifier une intervention réglementaire dans le secteur technologique",
  "evidence_ids": ["E1", "E2"],
  "would_prove_it": "Un document gouvernemental préalable à la baisse discutant d'une future régulation du secteur, ou des preuves de coordination entre régulateurs."
}
```

## Governance Review

The governance agent will review each theory and mark it as:
- **"rejected"**: Evidence contradicts the theory
- **"unproven"**: No evidence supports it, but nothing contradicts it either

This is expected and correct behavior - conspiracy theories should be marked as unproven!

## Troubleshooting

### If still generating 0 theories:

1. **Check the evidence:**
   - In debug view, go to Evidence tab
   - Should have at least 1-2 evidence items
   - If empty, the research agent failed to find data

2. **Check the model response:**
   - Look at Flask terminal logs
   - Search for `conspiracy_theorist` entries
   - Check if `stop_reason: max_tokens` (means truncated)

3. **Try a more specific question:**
   - Include a real ticker: "Why did NVDA drop?"
   - Reference recent events: "What caused the tech selloff?"
   - Avoid vague questions: "Tell me about the market"

4. **Verify the prompt loaded:**
   ```python
   # In Python
   from alphaforge.team.conspiracy import ConspiracyTheorist
   from alphaforge.llm import ModelRouter
   from alphaforge.config import get_settings
   
   router = ModelRouter.from_settings(get_settings(), [])
   agent = ConspiracyTheorist(router)
   print(agent.role)  # Should show the new aggressive prompt
   ```

## What Makes a Good Conspiracy Theory

According to the updated prompt, theories should:
- ✅ Be based on evidence (cite E1, E2, etc.)
- ✅ Identify a suspected actor (government, central bank, regulator)
- ✅ Propose a motive (control markets, justify regulation, advantage insiders)
- ✅ Suggest what would prove or disprove it
- ❌ NOT invent numbers
- ❌ NOT invent sources
- ❌ NOT name specific people

The more dramatic the timing/coincidence in the evidence, the better the conspiracy theory!
