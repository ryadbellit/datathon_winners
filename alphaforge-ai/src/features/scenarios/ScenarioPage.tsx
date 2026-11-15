import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowDown, ArrowLeft, CheckCircle2, FlaskConical } from 'lucide-react';
import { ASSETS, SCENARIOS } from '../../data/assets';
import type { Profile } from '../../data/types';
import { useAppStore } from '../../shared/store';
import { colors } from '../../shared/tokens';
import { fmtPct, fmtUSD, fmtWeight } from '../../shared/format';
import { Card, EmptyState, ProvenanceTag } from '../../shared/ui';
import { AdvisorChat } from './AdvisorChat';
import type { ChatContext } from '../../lib/chat';
import {
  CAPITAL,
  COMFORT_RULES,
  CUSTOM_DEFAULTS,
  HORIZON_YEARS,
  buildHoldings,
  buildMix,
  customMoveFor,
  presetScenarioMove,
  runScenario,
  type CustomScenarioParams,
  type Holding,
} from '../../lib/engine';

type Tab = 'contrib' | 'custom';

export function ScenarioPage() {
  const profile = useAppStore((s) => s.profile) as Profile;
  const selectedIds = useAppStore((s) => s.selectedIds);
  const overrides = useAppStore((s) => s.weightOverrides);
  const viewMode = useAppStore((s) => s.viewMode);
  const scenarioId = useAppStore((s) => s.scenarioId);
  const horizonOverride = useAppStore((s) => s.horizonOverride);
  const setScenario = useAppStore((s) => s.setScenario);
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('contrib');

  const advanced = viewMode === 'advanced';
  const activeTab: Tab = tab === 'custom' && !advanced ? 'contrib' : tab;

  const holdings = useMemo(
    () => buildHoldings(ASSETS.filter((a) => selectedIds.includes(a.ticker)), overrides),
    [selectedIds, overrides],
  );

  const chatCtx = useMemo<ChatContext | null>(() => {
    const horizonYears = horizonOverride ?? HORIZON_YEARS[profile.horizon];
    const mix = buildMix(profile, ASSETS.filter((a) => selectedIds.includes(a.ticker)), overrides, horizonYears);
    return mix ? { mix, profile, horizonYears } : null;
  }, [profile, selectedIds, overrides, horizonOverride]);

  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="mb-2 flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-3">Scenario analysis</p>
          <h1 className="text-xl font-semibold text-ink">Explore "what if" market conditions</h1>
          <p className="text-xs text-ink-2">Scenarios are hypothetical learning tools, not forecasts, probabilities, or guarantees.</p>
        </div>
        <button type="button" className="btn-secondary px-3 py-1.5 text-sm" onClick={() => navigate('/')}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Adjust portfolio
        </button>
      </header>

      {!holdings ? (
        <EmptyState
          title="Select assets in Discover to run scenarios"
          body="Scenarios use the assets you have selected and their weights. Pick at least one asset to see the impact."
          actionLabel="Select assets in Discover"
          onAction={() => navigate('/')}
        />
      ) : (
        <Card dense className="flex min-h-0 flex-1 flex-col gap-4">
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[230px_1fr] lg:grid-rows-[minmax(0,1fr)]">
          {/* Left: scenario list. Always visible. */}
          <div className="flex min-h-0 flex-col">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-3">Choose a scenario</p>
            <ol className="flex flex-col gap-1.5">
              {SCENARIOS.map((s, i) => {
                const on = s.id === scenario.id;
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      aria-pressed={on}
                      onClick={() => setScenario(s.id)}
                      className={`focus-ring flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition duration-200 hover:bg-raised ${
                        on ? 'border-brand bg-raised' : 'border-line'
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                          on ? 'bg-brand text-white' : 'border border-line-strong text-ink-2'
                        }`}
                        aria-hidden="true"
                      >
                        {i + 1}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-xs font-medium text-ink">{s.name}</span>
                        <span className="block truncate text-[11px] text-ink-2">{s.description}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>

          {/* Right: selected scenario, impact and a tabbed detail area. */}
          <div className="flex min-h-0 flex-col gap-3">
            <ScenarioSummary
              holdings={holdings}
              scenarioName={scenario.name}
              scenarioExplanation={scenario.explanation}
              moveFor={presetScenarioMove(scenario)}
              limit={COMFORT_RULES[profile.comfort].badYearLimit}
              bondMove={scenario.moves.AGG ?? 0}
              bondWeight={holdings.filter((h) => h.asset.type === 'bond').reduce((s, h) => s + h.weight, 0)}
            />

            <div role="tablist" aria-label="Scenario details" className="flex shrink-0 gap-1 border-b border-line">
              {(
                [
                  ['contrib', 'Contributions'],
                  ...(advanced ? ([['custom', 'Custom builder']] as [Tab, string][]) : []),
                ] as [Tab, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  role="tab"
                  type="button"
                  aria-selected={activeTab === id}
                  onClick={() => setTab(id)}
                  className={`focus-ring -mb-px border-b-2 px-3 py-1.5 text-xs transition ${
                    activeTab === id ? 'border-brand text-ink' : 'border-transparent text-ink-2 hover:text-ink'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div role="tabpanel" className="min-h-0 flex-1 overflow-hidden">
              {activeTab === 'contrib' && (
                <Contributions holdings={holdings} moveFor={presetScenarioMove(scenario)} advanced={advanced} />
              )}
              {activeTab === 'custom' && advanced && <CustomBuilder holdings={holdings} limit={COMFORT_RULES[profile.comfort].badYearLimit} />}
            </div>

          </div>
        </div>

        {/* Full-width bottom bar, so the input is centred on the whole card. */}
        <AdvisorChat ctx={chatCtx} />
        </Card>
      )}
    </div>
  );
}

/* ---------- Impact summary ---------- */

function ScenarioSummary({
  holdings,
  scenarioName,
  scenarioExplanation,
  moveFor,
  limit,
  bondMove,
  bondWeight,
}: {
  holdings: Holding[];
  scenarioName: string;
  scenarioExplanation: string;
  moveFor: (asset: Holding['asset']) => number;
  limit: number;
  bondMove: number;
  bondWeight: number;
}) {
  const result = runScenario(holdings, moveFor);
  const negative = result.impact < 0;
  const worse = result.impact < limit;
  const top = [...result.contributions].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0];
  const bondSentence =
    bondWeight > 0
      ? `Bonds (${fmtWeight(bondWeight)} of the mix) are assumed to move ${fmtPct(bondMove, { dp: 0, sign: true })}.`
      : 'The mix has no bonds, so there is no cushion from them.';

  return (
    <div className="flex shrink-0 flex-col gap-2">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-raised">
          <FlaskConical className="h-4 w-4 text-model" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">Hypothetical scenario</p>
          <p className="truncate text-base font-semibold text-ink">{scenarioName}</p>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border border-line bg-raised p-3 sm:grid-cols-[auto_1fr] sm:items-center">
        <div>
          <p className={`flex items-center gap-1.5 text-[32px] font-semibold leading-none ${negative ? 'text-caution' : 'text-ink'}`}>
            {negative && <ArrowDown className="h-5 w-5" aria-hidden="true" />}
            {fmtPct(result.impact, { sign: true })}
          </p>
          <p className="mt-1 text-xs text-ink-2">
            {fmtUSD(CAPITAL)} could become about {fmtUSD(result.endValue)}. The actual result could be better or worse.
          </p>
          <div className="mt-1.5">
            <ProvenanceTag kind="hypothetical" />
          </div>
        </div>
        <div className="flex flex-col gap-1 text-xs">
          <p className={`flex items-start gap-1.5 ${worse ? 'text-caution' : 'text-ink-2'}`}>
            {worse ? (
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
            )}
            <span>
              <span className="font-medium">{worse ? 'Flagged. ' : 'Pass. '}</span>
              {worse
                ? `Worse than the ${fmtPct(limit, { dp: 0 })} rough-year limit for your risk comfort.`
                : `Within the ${fmtPct(limit, { dp: 0 })} rough-year limit for your risk comfort.`}
            </span>
          </p>
          <p className="text-ink-2">{scenarioExplanation}</p>
          <p className="text-ink-2">
            {top ? `${top.asset.ticker} is the largest driver (${fmtPct(top.contribution, { sign: true })} to the mix).` : ''} {bondSentence}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ---------- Contributions ---------- */

function Contributions({
  holdings,
  moveFor,
  advanced,
}: {
  holdings: Holding[];
  moveFor: (asset: Holding['asset']) => number;
  advanced: boolean;
}) {
  const result = runScenario(holdings, moveFor);
  const sorted = [...result.contributions].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const shown = advanced ? sorted : sorted.slice(0, 3);
  const maxAbs = Math.max(...result.contributions.map((c) => Math.abs(c.contribution)), 0.0001);

  return (
    <div className="flex flex-col gap-1.5 pt-1">
      <p className="text-[11px] text-ink-3">{advanced ? 'Every holding' : 'Biggest drivers'}</p>
      {shown.map((c) => {
        const width = (Math.abs(c.contribution) / maxAbs) * 100;
        const neg = c.contribution < 0;
        return (
          <div key={c.asset.ticker} className="grid grid-cols-[52px_1fr_auto] items-center gap-2 text-xs">
            <span className="font-semibold text-ink">{c.asset.ticker}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
              <div className="h-full rounded-full" style={{ width: `${width}%`, background: neg ? colors.caution : colors.dataSlate }} />
            </div>
            <span className={neg ? 'text-caution' : 'text-ink-2'}>
              {advanced
                ? `${fmtWeight(c.weight)} × ${fmtPct(c.move, { sign: true })} = ${fmtPct(c.contribution, { sign: true })}`
                : fmtPct(c.contribution, { sign: true })}
            </span>
          </div>
        );
      })}
      <div className="mt-1">
        <ProvenanceTag kind="hypothetical" />
      </div>
    </div>
  );
}

/* ---------- Advanced: custom scenario builder ---------- */

const CUSTOM_CONTROLS: {
  key: keyof CustomScenarioParams;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}[] = [
  { key: 'equityMove', label: 'Equity move', min: -50, max: 30, step: 1, unit: '%' },
  { key: 'techMove', label: 'Extra tech move', min: -30, max: 30, step: 1, unit: '%' },
  { key: 'bondMove', label: 'Bond move', min: -15, max: 10, step: 1, unit: '%' },
  { key: 'rateChange', label: 'Rate change', min: -2, max: 3, step: 0.25, unit: ' pts' },
];

function CustomBuilder({ holdings, limit }: { holdings: Holding[]; limit: number }) {
  const [params, setParams] = useState<CustomScenarioParams>(CUSTOM_DEFAULTS);
  const result = useMemo(() => runScenario(holdings, customMoveFor(params)), [holdings, params]);
  const worse = result.impact < limit;

  return (
    <div className="flex flex-col gap-2 pt-1">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
        <p className={result.impact < 0 ? 'text-caution' : 'text-ink'}>
          <span className="text-base font-semibold">{fmtPct(result.impact, { sign: true })}</span>{' '}
          <span className="text-ink-2">· {fmtUSD(CAPITAL)} could become about {fmtUSD(result.endValue)}</span>
        </p>
        <p className={worse ? 'text-caution' : 'text-ink-2'}>
          {worse ? 'Flagged' : 'Pass'} against the {fmtPct(limit, { dp: 0 })} limit
        </p>
      </div>
      {CUSTOM_CONTROLS.map((c) => {
        const value = params[c.key];
        const id = `custom-${c.key}`;
        return (
          <div key={c.key} className="grid grid-cols-[110px_1fr_auto] items-center gap-2 text-xs">
            <label htmlFor={id} className="text-ink">
              {c.label}
            </label>
            <input
              id={id}
              type="range"
              min={c.min}
              max={c.max}
              step={c.step}
              value={value}
              onChange={(e) => setParams((p) => ({ ...p, [c.key]: Number(e.target.value) }))}
            />
            <span className="flex items-center gap-1.5">
              <span className="w-16 text-right text-ink">
                {value > 0 ? '+' : ''}
                {value.toFixed(c.step < 1 ? 2 : 0)}
                {c.unit}
              </span>
              <button
                type="button"
                className="focus-ring rounded px-1 text-[11px] text-brand-hover hover:underline"
                onClick={() => setParams((p) => ({ ...p, [c.key]: CUSTOM_DEFAULTS[c.key] }))}
              >
                Reset
                <span className="sr-only"> {c.label}</span>
              </button>
            </span>
          </div>
        );
      })}
    </div>
  );
}
