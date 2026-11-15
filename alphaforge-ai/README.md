# AlphaForge AI (prototype)

An investment decision guide prototype for a financial data challenge. It helps a user describe their investing situation, see an example mix of assets that fits that profile, explore why each asset appears, and test the mix against hypothetical market events.

**Everything is a simulation.** There are no real transactions, no real market data and no personalized financial advice.

## Install and run

Requires Node.js 20 or newer.

```bash
npm install
npm run dev        # development server at http://localhost:5173
```

Other commands:

```bash
npm run typecheck  # TypeScript check
npm run build      # type check and production build into dist/
npm run preview    # serve the production build locally
```

The app makes no network requests. Styles and fonts are local (the system sans-serif stack).

## Screens

- **Welcome** and **Onboarding**: a five-step investor profile (Goals, Risk comfort, Preferences, Experience, Summary). Steps validate their answers, Back keeps every answer, and Edit on the summary returns to it.
- **Overview**: verdict banner, future value fan chart, portfolio donut, key checks and Ask AlphaForge. Advanced adds metric cards, a holdings table with editable weights and Reset.
- **Discover Assets**: asset cards filtered and ordered by the profile rules, plus a "Why am I seeing this?" drawer and a wide "View analysis" drawer.
- **Scenario Analysis**: five hypothetical scenarios with impact, dollar effect, contributions and a bad-year comparison. Advanced adds a custom scenario builder.
- Other sidebar items (Compare, Agent Activity, Portfolio Simulator, Analysis Reports, Settings) are "Coming soon" placeholders.

Guided and Advanced is one global toggle in the top bar. It changes what is shown, never the numbers, and it persists.

## Project structure

```
src/
  data/          typed mock data: types, assets and scenarios, form options
  lib/engine.ts  all computations (discovery rules, portfolio statistics, fan chart, checks, scenarios, Ask answers)
  shared/        design tokens, formatting helpers, Zustand store, UI kit, layout
  features/
    form/        onboarding flow
    dashboard/   Overview
    discover/    Discover Assets
    scenarios/   Scenario Analysis
    misc/        welcome and placeholder pages
```

Data access is limited to `src/data` and the functions in `src/lib/engine.ts`. A real API could replace the mock data behind those functions later.

## Mock data and computation rules

- **Assets**: eight example assets (NVDA, MSFT, VOO, VT, VXUS, XIC, AGG, ZAG). Every figure is invented and labelled "Example data".
- **Base mix**: VT 35, VOO 25, MSFT 10, AGG 30. Other assets have their own base weights. Selected weights are renormalized to 100 percent.
- **Portfolio statistics**: expected return is the weighted average. Volatility uses a constant correlation of 0.5 between every pair: `variance = ½·Σ(wσ)² + ½·(Σwσ)²`.
- **Fan chart**: a log-normal model. At time t, the median, 5th and 95th percentile values use `drift·t + z·σ·√t` with z = 0, −1.645, +1.645, multiplied by a fictive $100,000.
- **Rough-year figure**: the 5th percentile one-year return from the same model.
- **Checks**: thresholds by risk comfort (volatility ceiling 8, 12 or 18 percent; bad-year limit −10, −18 or −30 percent). Diversification needs at least 3 holdings, no stock above 20 percent and no asset above 40 percent.
- **Scenarios**: impact is the sum of each asset's normalized weight times its assumed move. Dollar effects are rounded to the nearest hundred. Percentages with no valid input render as an em dash, never NaN.
- **Formatting**: every number goes through `src/shared/format.ts`.

## Assumptions and decisions

See the list delivered with the project summary. In short: the discovery threshold uses the ceilings from the spec, the initial selection is the four starting assets filtered by the profile, and Ask AlphaForge matches only the four preset questions.
