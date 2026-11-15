import { ASSETS, CORRELATIONS, SCENARIOS } from '../data/assets';
import type { Asset, AssetInterest, Comfort, Horizon, Profile, Scenario } from '../data/types';

/*
 * Pure computation layer. Every screen reads from these functions so the same
 * selection and weights always give the same figures. Percentages are plain
 * numbers (12.5 means 12.5%) unless a name says otherwise.
 */

export const CAPITAL = 100_000;
const Z_P5 = -1.645;
const Z_P95 = 1.645;

export const COMFORT_RULES: Record<
  Comfort,
  { volCeiling: number; badYearLimit: number; riskFitCeiling: number }
> = {
  stability: { volCeiling: 8, badYearLimit: -10, riskFitCeiling: 10 },
  'ups-downs': { volCeiling: 12, badYearLimit: -18, riskFitCeiling: 20 },
  fluctuations: { volCeiling: 18, badYearLimit: -30, riskFitCeiling: Number.POSITIVE_INFINITY },
};

export const HORIZON_YEARS: Record<Horizon, number> = { short: 3, medium: 5, long: 15 };
export const HORIZON_CHOICES = [1, 3, 5, 10, 15, 20];

export const isFiniteNumber = (n: unknown): n is number =>
  typeof n === 'number' && Number.isFinite(n);

/* ---------- Discovery ---------- */

function parseTerms(text: string): string[] {
  return text
    .split(/[,;]/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s && s !== 'none');
}

function matchesTerm(asset: Asset, term: string): boolean {
  return [asset.name, asset.ticker, ...asset.sectors, ...asset.keywords].some((v) =>
    v.toLowerCase().includes(term),
  );
}

export function matchesExclusions(asset: Asset, exclusions: string): boolean {
  return parseTerms(exclusions).some((t) => matchesTerm(asset, t));
}

function fitScore(asset: Asset, profile: Profile): number {
  let score = 0;
  const beginnerOrIntermediate = profile.knowledge !== 'advanced';
  if (asset.type === 'etf' && beginnerOrIntermediate && asset.sectors.includes('Diversified')) {
    score += 2; // broad funds first for Beginner and Intermediate users
  }
  if (asset.sectors.some((s) => profile.sectors.includes(s))) score += 1;
  if (profile.regions.includes(asset.region)) score += 1;
  return score;
}

/** Assets that pass the discovery rules, best fit first. */
export function discoverAssets(profile: Profile): Asset[] {
  const rules = COMFORT_RULES[profile.comfort];
  const wanted = profile.assetTypes;

  return ASSETS.filter((a) => {
    if (!wanted.includes(a.type as AssetInterest)) return false; // rule 1: asset types
    const regionOk =
      profile.regions.length === 0 ||
      profile.regions.includes('Global') ||
      a.regions.some((r) => profile.regions.includes(r)); // rule 2: regions
    const riskOk = a.vol <= rules.riskFitCeiling; // rule 3: risk fit
    const highVolStockOk =
      !(a.type === 'stock' && a.vol > 30) ||
      (profile.comfort !== 'stability' && profile.horizon !== 'short');
    const excluded = matchesExclusions(a, profile.exclusions); // rule 5
    return regionOk && riskOk && highVolStockOk && !excluded;
  }).sort((x, y) => {
    const d = fitScore(y, profile) - fitScore(x, profile); // rule 6 (rule 4 is informational)
    return d !== 0 ? d : x.vol - y.vol;
  });
}

/* ---------- Portfolio ---------- */

export interface Holding {
  asset: Asset;
  /** Normalized weight, percent. All holdings sum to 100. */
  weight: number;
}

/**
 * Normalized holdings for the selected assets. Overrides replace base weights;
 * the result always renormalizes to 100. Returns null when nothing usable is selected.
 */
export function buildHoldings(
  selected: Asset[],
  overrides: Record<string, number>,
): Holding[] | null {
  if (selected.length === 0) return null;
  const raw = selected.map((asset) => {
    const v = overrides[asset.ticker] ?? asset.baseWeight;
    return { asset, value: isFiniteNumber(v) ? Math.max(0, v) : 0 };
  });
  const total = raw.reduce((s, r) => s + r.value, 0);
  if (!(total > 0)) return null;
  return raw.map((r) => ({ asset: r.asset, weight: (r.value / total) * 100 }));
}

export interface PortfolioStats {
  /** Weighted average of historical annualised returns, percent (used as the model's drift, not a promise). */
  expReturn: number;
  /** Volatility from the historical correlation matrix (0.5 when a pair is missing), percent. */
  vol: number;
  /** 5th percentile one-year return from the lognormal model, percent. */
  p5OneYear: number;
}

export function portfolioStats(holdings: Holding[]): PortfolioStats {
  const w = holdings.map((h) => h.weight / 100);
  const expReturn = holdings.reduce((s, h, i) => s + w[i] * h.asset.expReturn, 0);
  const weighted = holdings.map((h, i) => w[i] * h.asset.vol);
  const corr = (a: string, b: string) => (a === b ? 1 : (CORRELATIONS[a]?.[b] ?? 0.5));
  // w' Σ w with Σ_ij = ρ_ij σ_i σ_j, in %^2
  const variance = holdings.reduce(
    (sum, hi, i) => sum + holdings.reduce((inner, hj, j) => inner + weighted[i] * weighted[j] * corr(hi.asset.ticker, hj.asset.ticker), 0),
    0,
  );
  const vol = Math.sqrt(Math.max(0, variance));
  const p5OneYear = (Math.exp(logDrift(expReturn, vol) + Z_P5 * (vol / 100)) - 1) * 100;
  return { expReturn, vol, p5OneYear };
}

/** Drift of log returns over one year: expected return minus half the variance. */
function logDrift(expReturnPct: number, volPct: number): number {
  return expReturnPct / 100 - 0.5 * (volPct / 100) ** 2;
}

/** Value of the fictive capital at `years` for a given percentile z-value. */
export function percentileValue(z: number, years: number, stats: PortfolioStats): number {
  const drift = logDrift(stats.expReturn, stats.vol);
  return CAPITAL * Math.exp(drift * years + z * (stats.vol / 100) * Math.sqrt(years));
}

export interface FanPoint {
  year: number;
  label: string;
  p5: number;
  median: number;
  p95: number;
  /** Stacked-area helpers: a transparent base and the 5th-to-95th band. */
  base: number;
  band: number;
}

export function fanSeries(stats: PortfolioStats, years: number): FanPoint[] {
  const steps = Math.max(1, Math.round(years * 4));
  const points: FanPoint[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / 4;
    const p5 = percentileValue(Z_P5, t, stats);
    const p95 = percentileValue(Z_P95, t, stats);
    points.push({
      year: t,
      label: t === 0 ? 'Start' : `Year ${t}`,
      p5,
      median: percentileValue(0, t, stats),
      p95,
      base: p5,
      band: Math.max(0, p95 - p5),
    });
  }
  return points;
}

export function horizonDefault(horizon: Horizon): number {
  return HORIZON_YEARS[horizon];
}

/* ---------- Checks ---------- */

export interface Check {
  id: 'risk' | 'badYear' | 'diversification' | 'exclusions';
  name: string;
  passed: boolean;
  guided: string;
  advanced: string;
  help: string;
}

export function computeChecks(
  holdings: Holding[],
  stats: PortfolioStats,
  profile: Profile,
): Check[] {
  const rules = COMFORT_RULES[profile.comfort];
  const n = holdings.length;
  const maxAsset = Math.max(...holdings.map((h) => h.weight));
  const stockWeights = holdings.filter((h) => h.asset.type === 'stock').map((h) => h.weight);
  const maxStock = stockWeights.length ? Math.max(...stockWeights) : 0;
  const matched = holdings.filter((h) => matchesExclusions(h.asset, profile.exclusions));

  const risk = stats.vol <= rules.volCeiling;
  const badYear = stats.p5OneYear >= rules.badYearLimit;
  const diversified = n >= 3 && maxStock <= 20 && maxAsset <= 40;
  const clean = matched.length === 0;

  return [
    {
      id: 'risk',
      name: 'Risk level',
      passed: risk,
      guided: risk ? 'On target' : 'Swings more than your comfort range',
      advanced: `Volatility ${stats.vol.toFixed(1)}% against a ${rules.volCeiling}% ceiling`,
      help: 'Give more weight to steadier holdings, such as broad funds or bonds.',
    },
    {
      id: 'badYear',
      name: 'Bad-year limit',
      passed: badYear,
      guided: badYear ? 'Good' : 'A rough year could fall further than you are comfortable with',
      advanced: `5th percentile one-year return ${stats.p5OneYear.toFixed(1)}% against the ${rules.badYearLimit}% limit`,
      help: 'Add more bonds or reduce the largest equity holdings.',
    },
    {
      id: 'diversification',
      name: 'Diversification',
      passed: diversified,
      guided: diversified ? 'Good' : 'Needs more spread',
      advanced: `${n} holdings, largest stock ${maxStock.toFixed(1)}%, largest holding ${maxAsset.toFixed(1)}%`,
      help: 'Hold at least 3 assets, keep single stocks at or below 20% and any asset at or below 40%.',
    },
    {
      id: 'exclusions',
      name: 'Profile exclusions',
      passed: clean,
      guided: clean ? 'Good' : `${matched.map((h) => h.asset.ticker).join(', ')} conflicts with your exclusions`,
      advanced: clean
        ? 'No selected asset matches your exclusions'
        : `Matches: ${matched.map((h) => h.asset.ticker).join(', ')}`,
      help: 'Remove the flagged assets from your selection in Discover Assets.',
    },
  ];
}

/* ---------- Risk contribution ---------- */

/** Share of total risk per holding, percent. Weight times volatility. */
export function riskContributions(holdings: Holding[]): { asset: Asset; share: number }[] {
  const raw = holdings.map((h) => ({ asset: h.asset, value: (h.weight / 100) * h.asset.vol }));
  const total = raw.reduce((s, r) => s + r.value, 0);
  return raw.map((r) => ({ asset: r.asset, share: total > 0 ? (r.value / total) * 100 : 0 }));
}

/* ---------- Scenarios ---------- */

export interface ScenarioContribution {
  asset: Asset;
  weight: number;
  move: number;
  /** Percentage points added to the total impact. */
  contribution: number;
}

export interface ScenarioResult {
  impact: number;
  dollars: number;
  endValue: number;
  contributions: ScenarioContribution[];
}

export function runScenario(
  holdings: Holding[],
  moveFor: (asset: Asset) => number,
): ScenarioResult {
  const contributions = holdings.map((h) => {
    const move = moveFor(h.asset);
    return {
      asset: h.asset,
      weight: h.weight,
      move,
      contribution: (h.weight / 100) * move,
    };
  });
  const impact = contributions.reduce((s, c) => s + c.contribution, 0);
  const endValue = CAPITAL * (1 + impact / 100);
  return {
    impact,
    dollars: CAPITAL * (impact / 100),
    endValue,
    contributions,
  };
}

export function presetScenarioMove(scenario: Scenario) {
  return (asset: Asset) => scenario.moves[asset.ticker] ?? 0;
}

export interface CustomScenarioParams {
  equityMove: number;
  techMove: number;
  bondMove: number;
  rateChange: number;
}

export const CUSTOM_DEFAULTS: CustomScenarioParams = {
  equityMove: 0,
  techMove: 0,
  bondMove: 0,
  rateChange: 0,
};

/**
 * Advanced custom builder. Equity moves apply to stocks and equity ETFs; the tech
 * move adds to technology stocks; the bond move applies to bond ETFs; an interest
 * rate change adds -6 times the rate change to bonds (an assumed duration of 6).
 */
export function customMoveFor(p: CustomScenarioParams) {
  return (asset: Asset): number => {
    if (asset.type === 'bond') return p.bondMove - p.rateChange * 6;
    let move = p.equityMove;
    if (asset.type === 'stock' && asset.sectors.includes('Technology')) move += p.techMove;
    return move;
  };
}

/* ---------- Live mix snapshot (shared by committed mix and what-if preview) ---------- */

export interface MixSnapshot {
  holdings: Holding[];
  stats: PortfolioStats;
  checks: Check[];
  flagged: number;
  series: FanPoint[];
  end: FanPoint;
}

/** Full mix for a set of assets. Returns null when nothing usable is selected. */
export function buildMix(
  profile: Profile,
  selected: Asset[],
  overrides: Record<string, number>,
  horizonYears: number,
): MixSnapshot | null {
  const holdings = buildHoldings(selected, overrides);
  if (!holdings) return null;
  const stats = portfolioStats(holdings);
  const checks = computeChecks(holdings, stats, profile);
  const series = fanSeries(stats, horizonYears);
  return {
    holdings,
    stats,
    checks,
    flagged: checks.filter((c) => !c.passed).length,
    series,
    end: series[series.length - 1],
  };
}

/** Inputs for Ask AlphaForge, derived from a mix snapshot. */
export function buildAskContext(mix: MixSnapshot, profile: Profile, horizonYears: number): AnswerContext {
  const rate = runScenario(mix.holdings, presetScenarioMove(findScenario('year-2022')));
  return {
    holdings: mix.holdings,
    stats: mix.stats,
    horizonYears,
    horizonEndMedian: mix.end.median,
    horizonEndP5: mix.end.p5,
    rateScenarioImpact: rate.impact,
    rateScenarioDollars: rate.dollars,
    badYearLimit: COMFORT_RULES[profile.comfort].badYearLimit,
    topRisk: riskContributions(mix.holdings)
      .sort((a, b) => b.share - a.share)
      .slice(0, 2),
  };
}

/* ---------- Personal conditions: monthly saving and time horizon ---------- */

/** Standard normal cumulative distribution (Abramowitz and Stegun approximation). */
export function normalCdf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const z = Math.abs(x) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * z);
  const poly = ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t;
  return 0.5 * (1 + sign * (1 - poly * Math.exp(-z * z)));
}

/** Model chance (percent) that the starting amount is worth less than it started with after `years`. */
export function chanceBelowStart(stats: PortfolioStats, years: number): number {
  const sd = (stats.vol / 100) * Math.sqrt(years);
  if (!(sd > 0)) return 0;
  return normalCdf((-logDrift(stats.expReturn, stats.vol) * years) / sd) * 100;
}

/**
 * Starting amount plus a fixed amount invested at the start of every month.
 * Each monthly amount grows on the same lognormal model as the starting amount.
 */
export function savingsOutcome(stats: PortfolioStats, monthly: number, years: number) {
  const n = Math.max(1, Math.round(years * 12));
  const s = stats.vol / 100;
  const drift = logDrift(stats.expReturn, stats.vol);
  const contributionsAt = (z: number) => {
    let sum = 0;
    for (let k = 1; k <= n; k++) {
      const t = (n - k + 1) / 12; // months each contribution stays invested
      sum += Math.exp(drift * t + z * s * Math.sqrt(t));
    }
    return monthly * sum;
  };
  const value = (z: number) => percentileValue(z, years, stats) + contributionsAt(z);
  return {
    contributed: monthly * n,
    median: value(0),
    p5: value(Z_P5),
    p95: value(Z_P95),
  };
}

export function findScenario(id: string): Scenario {
  return SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[0];
}

/* ---------- Ask AlphaForge ---------- */

export type PresetQuestion =
  | 'Why this mix?'
  | 'What is my worst case?'
  | 'What if 2022 repeats?'
  | 'What drives the risk?';

export function matchPreset(text: string): PresetQuestion | null {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
  const t = norm(text);
  const found = (
    ['Why this mix?', 'What is my worst case?', 'What if 2022 repeats?', 'What drives the risk?'] as PresetQuestion[]
  ).find((q) => norm(q) === t);
  return found ?? null;
}

export interface AnswerContext {
  holdings: Holding[];
  stats: PortfolioStats;
  horizonYears: number;
  horizonEndMedian: number;
  horizonEndP5: number;
  rateScenarioImpact: number;
  rateScenarioDollars: number;
  badYearLimit: number;
  topRisk: { asset: Asset; share: number }[];
}

export function answerFor(q: PresetQuestion, c: AnswerContext): string {
  const byWeight = [...c.holdings].sort((a, b) => b.weight - a.weight);
  const bondShare = c.holdings
    .filter((h) => h.asset.type === 'bond')
    .reduce((s, h) => s + h.weight, 0);
  switch (q) {
    case 'Why this mix?': {
      const [a, b] = byWeight;
      const top = b
        ? `${a.asset.ticker} (${a.weight.toFixed(1)}%) and ${b.asset.ticker} (${b.weight.toFixed(1)}%)`
        : `${a.asset.ticker} (${a.weight.toFixed(1)}%)`;
      return `The largest holdings are ${top}. Bonds make up ${bondShare.toFixed(1)}% of the mix. Diversification caps apply: no single stock above 20% and no asset above 40%.`;
    }
    case 'What is my worst case?':
      return `In the model's 5th percentile year, the mix could return ${c.stats.p5OneYear.toFixed(1)}%, against your ${c.badYearLimit}% limit. Over ${c.horizonYears} years, the 5th percentile outcome is about $${Math.round(c.horizonEndP5 / 100) * 100} and the median about $${Math.round(c.horizonEndMedian / 100) * 100}, starting from a fictive $100,000.`;
    case 'What if 2022 repeats?':
      return `Replaying what each holding actually did in 2022, this mix would have moved ${c.rateScenarioImpact.toFixed(1)}%, about ${c.rateScenarioDollars < 0 ? '-' : '+'}$${Math.abs(Math.round(c.rateScenarioDollars / 100) * 100).toLocaleString('en-US')} on the fictive capital. That year stocks and bonds fell together. Past moves, not a forecast.`;
    case 'What drives the risk?': {
      const [x, y] = c.topRisk;
      return y
        ? `The two largest risk contributors are ${x.asset.ticker} (${x.share.toFixed(1)}% of total risk) and ${y.asset.ticker} (${y.share.toFixed(1)}%).`
        : `${x.asset.ticker} carries ${x.share.toFixed(1)}% of total risk.`;
    }
  }
}
