import { SCENARIOS } from '../data/assets';
import type { Profile } from '../data/types';
import { fmtPct, fmtUSD } from '../shared/format';
import {
  COMFORT_RULES,
  HORIZON_CHOICES,
  answerFor,
  buildAskContext,
  chanceBelowStart,
  matchPreset,
  percentileValue,
  presetScenarioMove,
  runScenario,
  savingsOutcome,
  type MixSnapshot,
  type PresetQuestion,
} from './engine';

/*
 * Rule-based answers for the scenario chat. Every number comes from the same model
 * used on the other screens. Nothing is invented, and nothing is predicted.
 */

export interface ChatContext {
  mix: MixSnapshot;
  profile: Profile;
  horizonYears: number;
}

const Z_P5 = -1.645;
const money = (n: number) => fmtUSD(n);

const SCENARIO_KEYWORDS: [RegExp, string][] = [
  [/tech/, 'tech-downturn'],
  [/rate|interest|2022/, 'rate-increase'],
  [/slow|recession|earnings/, 'slowdown'],
  [/rall|strong|bull|boom|rise|rising/, 'strong-global'],
  [/crash|decline|broad|market|fall/, 'broad-decline'],
];

const HELP =
  'I answer questions about this portfolio\'s numbers. Try: "What if I save $300 a month for 10 years?", "What if I invest for 3 years instead?", "What happens in a technology downturn?" or "What is my worst case?". For decisions beyond this simulation, a licensed financial advisor can help.';

/** Years mentioned in the question, e.g. "for 10 years". */
function yearsIn(text: string): number | null {
  const m = text.match(/(\d+)\s*(?:years?|yrs?)\b/i);
  return m ? Number(m[1]) : null;
}

/** The first amount mentioned, ignoring any "N years" part. "$300" and "2k" both work. */
function amountIn(text: string): number | null {
  const stripped = text.replace(/(\d+)\s*(?:years?|yrs?)\b/gi, ' ');
  const m = stripped.match(/(\d[\d,]*(?:\.\d+)?)\s*(k)?/i);
  if (!m) return null;
  const v = Number(m[1].replace(/,/g, '')) * (m[2] ? 1000 : 1);
  return Number.isFinite(v) && v > 0 ? v : null;
}

export function answerChat(text: string, ctx: ChatContext): string {
  const { mix, profile, horizonYears } = ctx;
  const { stats } = mix;
  const t = text.trim().toLowerCase();
  const askCtx = buildAskContext(mix, profile, horizonYears);
  const limit = COMFORT_RULES[profile.comfort].badYearLimit;

  // 1. Exact preset questions.
  const preset = matchPreset(text);
  if (preset) return answerFor(preset as PresetQuestion, askCtx);

  // 2. Monthly saving.
  if (/month|saving|save|contribut/.test(t)) {
    const monthly = amountIn(t);
    const years = yearsIn(t) ?? horizonYears;
    if (monthly === null) return 'Tell me the monthly amount, for example: "What if I save $300 a month for 10 years?"';
    const out = savingsOutcome(stats, monthly, years);
    const baseline = percentileValue(0, years, stats);
    return `Saving ${money(monthly)} a month for ${years} years adds ${money(out.contributed)} on top of the fictive $100,000 starting amount. The typical outcome is about ${money(out.median)}, a rough case about ${money(out.p5)}, and a strong case about ${money(out.p95)}. Without saving, the typical outcome is about ${money(baseline)}. These are model estimates, not forecasts.`;
  }

  // 3. Market scenarios named in the question.
  const scenarioId = SCENARIO_KEYWORDS.find(([re]) => re.test(t))?.[1];
  if (scenarioId) {
    const s = SCENARIOS.find((x) => x.id === scenarioId) ?? SCENARIOS[0];
    const r = runScenario(mix.holdings, presetScenarioMove(s));
    const relation = r.impact < limit ? 'worse than' : 'within';
    return `In "${s.name}" (${s.description.replace(/\.$/, '')}), the mix would move about ${fmtPct(r.impact, { sign: true })}, so $100,000 could become about ${money(r.endValue)}. ${s.explanation} That is ${relation} your ${fmtPct(limit, { dp: 0 })} rough-year limit. These are hypothetical assumptions, not predictions.`;
  }

  // 4. Time horizon.
  if (/year|yr|horizon|how long|longer|shorter|later|sooner/.test(t)) {
    const row = (years: number) => ({
      years,
      median: percentileValue(0, years, stats),
      p5: percentileValue(Z_P5, years, stats),
      below: chanceBelowStart(stats, years),
    });
    const y = yearsIn(t);
    if (y !== null) {
      const r = row(y);
      return `Over ${y} years, the typical outcome is about ${money(r.median)} and a rough case about ${money(r.p5)}. The model gives roughly a ${fmtPct(r.below, { dp: 0 })} chance of ending below the starting $100,000. A shorter horizon leaves less time to recover after a drop.`;
    }
    const rows = HORIZON_CHOICES.map(row).map(
      (r) => `${r.years} yr: typical ${money(r.median)}, ${fmtPct(r.below, { dp: 0 })} chance below start`,
    );
    return `By horizon: ${rows.join('; ')}. Longer horizons usually leave more time to recover, but results still vary.`;
  }

  // 5. Presets phrased loosely.
  if (/worst|bad|rough|lose|loss|drop/.test(t)) return answerFor('What is my worst case?', askCtx);
  if (/risk|drive/.test(t)) return answerFor('What drives the risk?', askCtx);
  if (/why|mix/.test(t)) return answerFor('Why this mix?', askCtx);

  return HELP;
}
