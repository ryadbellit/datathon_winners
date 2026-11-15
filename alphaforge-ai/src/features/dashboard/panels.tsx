import { useMemo, useState, type FormEvent } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, CheckCircle2, Sparkles } from 'lucide-react';
import { PRESET_QUESTIONS } from '../../data/options';
import { colors } from '../../shared/tokens';
import { fmtPct, fmtUSD } from '../../shared/format';
import { Chip, ProvenanceTag } from '../../shared/ui';
import {
  CAPITAL,
  HORIZON_CHOICES,
  answerFor,
  matchPreset,
  type AnswerContext,
  type Check,
  type FanPoint,
  type Holding,
  type PortfolioStats,
  type PresetQuestion,
} from '../../lib/engine';

/* ---------- Verdict ---------- */

export function VerdictBanner({ checks, flagged }: { checks: Check[]; flagged: Check[] }) {
  const ok = flagged.length === 0;
  return (
    <div className="group relative">
      <div
        role="status"
        tabIndex={ok ? -1 : 0}
        aria-label={ok ? 'Fits your profile' : `${flagged.length} checks flagged. Hover or focus for details.`}
        className={`flex items-center gap-2 rounded-xl border px-3 py-2 ${
          ok ? 'border-success/50 bg-success/10' : 'border-caution/50 bg-caution/10'
        }`}
      >
        {ok ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
        ) : (
          <AlertTriangle className="h-4 w-4 shrink-0 text-caution" aria-hidden="true" />
        )}
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
          {ok ? 'Fits your profile.' : `${flagged.length} ${flagged.length === 1 ? 'check' : 'checks'} flagged: ${flagged.map((c) => c.name).join(', ')}`}
        </p>
        {!ok && <span className="shrink-0 text-[11px] text-ink-2">Hover for details</span>}
      </div>

      {/* Details appear only while hovering or focusing the strip, as a small box beside it. */}
      {!ok && (
        <div
          role="tooltip"
          className="pointer-events-none invisible absolute left-0 top-full z-30 mt-1 w-[min(420px,100%)] rounded-xl border border-line-strong bg-raised p-3 opacity-0 shadow-sm transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
        >
          <ul className="grid gap-1.5">
            {checks.map((c) => (
              <li key={c.id} className="flex items-start gap-2 text-xs text-ink-2">
                {c.passed ? (
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-caution" aria-hidden="true" />
                )}
                <span>
                  <span className="text-ink">{c.name}</span>: {c.passed ? 'Pass' : 'Flagged'} · {advancedOrGuided(c)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function advancedOrGuided(c: Check): string {
  return c.passed ? c.guided : c.help;
}

/* ---------- Advanced metric strip ---------- */

export function MetricStrip({ holdings, stats }: { holdings: Holding[]; stats: PortfolioStats }) {
  const mdd = holdings.reduce((s, h) => s + (h.weight / 100) * h.asset.mdd, 0);
  const items = [
    { label: 'Expected return (illustr.)', value: fmtPct(stats.expReturn), tag: 'model' as const },
    { label: 'Volatility', value: fmtPct(stats.vol), tag: 'model' as const },
    { label: 'Max drawdown (approx.)', value: fmtPct(mdd), tag: 'historical' as const },
    { label: 'Rough-year loss', value: fmtPct(stats.p5OneYear), tag: 'model' as const },
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
      {items.map((m) => (
        <div key={m.label} className="min-w-0">
          <dt className="truncate text-[11px] text-ink-2">{m.label}</dt>
          <dd className="mt-0.5 flex flex-wrap items-center justify-between gap-1">
            <span className="text-base font-semibold text-ink">{m.value}</span>
            <ProvenanceTag kind={m.tag} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- Fan chart ---------- */

export interface PreviewCurve {
  ticker: string;
  series: FanPoint[];
  end: FanPoint;
}


function FanTooltip(props: { active?: boolean; payload?: Array<{ payload?: unknown }>; label?: unknown }) {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  const point = props.payload[0]?.payload as (FanPoint & { previewMedian?: number }) | undefined;
  if (!point) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-raised p-2 text-xs text-ink">
      <p className="mb-1 font-semibold">{point.label}</p>
      <p>Strong: {fmtUSD(point.p95)}</p>
      <p>Median: {fmtUSD(point.median)}</p>
      <p>Rough: {fmtUSD(point.p5)}</p>
      {typeof point.previewMedian === 'number' && <p className="text-model">With preview: {fmtUSD(point.previewMedian)}</p>}
    </div>
  );
}

export function FanChartCard({
  series,
  end,
  horizonYears,
  advanced,
  onHorizon,
  defaultYears,
  preview,
  chartHeight,
}: {
  series: FanPoint[];
  end: FanPoint;
  horizonYears: number;
  advanced: boolean;
  onHorizon: (y: number | null) => void;
  defaultYears: number;
  preview?: PreviewCurve | null;
  /** Height of the chart area in px. */
  chartHeight?: number;
}) {
  const [showTable, setShowTable] = useState(false);
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const pct = (v: number) => fmtPct(((v / CAPITAL) - 1) * 100, { sign: true });

  const data = useMemo(
    () => series.map((p, i) => ({ ...p, previewMedian: preview ? preview.series[i]?.median : undefined })),
    [series, preview],
  );

  const legend = advanced
    ? [
        { name: '95th percentile', value: end.p95, note: pct(end.p95) },
        { name: 'Median', value: end.median, note: pct(end.median) },
        { name: '5th percentile', value: end.p5, note: pct(end.p5) },
      ]
    : [
        { name: 'Strong outcome', value: end.p95, note: 'Better than most paths' },
        { name: 'Typical outcome', value: end.median, note: 'The middle path' },
        { name: 'Rough outcome', value: end.p5, note: '1 in 20 chance of less' },
      ];

  const summary = `Median outcome after ${horizonYears} years is about ${fmtUSD(end.median)}, with a rough case near ${fmtUSD(end.p5)}.`;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold text-ink">Your future value</h2>
          <span className="text-[11px] text-ink-3">Starting {fmtUSD(CAPITAL)} (fictive)</span>
        </div>
        <div className="flex items-center gap-2">
          {advanced && (
            <button type="button" onClick={() => setShowTable((v) => !v)} className="focus-ring rounded px-1.5 py-0.5 text-[11px] text-brand-hover hover:underline">
              {showTable ? 'Chart' : 'Table'}
            </button>
          )}
          <label htmlFor="horizon" className="sr-only">
            Horizon
          </label>
          <select
            id="horizon"
            value={horizonYears}
            onChange={(e) => {
              const v = Number(e.target.value);
              onHorizon(v === defaultYears ? null : v);
            }}
            className="focus-ring rounded-md border border-line bg-raised px-2 py-0.5 text-xs text-ink"
          >
            {HORIZON_CHOICES.map((y) => (
              <option key={y} value={y}>
                {y} {y === 1 ? 'yr' : 'yrs'}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-2">
        {/* With no fixed chartHeight, the row and the chart fill the space left in the card. */}
        <div className={`relative min-h-0 min-w-0 flex-1 ${chartHeight ? '' : 'self-stretch'}`} style={chartHeight ? { height: chartHeight } : undefined}>
          {advanced && showTable ? (
            <div className="h-full overflow-auto rounded-lg border border-line">
              <table className="w-full text-left text-[11px]">
                <caption className="sr-only">Projected values by year</caption>
                <thead className="sticky top-0 bg-raised text-ink-2">
                  <tr>
                    <th scope="col" className="px-2 py-1 font-medium">Year</th>
                    <th scope="col" className="px-2 py-1 font-medium">5th</th>
                    <th scope="col" className="px-2 py-1 font-medium">Median</th>
                    <th scope="col" className="px-2 py-1 font-medium">95th</th>
                  </tr>
                </thead>
                <tbody>
                  {series
                    .filter((p) => Number.isInteger(p.year))
                    .map((p) => (
                      <tr key={p.year} className="border-t border-line">
                        <td className="px-2 py-0.5">{p.year}</td>
                        <td className="px-2 py-0.5">{fmtUSD(p.p5)}</td>
                        <td className="px-2 py-0.5">{fmtUSD(p.median)}</td>
                        <td className="px-2 py-0.5">{fmtUSD(p.p95)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            // Pinned to the full cell so the chart always fills the card, whatever the window size.
            <div className="absolute inset-0">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={colors.border} vertical={false} />
                <XAxis dataKey="year" tickFormatter={(v: number) => `${v}y`} tick={{ fill: colors.textMuted, fontSize: 11 }} stroke={colors.border} />
                <YAxis tickFormatter={(v: number) => fmtUSD(v, { roundTo: 1000 })} tick={{ fill: colors.textMuted, fontSize: 11 }} stroke={colors.border} width={64} />
                <Tooltip content={FanTooltip} />
                <ReferenceLine y={CAPITAL} stroke={colors.textMuted} strokeDasharray="4 4" />
                <Area type="monotone" dataKey="base" stackId="band" stroke="none" fill="transparent" isAnimationActive={!reduced} />
                <Area type="monotone" dataKey="band" stackId="band" stroke="none" fill={colors.dataSlate} fillOpacity={0.22} isAnimationActive={!reduced} />
                <Line type="monotone" dataKey="median" stroke={colors.dataSlate} strokeWidth={2.5} dot={false} isAnimationActive={!reduced} />
                {preview && (
                  <Line type="monotone" dataKey="previewMedian" stroke={colors.model} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={!reduced} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          )}
        </div>

        <ul className="grid shrink-0 grid-cols-3 gap-2 self-start md:w-[120px] md:grid-cols-1">
          {legend.map((l) => (
            <li key={l.name} className="min-w-0">
              <p className="truncate text-[10px] uppercase tracking-wide text-ink-3">{l.name}</p>
              <p className="text-sm font-semibold text-ink">{fmtUSD(l.value)}</p>
              <p className="truncate text-[10px] text-ink-2">{l.note}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
        <ProvenanceTag kind="model" />
        <span className="text-ink-2">{summary}</span>
        <span>Illustrative scenarios from a simple model. Not a forecast.</span>
      </div>
    </div>
  );
}

/* ---------- Checks tab ---------- */

export function ChecksTab({ checks, advanced }: { checks: Check[]; advanced: boolean }) {
  return (
    <ul className="flex flex-col gap-2">
      {checks.map((c) => (
        <li key={c.id} className="flex gap-2.5 rounded-lg border border-line p-2.5">
          {c.passed ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-caution" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">{c.name}</p>
              <span className={`text-[11px] font-semibold ${c.passed ? 'text-success' : 'text-caution'}`}>{c.passed ? 'Passed' : 'Flagged'}</span>
            </div>
            <p className="mt-0.5 text-xs text-ink-2">{advanced ? c.advanced : c.guided}</p>
            {!c.passed && <p className="mt-0.5 text-[11px] text-ink-3">{c.help}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Ask AlphaForge ---------- */

export function AskPanel({ ctx }: { ctx: AnswerContext | null }) {
  const [input, setInput] = useState('');
  const [answer, setAnswer] = useState<{ question: string; text: string } | null>(null);

  const ask = (question: string) => {
    const preset = matchPreset(question);
    if (!preset) {
      setAnswer({
        question,
        text: 'I can only answer questions about this analysis. A licensed financial advisor can help with anything beyond it.',
      });
      return;
    }
    if (!ctx) {
      setAnswer({ question: preset, text: 'Select at least one asset to answer this question.' });
      return;
    }
    setAnswer({ question: preset, text: answerFor(preset as PresetQuestion, ctx) });
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    ask(input);
    setInput('');
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-model" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-ink">Ask AlphaForge</h2>
      </div>
      <form onSubmit={onSubmit} className="flex gap-2" role="search">
        <label htmlFor="ask-input" className="sr-only">
          Ask a question about this analysis
        </label>
        <input
          id="ask-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Why this mix?"
          className="focus-ring min-w-0 flex-1 rounded-lg border border-line bg-raised px-3 py-1.5 text-sm text-ink placeholder:text-ink-3"
        />
        <button type="submit" className="btn-primary px-3 py-1.5 text-sm">
          Ask
        </button>
      </form>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Suggested questions">
        {PRESET_QUESTIONS.map((q) => (
          <Chip key={q} selected={answer?.question === q} onToggle={() => ask(q)}>
            {q}
          </Chip>
        ))}
      </div>
      <div className="min-h-[96px] rounded-lg border border-line bg-raised p-3" aria-live="polite">
        {answer ? (
          <>
            <p className="text-sm font-semibold text-ink">{answer.question}</p>
            <p className="mt-1 text-sm text-ink-2">{answer.text}</p>
            <p className="mt-2 text-[11px] text-ink-3">Source: figures on this page, illustrative model.</p>
          </>
        ) : (
          <p className="text-sm text-ink-3">Answers use only the numbers on this page. Pick a question or type one.</p>
        )}
      </div>
    </div>
  );
}
