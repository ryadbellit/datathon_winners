import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, Tooltip } from 'recharts';
import { RotateCcw } from 'lucide-react';
import type { Asset } from '../../data/types';
import { fmtUSD, fmtWeight } from '../../shared/format';
import { assetClassColors, holdingPalette } from '../../shared/tokens';
import { CAPITAL, type Holding } from '../../lib/engine';

const CLASS_LABEL: Record<Asset['type'], 'Stocks' | 'ETFs' | 'Bonds'> = {
  stock: 'Stocks',
  etf: 'ETFs',
  bond: 'Bonds',
};

interface Slice {
  name: string;
  value: number;
  color: string;
  /** Shown in the hover tooltip under the name. */
  detail: string;
}

/** Data appears on hover only. Nothing is written under the donuts. */
function SliceTooltip(props: { active?: boolean; payload?: Array<{ payload?: unknown }> }) {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  const s = props.payload[0]?.payload as Slice | undefined;
  if (!s) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-raised px-3 py-2 text-xs text-ink shadow-sm">
      <p className="font-semibold">{s.name}</p>
      <p className="text-ink-2">{s.detail}</p>
      <p className="mt-0.5 text-ink">{fmtWeight(s.value)}</p>
    </div>
  );
}

function Donut({ title, slices, size = 150 }: { title: string; slices: Slice[]; size?: number }) {
  return (
    <figure className="flex flex-col items-center gap-1" aria-label={title}>
      <figcaption className="text-[11px] uppercase tracking-wide text-ink-3">{title}</figcaption>
      <PieChart width={size} height={size}>
        <Pie
          data={slices}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={Math.round(size * 0.3)}
          outerRadius={Math.round(size * 0.46)}
          stroke="none"
          isAnimationActive={false}
        >
          {slices.map((s) => (
            <Cell key={s.name} fill={s.color} />
          ))}
        </Pie>
        <Tooltip content={SliceTooltip} />
      </PieChart>
    </figure>
  );
}

export function PortfolioDistribution({
  holdings,
  advanced,
  overrides,
  onWeight,
  onReset,
}: {
  holdings: Holding[];
  advanced: boolean;
  overrides: Record<string, number>;
  onWeight: (ticker: string, value: number) => void;
  onReset: () => void;
}) {
  const [editing, setEditing] = useState(false);

  const classSlices = useMemo<Slice[]>(() => {
    const map = new Map<string, { value: number; count: number }>();
    holdings.forEach((h) => {
      const key = CLASS_LABEL[h.asset.type];
      const cur = map.get(key) ?? { value: 0, count: 0 };
      map.set(key, { value: cur.value + h.weight, count: cur.count + 1 });
    });
    return Array.from(map, ([name, v]) => ({
      name,
      value: v.value,
      color: assetClassColors[name as keyof typeof assetClassColors],
      detail: `${v.count} ${v.count === 1 ? 'holding' : 'holdings'}`,
    }));
  }, [holdings]);

  // Index-based palette: holdings keep their order, so each ticker keeps its colour.
  const holdingSlices = useMemo<Slice[]>(
    () =>
      holdings.map((h, i) => ({
        name: h.asset.ticker,
        value: h.weight,
        color: holdingPalette[i % holdingPalette.length],
        detail: `${h.asset.name} · ${h.asset.typeLabel}`,
      })),
    [holdings],
  );

  const weightsValid = holdings.some((h) => h.weight > 0);

  const header = (
    <div className="flex shrink-0 items-center justify-between gap-2">
      <h2 className="text-sm font-semibold text-ink">Portfolio distribution</h2>
      {advanced && (
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          aria-expanded={editing}
          className="focus-ring rounded px-1.5 py-0.5 text-xs text-brand-hover hover:underline"
        >
          {editing ? 'Back to distribution' : 'Edit weights'}
        </button>
      )}
    </div>
  );

  // Advanced weight editor replaces the donuts while open, so nothing needs to scroll.
  if (advanced && editing) {
    return (
      <div className="flex h-full flex-col gap-2">
        {header}
        <div className="flex items-center justify-end">
          <button type="button" onClick={onReset} className="focus-ring inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-2 hover:text-ink">
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            Reset weights
          </button>
        </div>
        <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
          {holdings.map((h) => {
            const raw = overrides[h.asset.ticker] ?? h.asset.baseWeight;
            return (
              <li key={h.asset.ticker} className="flex items-center gap-2 text-xs">
                <label htmlFor={`w-${h.asset.ticker}`} className="w-11 font-semibold text-ink">
                  {h.asset.ticker}
                </label>
                <input
                  id={`w-${h.asset.ticker}`}
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={raw}
                  onChange={(e) => onWeight(h.asset.ticker, Number(e.target.value))}
                  className="min-w-0 flex-1"
                />
                <span className="w-11 text-right text-ink">{fmtWeight(h.weight)}</span>
              </li>
            );
          })}
        </ul>
        <p className="text-[11px] text-ink-3">Weights renormalize to 100%.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col justify-between gap-2">
      {header}
      <div className="flex flex-wrap items-start justify-around gap-3">
        <Donut title="Asset class" slices={classSlices} />
        <Donut title="Holdings" slices={holdingSlices} />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 border-t border-line pt-2 text-xs">
        {/* Colour legend for the asset-class donut: colour and name only. */}
        <ul className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="Asset class colours">
          {classSlices.map((c) => (
            <li key={c.name} className="flex items-center gap-1.5 text-ink-2">
              <span className="h-2 w-2 rounded-full" style={{ background: c.color }} aria-hidden="true" />
              {c.name}
            </li>
          ))}
        </ul>
        <span className="text-ink">
          Total invested <span className="font-semibold">{fmtUSD(CAPITAL)}</span>
        </span>
      </div>
      {!weightsValid && <p className="text-xs text-caution">Every weight is zero. Use Edit weights above to set at least one above zero.</p>}
    </div>
  );
}
