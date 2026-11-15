/**
 * Design tokens for JavaScript consumers (charts, inline styles).
 * The same values are defined as Tailwind theme variables in src/index.css.
 * Keep the two files in sync when a colour changes.
 */
export const colors = {
  page: '#0E0F12',
  surface: '#16181D',
  surfaceRaised: '#1D2027',
  border: '#2A2E37',
  textPrimary: '#F5F6F8',
  textSecondary: '#A6ACB8',
  textMuted: '#7A8190',
  brand: '#E1251B',
  brandHover: '#EC4438',
  dataSlate: '#6C8CBF',
  success: '#3FB68B',
  caution: '#F2B04A',
  model: '#9B87F5',
} as const;

/** Chart series colours for asset classes. Brand red is reserved for brand and actions. */
export const assetClassColors = {
  Stocks: colors.dataSlate,
  ETFs: colors.success,
  Bonds: colors.model,
} as const;

/**
 * Slice colours for individual holdings. Deliberately different from the asset-class
 * colours above, so the two donuts are never confused. No red, no amber (those mean
 * action and caution).
 */
export const holdingPalette = [
  '#4FB8D6',
  '#D98FC4',
  '#8CC152',
  '#C9A0FF',
  '#7F8FA6',
  '#E8A87C',
  '#A3B8FF',
  '#B8C46A',
] as const;

export type ProvenanceKind = 'historical' | 'model' | 'hypothetical';

export const provenance: Record<ProvenanceKind, { label: string; color: string }> = {
  historical: { label: 'Historical observation', color: colors.dataSlate },
  model: { label: 'Model estimate', color: colors.model },
  hypothetical: { label: 'Hypothetical assumption', color: colors.caution },
};
