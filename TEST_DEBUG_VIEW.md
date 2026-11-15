# Testing the Debug View

## Steps to Test

1. **Start both servers:**
   ```powershell
   # Terminal 1 - Backend
   cd C:\Users\Ryad\datathon_winners
   server\.venv\Scripts\python.exe -m flask --app server.src.main run --port 5000

   # Terminal 2 - Frontend  
   cd C:\Users\Ryad\datathon_winners\alphaforge-ai
   npm run dev
   ```

2. **Open the browser console** (F12) to see debug logs

3. **Go to Scenario chat:** http://localhost:5173/scenarios

4. **Ask a question:**
   - Example: "Why did NVIDIA drop?"
   - Wait ~90-110 seconds for the analysis

5. **Check console logs:**
   - After the analysis completes, you should see:
   ```
   Analysis complete, report has agent data: {
     hasResearch: true,
     hasEvents: true,
     hasPortfolio: true,
     hasConspiracy: true,
     hasDevil: true,
     hasGovernance: true,
     reportKeys: [...array of field names...]
   }
   ```

6. **Click the bug icon (🐛)** in the top-right of the answer box

7. **Verify debug page loads:**
   - Should show the Agent Debug View with all 6 agents listed
   - Click each agent to see their output
   - Check console for:
   ```
   Debug report loaded: {
     hasReport: true,
     hasEvidence: true,
     hasResearch: true,
     ...
   }
   ```

## Troubleshooting

### If "No analysis to debug" appears:

1. **Check browser console** for the debug logs
2. **Verify the API returned agent data:**
   - Look for the "Analysis complete" log
   - All `has*` fields should be `true`
3. **Check sessionStorage:**
   - In browser console, run: `sessionStorage.getItem('debugReport')`
   - Should show a large JSON object
4. **If agent fields are missing from the API response:**
   - Check the Flask terminal for errors
   - Verify the API endpoint is returning full TeamReport

### If specific agents show "No data available":

- The agent likely has `status: "skipped"` or `status: "no_evidence"`
- This is normal if there wasn't enough data for that agent
- Try a more specific question with real tickers like "NVDA"

### Expected agent statuses for a typical question:

- Research: `ok` (should always have evidence)
- Event Hunter: `ok` or `partial` (depends on news)
- Portfolio Storyteller: `ok` if you have holdings
- Conspiracy Theorist: `ok` (should generate 1-3 theories)
- Devil's Advocate: `ok` or `failed` (sometimes hits token limits)
- Governance: `ok` (should always run)

## What to Check in Each Tab

### Agents Tab
- Click each agent in the sidebar
- Verify the full JSON output appears
- Check confidence scores and status badges

### Debate Tab  
- Should show Devil's Advocate challenges
- Should show rebuttals if debate_rounds >= 2
- Should show conspiracy theory review
- Should show alternative hypotheses

### Evidence Tab
- Should show all evidence items (E1, E2, E3...)
- Each should have: claim, source, validation status
- Check that real data appears (not mock data)
