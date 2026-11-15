import { isFiniteNumber } from '../lib/engine';

/** Shared formatting helpers. Anything that is not a finite number renders as an em dash. */

const DASH = '—';

export function fmtPct(value: number, opts: { dp?: number; sign?: boolean } = {}): string {
  if (!isFiniteNumber(value)) return DASH;
  const dp = opts.dp ?? 1;
  const rounded = Number(value.toFixed(dp));
  const body = Math.abs(rounded).toFixed(dp);
  if (rounded < 0) return `-${body}%`;
  return `${opts.sign && rounded > 0 ? '+' : ''}${body}%`;
}

/** Whole-dollar display, rounded to the nearest hundred by default. */
export function fmtUSD(value: number, opts: { roundTo?: number } = {}): string {
  if (!isFiniteNumber(value)) return DASH;
  const step = opts.roundTo ?? 100;
  const rounded = Math.round(value / step) * step;
  const abs = Math.abs(rounded).toLocaleString('en-US', { maximumFractionDigits: 0 });
  return `${rounded < 0 ? '-' : ''}$${abs}`;
}

export function fmtWeight(value: number): string {
  return fmtPct(value, { dp: 1 });
}

export function fmtNumber(value: number, dp = 1): string {
  if (!isFiniteNumber(value)) return DASH;
  return value.toFixed(dp);
}

