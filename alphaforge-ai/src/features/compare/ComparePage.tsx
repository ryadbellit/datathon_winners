import { useState } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { ASSETS } from '../../data/assets';
import type { Asset, Profile } from '../../data/types';
import { useAppStore } from '../../shared/store';
import { holdingPalette } from '../../shared/tokens';
import { fmtPct } from '../../shared/format';
import { Card, EmptyState, HelpTip } from '../../shared/ui';
import { COMFORT_RULES, matchesExclusions } from '../../lib/engine';

/** Most assets that can be shown side by side. */
const MAX_COMPARED = 4;

function riskLevel(vol: number): string {
  if (vol < 10) return 'Low';
  if (vol < 25) return 'Medium';
  return 'High';
}

/** Plain-language view of how an asset spreads risk across the portfolio. */
function diversificationNote(a: Asset): string {
  if (a.type === 'bond') return 'Tends to move less with stock markets.';
  if (a.sectors.includes('Diversified')) return 'Spreads exposure across many companies.';
  return 'Concentrated in a few companies, so it adds less spread.';
}

/** The first reason an asset clashes with the profile, or null when it fits. */
function fitIssue(a: Asset, p: Profile): string | null {
  const rules = COMFORT_RULES[p.comfort];
  if (a.vol > rules.riskFitCeiling) {
    return `${a.ticker}'s historical volatility (${fmtPct(a.vol)}) is above the usual range for your risk comfort (up to ${rules.riskFitCeiling}%).`;
  }
  if (a.type === 'stock' && a.vol > 30 && (p.comfort === 'stability' || p.horizon === 'short')) {
    return `${a.ticker} is a higher-movement stock, usually better suited to a longer horizon and higher risk comfort.`;
  }
  if (matchesExclusions(a, p.exclusions)) return `${a.ticker} matches one of your exclusions.`;
  return null;
}

interface Row {
  label: string;
  help?: string;
  tone?: 'caution';
  value: (a: Asset) => string;
}

export function ComparePage() {
  const profile = useAppStore((s) => s.profile) as Profile;
  const selectedIds = useAppStore((s) => s.selectedIds);
  const advanced = useAppStore((s) => s.viewMode) === 'advanced';

  const [picked, setPicked] = useState<string[]>(() => selectedIds.slice(0, 3));
  const assets = picked
    .map((t) => ASSETS.find((a) => a.ticker === t))
    .filter((a): a is Asset => Boolean(a));

  const colorOf = (ticker: string) => holdingPalette[ASSETS.findIndex((a) => a.ticker === ticker) % holdingPalette.length];

  const toggle = (ticker: string) =>
    setPicked((prev) => (prev.includes(ticker) ? prev.filter((t) => t !== ticker) : [...prev, ticker].slice(-MAX_COMPARED)));

  const rows: Row[] = [
    { label: 'What it offers', value: (a) => a.role },
    {
      label: 'Risk level',
      help: 'Based on historical volatility over the dataset window: Low below 10%, Medium below 25%, High above that.',
      value: (a) => riskLevel(a.vol),
    },
    { label: 'Main benefit', value: (a) => a.why },
    { label: 'Main limitation', tone: 'caution', value: (a) => a.limitation },
    { label: 'Potential diversification', value: (a) => diversificationNote(a) },
    ...(advanced
      ? [
          { label: 'Volatility', value: (a: Asset) => fmtPct(a.vol) },
          { label: 'Maximum drawdown', value: (a: Asset) => fmtPct(a.mdd) },
          { label: 'Expense ratio', value: (a: Asset) => (a.expense === null ? 'Not applicable' : fmtPct(a.expense, { dp: 2 })) },
        ]
      : []),
  ];

  // Summary cards.
  const lowestRiskNonStock = assets.filter((a) => a.type !== 'stock').sort((a, b) => a.vol - b.vol)[0];
  const issue = assets.map((a) => fitIssue(a, profile)).find(Boolean) ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <header>
        <h1 className="text-2xl font-semibold text-ink">Compare important differences</h1>
        <p className="text-sm text-ink-2">No asset is universally superior. Compare roles, risks and limitations in the context of your profile.</p>
      </header>

      <div role="group" aria-label="Choose assets to compare" className="flex shrink-0 flex-wrap items-center gap-2">
        {ASSETS.map((a) => {
          const on = picked.includes(a.ticker);
          return (
            <button
              key={a.ticker}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(a.ticker)}
              className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition duration-200 ${
                on ? 'border-line-strong bg-raised text-ink' : 'border-line text-ink-2 hover:text-ink'
              }`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: colorOf(a.ticker) }} aria-hidden="true" />
              {a.ticker}
            </button>
          );
        })}
        <span className="text-xs text-ink-3">Up to {MAX_COMPARED} at a time</span>
      </div>

      <Card dense className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
        {assets.length === 0 ? (
          <div className="p-4">
            <EmptyState title="Choose assets to compare" body="Tick one or more assets above to see how they differ." />
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-hidden">
            <table className="w-full table-fixed border-collapse text-left">
              <colgroup>
                <col style={{ width: '170px' }} />
                {assets.map((a) => (
                  <col key={a.ticker} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="p-3 align-bottom text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                    Comparison
                  </th>
                  {assets.map((a) => (
                    <th key={a.ticker} scope="col" className="border-l border-line p-3 align-top font-normal">
                      <div className="flex items-center gap-2.5">
                        <span
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold text-page"
                          style={{ background: colorOf(a.ticker) }}
                          aria-hidden="true"
                        >
                          {a.ticker.slice(0, 3)}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-ink">{a.ticker}</span>
                          <span className="block truncate text-[11px] text-ink-2">{a.name}</span>
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.label} className="border-t border-line">
                    <th scope="row" className="p-2.5 align-middle text-xs font-normal text-ink-2">
                      <span className="flex items-center justify-between gap-2">
                        {r.label}
                        {r.help && <HelpTip text={r.help} />}
                      </span>
                    </th>
                    {assets.map((a) => (
                      <td key={a.ticker} className={`border-l border-line p-2.5 align-middle text-xs ${r.tone === 'caution' ? 'text-caution' : 'text-ink'}`}>
                        {r.value(a)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid shrink-0 gap-3 md:grid-cols-2">
        <Card dense className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-ink">Strongest diversification contribution</p>
            <p className="text-xs text-ink-2">
              {lowestRiskNonStock
                ? `${lowestRiskNonStock.ticker} has the lowest historical volatility of the non-stock assets you chose (${fmtPct(lowestRiskNonStock.vol)}). It still carries risk.`
                : 'No bond or lower-volatility asset is selected to compare.'}
            </p>
          </div>
        </Card>
        <Card dense className="flex items-start gap-3">
          {issue ? (
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-caution" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
          )}
          <div>
            <p className="text-sm font-semibold text-ink">Most important incompatibility</p>
            <p className="text-xs text-ink-2">{issue ?? 'None of the assets you chose clashes with your profile.'}</p>
          </div>
        </Card>
      </div>
    </div>
  );
}
