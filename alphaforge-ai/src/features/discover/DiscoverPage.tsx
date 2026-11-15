import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, ArrowLeft, CheckCircle2, Info, Search } from 'lucide-react';
import { ASSETS } from '../../data/assets';
import { ASSET_INTERESTS, COMFORTS, HORIZONS, KNOWLEDGE, OBJECTIVES } from '../../data/options';
import type { Asset, AssetType, Profile } from '../../data/types';
import { useAppStore } from '../../shared/store';
import { colors } from '../../shared/tokens';
import { fmtMinutesAgo, fmtPct, fmtUSD } from '../../shared/format';
import { Card, Chip, Drawer, EmptyState, ProvenanceTag } from '../../shared/ui';
import {
  COMFORT_RULES,
  HORIZON_YEARS,
  buildMix,
  discoverAssets,
  matchesExclusions,
  type MixSnapshot,
} from '../../lib/engine';
import { FanChartCard, VerdictBanner } from '../dashboard/panels';
import { PortfolioDistribution } from '../dashboard/distribution';

type TypeFilter = 'all' | AssetType;
type Sort = 'fit' | 'volatility' | 'return';
type Status = 'in' | 'flags' | 'clear' | 'pending';

const TYPE_LABEL: Record<AssetType, string> = { stock: 'Stocks', etf: 'ETFs', bond: 'Bonds' };

interface Delta {
  median: number;
  flagged: number;
}

export function DiscoverPage() {
  const profile = useAppStore((s) => s.profile) as Profile;
  const selectedIds = useAppStore((s) => s.selectedIds);
  const overrides = useAppStore((s) => s.weightOverrides);
  const viewMode = useAppStore((s) => s.viewMode);
  const horizonOverride = useAppStore((s) => s.horizonOverride);
  const toggleAsset = useAppStore((s) => s.toggleAsset);
  const setWeight = useAppStore((s) => s.setWeight);
  const resetWeights = useAppStore((s) => s.resetWeights);
  const setHorizon = useAppStore((s) => s.setHorizon);
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [sort, setSort] = useState<Sort>('fit');
  const [whyOpen, setWhyOpen] = useState(false);
  const [focusTicker, setFocusTicker] = useState<string | null>(null);

  const advanced = viewMode === 'advanced';
  const horizonYears = horizonOverride ?? HORIZON_YEARS[profile.horizon];
  const discovered = useMemo(() => discoverAssets(profile), [profile]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = discovered.filter((a) => typeFilter === 'all' || a.type === typeFilter);
    if (q) list = list.filter((a) => a.ticker.toLowerCase().includes(q) || a.name.toLowerCase().includes(q));
    if (advanced && sort === 'volatility') list = [...list].sort((a, b) => a.vol - b.vol);
    if (advanced && sort === 'return') list = [...list].sort((a, b) => b.expReturn - a.expReturn);
    return list;
  }, [discovered, query, typeFilter, sort, advanced]);

  const selectedAssets = useMemo(() => ASSETS.filter((a) => selectedIds.includes(a.ticker)), [selectedIds]);
  const committed = useMemo<MixSnapshot | null>(
    () => buildMix(profile, selectedAssets, overrides, horizonYears),
    [profile, selectedAssets, overrides, horizonYears],
  );

  // What-if preview for the asset open in the detail view (only when not yet selected).
  const focusAsset = ASSETS.find((a) => a.ticker === focusTicker) ?? null;
  const focusSelected = focusAsset ? selectedIds.includes(focusAsset.ticker) : false;
  const preview = useMemo(() => {
    if (!focusAsset || focusSelected) return null;
    const m = buildMix(profile, [...selectedAssets, focusAsset], overrides, horizonYears);
    return m ? { ticker: focusAsset.ticker, series: m.series, end: m.end, flagged: m.flagged } : null;
  }, [focusAsset, focusSelected, profile, selectedAssets, overrides, horizonYears]);

  // Per-tile status: would adding this asset raise the number of flagged checks?
  const statusOf = useMemo(() => {
    const base = committed?.flagged;
    const map: Record<string, Status> = {};
    for (const a of ASSETS) {
      if (selectedIds.includes(a.ticker)) map[a.ticker] = 'in';
      else if (base === undefined) map[a.ticker] = 'pending';
      else {
        const m = buildMix(profile, [...selectedAssets, a], overrides, horizonYears);
        map[a.ticker] = m && m.flagged > base ? 'flags' : 'clear';
      }
    }
    return map;
  }, [committed, selectedIds, profile, selectedAssets, overrides, horizonYears]);

  // "Since your last change" delta, recorded whenever the committed mix changes.
  const medianKey = committed ? committed.end.median : null;
  const flaggedKey = committed ? committed.flagged : null;
  const lastRef = useRef<Delta | null>(null);
  const [delta, setDelta] = useState<Delta | null>(null);
  useEffect(() => {
    if (medianKey === null || flaggedKey === null) return;
    const prev = lastRef.current;
    if (prev) setDelta({ median: medianKey - prev.median, flagged: flaggedKey - prev.flagged });
    lastRef.current = { median: medianKey, flagged: flaggedKey };
  }, [medianKey, flaggedKey]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h1 className="text-xl font-semibold text-ink">Opportunities selected for your profile</h1>
        <button type="button" className="btn-outline-brand px-3 py-1.5 text-sm" onClick={() => setWhyOpen(true)}>
          <Info className="h-4 w-4" aria-hidden="true" />
          Why am I seeing this?
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3">
        {/* Slim verdict strip. */}
        {committed ? (
          <VerdictBanner checks={committed.checks} flagged={committed.checks.filter((c) => !c.passed)} />
        ) : (
          <div className="rounded-xl border border-dashed border-line-strong px-3 py-2.5 text-sm text-ink-2">
            Select at least one stock below to build your mix.
          </div>
        )}
        {(delta || preview) && (
          <p className="-mt-1 flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-ink-2">
            {delta && (
              <span>
                Since your last change: typical outcome {signed(delta.median)} ·{' '}
                {delta.flagged === 0 ? 'no change in flags' : delta.flagged > 0 ? `${delta.flagged} more flagged` : `${-delta.flagged} fewer flagged`}
              </span>
            )}
            {preview && committed && (
              <span className="text-model" role="status">
                Preview with {preview.ticker}: typical outcome {fmtUSD(preview.end.median)}, {previewFlagText(preview.flagged, committed.flagged)}.
              </span>
            )}
          </p>
        )}

        {/* Top: the graph, full width. */}
        {committed ? (
          <Card dense className="flex min-h-0 flex-1 flex-col">
            <FanChartCard
              series={committed.series}
              end={committed.end}
              horizonYears={horizonYears}
              advanced={advanced}
              onHorizon={setHorizon}
              defaultYears={HORIZON_YEARS[profile.horizon]}
              preview={preview ? { ticker: preview.ticker, series: preview.series, end: preview.end } : null}
            />
          </Card>
        ) : (
          <Card dense>
            <p className="py-10 text-center text-sm text-ink-2">Your future value chart appears once you select a stock.</p>
          </Card>
        )}

        {/* Bottom: distribution (left) and stock search (right). */}
        <div className="grid gap-3 lg:h-[260px] lg:grid-cols-12">
          <Card dense className="flex min-h-0 flex-col lg:col-span-5">
            {committed ? (
              <div className="flex min-h-0 flex-1 flex-col">
                <PortfolioDistribution
                  holdings={committed.holdings}
                  advanced={advanced}
                  overrides={overrides}
                  onWeight={setWeight}
                  onReset={resetWeights}
                />
              </div>
            ) : (
              <>
                <h2 className="text-sm font-semibold text-ink">Portfolio distribution</h2>
                <p className="mt-2 text-sm text-ink-3">No mix yet. Select stocks to see the distribution.</p>
              </>
            )}
          </Card>

          <Card dense className="flex min-h-0 flex-col lg:col-span-7">
            {focusAsset ? (
              <AssetDetail
                asset={focusAsset}
                profile={profile}
                advanced={advanced}
                selected={focusSelected}
                onToggle={() => toggleAsset(focusAsset.ticker)}
                onBack={() => setFocusTicker(null)}
              />
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold text-ink">Stocks and funds</h2>
                  <div className="relative min-w-[160px] flex-1">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" aria-hidden="true" />
                    <label htmlFor="asset-search" className="sr-only">
                      Search assets or tickers
                    </label>
                    <input
                      id="asset-search"
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search assets or tickers"
                      className="focus-ring w-full rounded-lg border border-line bg-raised py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-ink-3"
                    />
                  </div>
                  <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by asset type">
                    {(['all', 'stock', 'etf', 'bond'] as TypeFilter[]).map((f) => (
                      <Chip key={f} selected={typeFilter === f} onToggle={() => setTypeFilter(f)}>
                        {f === 'all' ? 'All' : TYPE_LABEL[f]}
                      </Chip>
                    ))}
                  </div>
                  {advanced && (
                    <select
                      aria-label="Sort assets"
                      value={sort}
                      onChange={(e) => setSort(e.target.value as Sort)}
                      className="focus-ring rounded-lg border border-line bg-raised px-2 py-1.5 text-xs text-ink"
                    >
                      <option value="fit">Fit to profile</option>
                      <option value="volatility">Lowest volatility</option>
                      <option value="return">Illustrative return</option>
                    </select>
                  )}
                </div>

                <div className="mt-2 min-h-0 flex-1">
                  {discovered.length === 0 ? (
                    <EmptyState
                      title="No assets match your profile yet"
                      body="Your risk comfort, horizon or asset types filter out every example asset."
                      actionLabel="Update your profile"
                      onAction={() => navigate('/onboarding')}
                    />
                  ) : visible.length === 0 ? (
                    <p className="text-sm text-ink-2">
                      No search results.{' '}
                      <button type="button" className="focus-ring rounded text-brand-hover hover:underline" onClick={() => { setQuery(''); setTypeFilter('all'); }}>
                        Clear search and filters
                      </button>
                    </p>
                  ) : (
                    <ul className="grid grid-cols-2 gap-2 lg:grid-cols-3">
                      {visible.map((asset) => (
                        <AssetTile
                          key={asset.ticker}
                          asset={asset}
                          status={statusOf[asset.ticker] ?? 'pending'}
                          selected={selectedIds.includes(asset.ticker)}
                          onFocus={() => setFocusTicker(asset.ticker)}
                          onToggle={() => toggleAsset(asset.ticker)}
                        />
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </Card>
        </div>
      </div>

      <p className="mt-3 text-xs text-ink-3">Example data only. Simulation only. Not financial advice.</p>

      <WhyDrawer open={whyOpen} onClose={() => setWhyOpen(false)} profile={profile} />
    </div>
  );
}

function signed(n: number): string {
  return `${n > 0 ? '+' : ''}${fmtUSD(n)}`;
}

function previewFlagText(previewFlagged: number, committedFlagged: number): string {
  const diff = previewFlagged - committedFlagged;
  if (diff <= 0) return 'no new flags';
  return `${diff} new ${diff === 1 ? 'flag' : 'flags'}`;
}

/* ---------- Compact stock tile: ticker, status dot, Select ---------- */

const STATUS_TEXT: Record<Status, string> = {
  in: 'In mix',
  flags: 'Would add a flag',
  clear: 'No new flags',
  pending: 'Select to test',
};

const STATUS_DOT: Record<Status, string> = {
  in: 'bg-success',
  flags: 'bg-caution',
  clear: 'bg-data-slate',
  pending: 'bg-ink-3',
};

/** Status as a coloured dot. The word is in the tooltip and for screen readers. */
function StatusDot({ status }: { status: Status }) {
  return (
    <span className="inline-flex items-center" title={STATUS_TEXT[status]}>
      <span className={`h-2 w-2 rounded-full ${STATUS_DOT[status]}`} aria-hidden="true" />
      <span className="sr-only">{STATUS_TEXT[status]}</span>
    </span>
  );
}

function AssetTile({
  asset,
  status,
  selected,
  onFocus,
  onToggle,
}: {
  asset: Asset;
  status: Status;
  selected: boolean;
  onFocus: () => void;
  onToggle: () => void;
}) {
  return (
    <li
      className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2 transition duration-200 ${
        selected ? 'border-line-strong bg-raised' : 'border-line bg-surface hover:bg-raised'
      }`}
    >
      <button type="button" onClick={onFocus} className="focus-ring flex min-w-0 items-center gap-2 rounded text-left">
        <span className="text-xs font-semibold text-ink">{asset.ticker}</span>
        <StatusDot status={status} />
      </button>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onToggle}
        className={`focus-ring shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium transition duration-200 ${
          selected ? 'border-brand bg-brand text-white' : 'border-line-strong text-ink hover:bg-raised'
        }`}
      >
        {selected ? 'Selected' : 'Select'}
        <span className="sr-only"> {asset.ticker}</span>
      </button>
    </li>
  );
}

/* ---------- Asset detail (inside the bottom-right box) ---------- */

/** Deterministic mock price series, so the same ticker always draws the same line. */
function mockPriceSeries(asset: Asset) {
  let seed = 0;
  for (const ch of asset.ticker) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const gauss = () => Math.sqrt(-2 * Math.log(Math.max(rand(), 1e-9))) * Math.cos(2 * Math.PI * rand());
  const drift = asset.expReturn / 100 / 12;
  const shock = asset.vol / 100 / Math.sqrt(12);
  let price = 100;
  const out: { month: number; price: number }[] = [];
  for (let m = 0; m <= 60; m++) {
    out.push({ month: m, price: Number(price.toFixed(2)) });
    price = price * Math.exp(drift - 0.5 * shock * shock + shock * gauss());
  }
  return out;
}

/** Compact hover box for the stock chart: one line with the time and the price. */
function PriceTooltip(props: { active?: boolean; payload?: Array<{ payload?: unknown }> }) {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  const point = props.payload[0]?.payload as { month: number; price: number } | undefined;
  if (!point) return null;
  return (
    <div className="rounded-md border border-line-strong bg-raised px-2 py-1 text-[11px] text-ink">
      {(point.month / 12).toFixed(1)} yrs · {point.price.toFixed(2)}
    </div>
  );
}

function AssetDetail({
  asset,
  profile,
  advanced,
  selected,
  onToggle,
  onBack,
}: {
  asset: Asset;
  profile: Profile;
  advanced: boolean;
  selected: boolean;
  onToggle: () => void;
  onBack: () => void;
}) {
  const series = useMemo(() => mockPriceSeries(asset), [asset]);
  const rules = COMFORT_RULES[profile.comfort];
  const riskFit = asset.vol <= rules.riskFitCeiling;
  const horizonFit = !(asset.type === 'stock' && asset.vol > 30) || (profile.comfort !== 'stability' && profile.horizon !== 'short');
  const exclusionFit = !matchesExclusions(asset, profile.exclusions);
  const fits = [
    { label: 'Risk fit', passed: riskFit, text: riskFit ? 'within your range' : 'above your range' },
    { label: 'Horizon fit', passed: horizonFit, text: horizonFit ? 'suits your horizon' : 'better for a longer horizon' },
    { label: 'Exclusions', passed: exclusionFit, text: exclusionFit ? 'no match' : 'matches an exclusion' },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <button type="button" onClick={onBack} className="focus-ring inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-ink-2 hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          All stocks
        </button>
        <p className="min-w-0 truncate text-sm font-semibold text-ink">
          {asset.ticker} <span className="font-normal text-ink-2">· {asset.name}</span>
        </p>
        <button type="button" onClick={onToggle} className={selected ? 'btn-secondary px-2.5 py-1 text-xs' : 'btn-primary px-2.5 py-1 text-xs'}>
          {selected ? 'Remove from mix' : 'Add to mix'}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="min-w-0">
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={colors.border} vertical={false} />
                <XAxis dataKey="month" tickFormatter={(m: number) => `${Math.round(m / 12)}y`} tick={{ fill: colors.textMuted, fontSize: 10 }} stroke={colors.border} />
                <YAxis tick={{ fill: colors.textMuted, fontSize: 10 }} stroke={colors.border} width={36} domain={['auto', 'auto']} />
                                <Tooltip content={PriceTooltip} cursor={{ stroke: colors.textMuted, strokeDasharray: '3 3' }} />
                <Line type="monotone" dataKey="price" stroke={colors.dataSlate} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-[10px] text-ink-3">
            <ProvenanceTag kind="hypothetical" />
            Example data · {asset.typeLabel} · updated {fmtMinutesAgo(asset.updatedMinutesAgo)}
          </p>
        </div>

        <div className="flex min-w-0 flex-col gap-1 text-xs">
          <p><span className="font-semibold text-ink">Role: </span><span className="text-ink-2">{asset.role}</span></p>
          <p><span className="font-semibold text-ink">Why: </span><span className="text-ink-2">{asset.why}</span></p>
          <p className="flex gap-1">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-caution" aria-hidden="true" />
            <span className="text-ink-2">{asset.limitation}</span>
          </p>
          {fits.map((f) => (
            <p key={f.label} className="flex items-center gap-1">
              {f.passed ? (
                <CheckCircle2 className="h-3 w-3 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <AlertTriangle className="h-3 w-3 shrink-0 text-caution" aria-hidden="true" />
              )}
              <span className="text-ink">{f.label}:</span>
              <span className="text-ink-2">{f.passed ? 'pass' : 'flagged'}, {f.text}</span>
            </p>
          ))}
        </div>
      </div>

      {advanced && (
        <p className="border-t border-line pt-1.5 text-[11px] text-ink-2">
          Return {fmtPct(asset.expReturn)} · Volatility {fmtPct(asset.vol)} · Max drawdown {fmtPct(asset.mdd)} · Expense ratio{' '}
          {asset.expense === null ? 'n/a' : fmtPct(asset.expense, { dp: 2 })}
          <span className="text-ink-3"> (return and volatility are model estimates; drawdown is historical)</span>
        </p>
      )}
    </div>
  );
}

/* ---------- Why am I seeing this? ---------- */

function WhyDrawer({ open, onClose, profile }: { open: boolean; onClose: () => void; profile: Profile }) {
  const answers: { label: string; value: string }[] = [
    { label: 'Objective', value: OBJECTIVES.find((o) => o.value === profile.objective)?.label ?? '' },
    { label: 'Horizon', value: HORIZONS.find((h) => h.value === profile.horizon)?.label ?? '' },
    { label: 'Risk comfort', value: COMFORTS.find((c) => c.value === profile.comfort)?.label ?? '' },
    { label: 'Asset types', value: profile.assetTypes.map((a) => ASSET_INTERESTS.find((o) => o.value === a)?.label ?? '').join(', ') },
    { label: 'Regions', value: profile.regions.join(', ') || 'Any' },
    { label: 'Sectors', value: profile.sectors.join(', ') || 'None set' },
    { label: 'ESG', value: profile.esg === 'none' ? 'No strong preference' : 'Noted, not scored in this prototype' },
    { label: 'Exclusions', value: profile.exclusions.trim() || 'None' },
    { label: 'Knowledge level', value: KNOWLEDGE.find((k) => k.value === profile.knowledge)?.label ?? '' },
  ];
  const rules = COMFORT_RULES[profile.comfort];
  return (
    <Drawer open={open} onClose={onClose} title="Why am I seeing this?">
      <p className="text-sm text-ink-2">These are the profile answers used to choose and order the examples.</p>
      <dl className="mt-4 grid gap-3">
        {answers.map((a) => (
          <div key={a.label} className="rounded-xl border border-line p-3">
            <dt className="text-xs uppercase tracking-wide text-ink-3">{a.label}</dt>
            <dd className="mt-1 text-sm text-ink">{a.value}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mt-8 text-base font-semibold text-ink">How examples were filtered and ranked</h3>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-2">
        <li>Keep only the asset types you selected. Other assets add nothing in this prototype.</li>
        <li>Keep assets whose region matches your chosen regions. Global matches every region.</li>
        <li>
          Apply a risk fit: volatility up to {rules.riskFitCeiling === Number.POSITIVE_INFINITY ? 'any level' : `${rules.riskFitCeiling}%`}. Individual stocks above 30% volatility appear only for balanced or higher comfort with a medium or long horizon.
        </li>
        <li>Boost assets in preferred sectors. ESG preferences are noted, but no ESG scores are included.</li>
        <li>Remove assets that match your exclusions by sector or keyword.</li>
        <li>Order by fit to your profile, with broad funds first for Beginner and Intermediate users.</li>
      </ol>
      <p className="mt-6 text-sm text-ink-2">This is educational analysis, not a recommendation.</p>
      <p className="mt-3 text-xs text-ink-3">
        A balanced starting point, not a recommendation. Example values only.
        {profile.esg !== 'none' && ' No ESG data is included, so ESG preferences are noted but not scored.'}
      </p>
    </Drawer>
  );
}
