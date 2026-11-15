import { ASSETS } from '../data/assets';
import type { Profile } from '../data/types';

export type Assessment = 'supported' | 'partially_supported' | 'insufficient_evidence';

/** Subset of the backend TeamReport used by the UI (the full report also has evidence, debate and governance details). */
export interface AnalysisResult {
  answer: string;
  assessment: Assessment;
  sources: string[];
  debate_rounds: number;
  failures: string[];
  estimated_cost_usd: number | null;
}

/** Current selection as portfolio lines, weights normalised to 100 % (the backend never invents weights). */
function toHoldings(selectedIds: string[], overrides: Record<string, number>) {
  const picked = ASSETS.filter((a) => selectedIds.includes(a.ticker));
  const raw = picked.map((a) => Math.max(0, overrides[a.ticker] ?? a.baseWeight));
  const total = raw.reduce((sum, w) => sum + w, 0);
  return picked.map((a, i) => ({
    ticker: a.ticker,
    name: a.name,
    weight_pct: total > 0 ? (raw[i] / total) * 100 : 0,
    sector: a.sectors[0] ?? null,
  }));
}

export async function analyze(
  question: string,
  profile: Profile,
  selectedIds: string[],
  overrides: Record<string, number>,
  horizonYears: number | null,
): Promise<AnalysisResult> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 120_000); // the 5-agent workflow takes a while
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        profile: { objective: profile.objective, horizon: profile.horizon, comfort: profile.comfort },
        holdings: toHoldings(selectedIds, overrides),
        horizon_years: horizonYears,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error ?? `HTTP ${response.status}`);
    }
    return (await response.json()) as AnalysisResult;
  } finally {
    window.clearTimeout(timer);
  }
}
