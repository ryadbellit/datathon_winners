import { useMemo, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, FileText } from 'lucide-react';
import { ASSETS, DATA_AS_OF, DATA_START, SCENARIOS } from '../../data/assets';
import { ASSET_INTERESTS, COMFORTS, HORIZONS, KNOWLEDGE, OBJECTIVES } from '../../data/options';
import type { Asset, Profile } from '../../data/types';
import { useAppStore } from '../../shared/store';
import { assetClassColors, holdingPalette } from '../../shared/tokens';
import { fmtPct, fmtUSD, fmtWeight } from '../../shared/format';
import { Card, EmptyState } from '../../shared/ui';
import {
  CAPITAL,
  COMFORT_RULES,
  HORIZON_CHOICES,
  HORIZON_YEARS,
  buildMix,
  chanceBelowStart,
  discoverAssets,
  percentileValue,
  presetScenarioMove,
  runScenario,
  type Holding,
  type MixSnapshot,
} from '../../lib/engine';

const REPORT_DATE = '14 Nov 2026';
const Z_P5 = -1.645;

/** Rough-year return (5th percentile, one year) if the assumed correlation were `rho`. */
function roughYearAt(holdings: Holding[], rho: number, expReturn: number): number {
  const wv = holdings.map((h) => (h.weight / 100) * h.asset.vol);
  const sum = wv.reduce((a, b) => a + b, 0);
  const sumSq = wv.reduce((a, b) => a + b * b, 0);
  const vol = Math.sqrt(Math.max(0, sumSq + rho * (sum * sum - sumSq)));
  const drift = expReturn / 100 - 0.5 * (vol / 100) ** 2;
  return (Math.exp(drift + Z_P5 * (vol / 100)) - 1) * 100;
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  const v = Math.min(100, Math.max(0, value));
  return (
    <div className="grid grid-cols-[110px_1fr_56px] items-center gap-3 text-xs">
      <span className="text-ink-2">{label}</span>
      <div className="h-2 overflow-hidden rounded-full bg-line" aria-hidden="true">
        <div className="h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="text-right text-ink">{fmtWeight(value)}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-raised p-3">
      <p className="text-[11px] uppercase tracking-wide text-ink-3">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-ink">{value}</p>
    </div>
  );
}

export function ReportPage() {
  const profile = useAppStore((s) => s.profile) as Profile;
  const selectedIds = useAppStore((s) => s.selectedIds);
  const overrides = useAppStore((s) => s.weightOverrides);
  const horizonOverride = useAppStore((s) => s.horizonOverride);

  const horizonYears = horizonOverride ?? HORIZON_YEARS[profile.horizon];
  const mix: MixSnapshot | null = useMemo(
    () => buildMix(profile, ASSETS.filter((a) => selectedIds.includes(a.ticker)), overrides, horizonYears),
    [profile, selectedIds, overrides, horizonYears],
  );
  const discovered = useMemo(() => discoverAssets(profile), [profile]);

  if (!mix) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <h1 className="mb-3 text-xl font-semibold text-ink">Analysis report</h1>
        <EmptyState title="No analysis to report yet" body="Select assets in Discover and your report will be built from that mix." />
      </div>
    );
  }

  const { holdings, stats, checks, end } = mix;
  const flagged = checks.filter((c) => !c.passed);
  const rules = COMFORT_RULES[profile.comfort];
  const edited = Object.keys(overrides).length > 0;

  // Class split and region split, from the mix.
  const classShare = (type: Asset['type']) => holdings.filter((h) => h.asset.type === type).reduce((s, h) => s + h.weight, 0);
  const regionMap = new Map<string, number>();
  holdings.forEach((h) => regionMap.set(h.asset.region, (regionMap.get(h.asset.region) ?? 0) + h.weight));
  const regions = Array.from(regionMap, ([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
  const techShare = holdings.filter((h) => h.asset.sectors.includes('Technology')).reduce((s, h) => s + h.weight, 0);
  const limitations = Array.from(new Set(holdings.map((h) => h.asset.limitation)));
  const discoveredTypes = {
    stock: discovered.filter((a) => a.type === 'stock').length,
    etf: discovered.filter((a) => a.type === 'etf').length,
    bond: discovered.filter((a) => a.type === 'bond').length,
  };
  const discoveredRegions = new Set(discovered.map((a) => a.region)).size;
  const roughYearLimit = rules.badYearLimit;

  const sections: { id: string; title: string; body: ReactNode }[] = [
    {
      id: 'summary',
      title: 'Summary',
      body: (
        <div className="flex flex-col gap-4">
          <p className="flex items-start gap-2 text-base text-ink">
            {flagged.length === 0 ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-caution" aria-hidden="true" />
            )}
            <span>
              {flagged.length === 0
                ? 'The mix fits your profile on all four checks.'
                : `${flagged.length} ${flagged.length === 1 ? 'check' : 'checks'} flagged: ${flagged.map((c) => c.name).join(', ')}.`}
            </span>
          </p>
          <p className="text-sm text-ink-2">
            This mix holds {holdings.length} assets. Its historical annualised return is {fmtPct(stats.expReturn)} a year, with volatility of{' '}
            {fmtPct(stats.vol)}. In a rough year, the model's 5th-percentile return is {fmtPct(stats.p5OneYear)}, against your{' '}
            {fmtPct(roughYearLimit, { dp: 0 })} limit.
          </p>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Total invested" value={fmtUSD(CAPITAL)} />
            <Stat label="Holdings" value={String(holdings.length)} />
            <Stat label="Expected return" value={fmtPct(stats.expReturn)} />
            <Stat label="Volatility" value={fmtPct(stats.vol)} />
          </div>
          <p className="text-xs text-ink-3">Simulation on historical data (PolyFinances starter dataset). Not financial advice.</p>
        </div>
      ),
    },
    {
      id: 'profile',
      title: 'Profile and mix',
      body: (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
          <dl className="grid gap-2 text-sm">
            <Row label="Objective" value={OBJECTIVES.find((o) => o.value === profile.objective)?.label ?? ''} />
            <Row label="Horizon" value={HORIZONS.find((h) => h.value === profile.horizon)?.label ?? ''} />
            <Row label="Risk comfort" value={COMFORTS.find((c) => c.value === profile.comfort)?.label ?? ''} />
            <Row label="Asset types" value={profile.assetTypes.map((a) => ASSET_INTERESTS.find((o) => o.value === a)?.label ?? '').join(', ')} />
            <Row label="Knowledge level" value={KNOWLEDGE.find((k) => k.value === profile.knowledge)?.label ?? ''} />
            <Row label="Exclusions" value={profile.exclusions.trim() || 'None'} />
          </dl>
          <div>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Holdings and weights</caption>
              <thead className="text-xs text-ink-3">
                <tr>
                  <th scope="col" className="pb-1 font-medium">Ticker</th>
                  <th scope="col" className="pb-1 font-medium">Name</th>
                  <th scope="col" className="pb-1 font-medium">Type</th>
                  <th scope="col" className="pb-1 text-right font-medium">Weight</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <tr key={h.asset.ticker} className="border-t border-line">
                    <td className="py-1.5 font-semibold text-ink">{h.asset.ticker}</td>
                    <td className="py-1.5 text-ink-2">{h.asset.name}</td>
                    <td className="py-1.5 text-ink-2">{h.asset.typeLabel}</td>
                    <td className="py-1.5 text-right text-ink">{fmtWeight(h.weight)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">
              {edited ? 'Weights were edited by hand from the example mix. ' : 'Weights are the example mix. '}
              Total invested: {fmtUSD(CAPITAL)}.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'discovery',
      title: 'Discovery overview',
      body: (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-2">
            {discovered.length} of {ASSETS.length} example assets passed your profile rules. They appeared because they fit your answers, not because any one is predicted to perform best.
          </p>
          <div className="flex flex-wrap gap-2">
            {[
              `${discoveredTypes.stock} individual stocks`,
              `${discoveredTypes.etf} ETFs`,
              `${discoveredTypes.bond} bond ETFs`,
              `${discoveredRegions} regions`,
            ].map((t) => (
              <span key={t} className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink">
                {t}
              </span>
            ))}
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Assets in your mix and why they appeared</p>
            <ul className="grid gap-2 md:grid-cols-2">
              {holdings.map((h) => (
                <li key={h.asset.ticker} className="rounded-lg border border-line p-2.5 text-xs">
                  <p className="font-semibold text-ink">
                    {h.asset.ticker} <span className="font-normal text-ink-2">· {h.asset.role}</span>
                  </p>
                  <p className="mt-0.5 text-ink-2">{h.asset.why}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'diversification',
      title: 'Diversification',
      body: (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-3">Asset classes</p>
            <Bar label="Stocks" value={classShare('stock')} color={assetClassColors.Stocks} />
            <Bar label="ETFs" value={classShare('etf')} color={assetClassColors.ETFs} />
            <Bar label="Bonds" value={classShare('bond')} color={assetClassColors.Bonds} />
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-3">Geographic exposure</p>
            {regions.map((r, i) => (
              <Bar key={r.name} label={r.name} value={r.value} color={holdingPalette[i % holdingPalette.length]} />
            ))}
          </div>
          <div className="lg:col-span-2 flex items-start gap-2 rounded-xl border border-caution/40 bg-caution/10 p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-caution" aria-hidden="true" />
            <p className="text-ink-2">
              <span className="font-semibold text-ink">Technology concentration: {fmtWeight(techShare)} of the mix</span> sits in holdings
              that list technology as a sector. Broad funds also hold technology companies, so the true share may be higher. A sector decline could affect several holdings together.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'outcomes',
      title: 'Scenarios and horizon',
      body: (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Historical replays</p>
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Scenario impact on the mix</caption>
              <thead className="text-ink-3">
                <tr>
                  <th scope="col" className="pb-1 font-medium">Scenario</th>
                  <th scope="col" className="pb-1 text-right font-medium">Impact</th>
                  <th scope="col" className="pb-1 text-right font-medium">$100,000 becomes</th>
                </tr>
              </thead>
              <tbody>
                {SCENARIOS.map((s) => {
                  const r = runScenario(holdings, presetScenarioMove(s));
                  return (
                    <tr key={s.id} className="border-t border-line">
                      <td className="py-1.5 text-ink">{s.name}</td>
                      <td className={`py-1.5 text-right ${r.impact < roughYearLimit ? 'text-caution' : 'text-ink'}`}>{fmtPct(r.impact, { sign: true })}</td>
                      <td className="py-1.5 text-right text-ink">{fmtUSD(r.endValue)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Outcome by time horizon (model)</p>
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Model outcomes by horizon</caption>
              <thead className="text-ink-3">
                <tr>
                  <th scope="col" className="pb-1 font-medium">Years</th>
                  <th scope="col" className="pb-1 text-right font-medium">Typical</th>
                  <th scope="col" className="pb-1 text-right font-medium">Rough</th>
                  <th scope="col" className="pb-1 text-right font-medium">Chance below start</th>
                </tr>
              </thead>
              <tbody>
                {HORIZON_CHOICES.map((y) => (
                  <tr key={y} className="border-t border-line">
                    <td className="py-1.5 text-ink">{y}</td>
                    <td className="py-1.5 text-right text-ink">{fmtUSD(percentileValue(0, y, stats))}</td>
                    <td className="py-1.5 text-right text-ink">{fmtUSD(percentileValue(Z_P5, y, stats))}</td>
                    <td className="py-1.5 text-right text-ink">{fmtPct(chanceBelowStart(stats, y), { dp: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">
              Your selected horizon is {horizonYears} years: typical {fmtUSD(end.median)}, rough {fmtUSD(end.p5)}. Scenarios replay past windows; horizon figures are model estimates.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'risks',
      title: 'Main risks',
      body: (
        <div className="grid gap-5 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Limitations of the assets in your mix</p>
            <ul className="flex flex-col gap-2 text-sm text-ink-2">
              {limitations.map((l) => (
                <li key={l} className="flex gap-2">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-caution" aria-hidden="true" />
                  {l}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Flagged checks</p>
            {flagged.length === 0 ? (
              <p className="text-sm text-ink-2">No checks are flagged.</p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm text-ink-2">
                {flagged.map((c) => (
                  <li key={c.id}>
                    <span className="font-semibold text-ink">{c.name}: </span>
                    {c.guided}. {c.help}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ),
    },
    {
      id: 'reliability',
      title: 'How reliable is this analysis?',
      body: (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-line bg-raised p-3 text-sm text-ink-2">
            <p className="font-semibold text-ink">The figures come from the PolyFinances starter dataset.</p>
            <p className="mt-1">Adjusted closes from Yahoo Finance, CAD converted with the Bank of Canada rate, all in USD. Statistics describe the past window; they are not forecasts.</p>
          </div>
          <dl className="grid gap-2 text-sm md:grid-cols-2">
            <Row label="Data window" value={`Starter dataset, ${DATA_START} to ${DATA_AS_OF}`} />
            <Row label="Completeness" value={`All ${holdings.length} selected assets have full historical figures`} />
          </dl>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Sensitivity to the correlation assumption</p>
            <p className="mb-2 text-xs text-ink-2">
              The model assumes one correlation between every pair of holdings. If that assumption changes, the rough-year figure changes too.
            </p>
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Rough-year return at different correlations</caption>
              <thead className="text-ink-3">
                <tr>
                  <th scope="col" className="pb-1 font-medium">Assumed correlation</th>
                  <th scope="col" className="pb-1 text-right font-medium">Rough-year return</th>
                  <th scope="col" className="pb-1 text-right font-medium">Against your limit</th>
                </tr>
              </thead>
              <tbody>
                {[0.2, 0.5, 0.8].map((rho) => {
                  const r = roughYearAt(holdings, rho, stats.expReturn);
                  return (
                    <tr key={rho} className="border-t border-line">
                      <td className="py-1.5 text-ink">{rho.toFixed(1)}</td>
                      <td className="py-1.5 text-right text-ink">{fmtPct(r)}</td>
                      <td className={`py-1.5 text-right ${r < roughYearLimit ? 'text-caution' : 'text-ink-2'}`}>
                        {r < roughYearLimit ? 'Worse than limit' : 'Within limit'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ),
    },
    {
      id: 'questions',
      title: 'Questions for your advisor',
      body: (
        <div className="flex flex-col gap-3 text-sm text-ink-2">
          <ul className="list-disc space-y-1.5 pl-5">
            {flagged.length > 0 && <li>Which of these flagged points matter most for my situation: {flagged.map((c) => c.name.toLowerCase()).join(', ')}?</li>}
            {techShare > 20 && <li>Is a technology share of about {Math.round(techShare)}% of my mix appropriate for me?</li>}
            <li>Does my rough-year limit of {fmtPct(roughYearLimit, { dp: 0 })} reflect how I would really react?</li>
            <li>What are the real costs, fees and taxes on these kinds of investments in my country?</li>
            <li>How does this compare with the holdings I already have?</li>
            <li>Should I keep an emergency fund before investing?</li>
          </ul>
          <div className="mt-auto rounded-xl border border-line bg-raised p-3 text-xs text-ink-3">
            This report is a simulation built on historical data from the starter dataset. It is not financial advice and not a suitability assessment. A licensed financial advisor can use real data and your full situation.
          </div>
        </div>
      ),
    },
  ];

  return (
    <div id="analysis-report" className="flex min-h-0 flex-1 flex-col">
      <header className="mb-3 flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-3">Analysis report</p>
          <h1 className="text-xl font-semibold text-ink">Your investment analysis</h1>
          <p className="text-xs text-ink-2">Prepared {REPORT_DATE} · historical data · simulation only</p>
        </div>
        <button type="button" onClick={() => window.print()} className="btn-outline-brand no-print px-3 py-1.5 text-sm">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Export as PDF
        </button>
      </header>

      <Card dense className="report-scroll flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto pr-2">
          {sections.map((s, i) => (
            <section key={s.id} aria-labelledby={`sec-${s.id}`} className="report-section mb-8 last:mb-0">
              <h2 id={`sec-${s.id}`} className="mb-3 border-b border-line pb-2 text-base font-semibold text-ink">
                {String(i + 1).padStart(2, '0')} · {s.title}
              </h2>
              {s.body}
            </section>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col rounded-lg border border-line p-2">
      <dt className="text-[11px] uppercase tracking-wide text-ink-3">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}
