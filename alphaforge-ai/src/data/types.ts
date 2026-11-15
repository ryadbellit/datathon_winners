export type Objective = 'growth' | 'balanced' | 'preservation' | 'income';
export type Horizon = 'short' | 'medium' | 'long';
export type Comfort = 'stability' | 'ups-downs' | 'fluctuations';
export type AssetInterest = 'stock' | 'etf' | 'bond' | 'other';
export type AssetType = Exclude<AssetInterest, 'other'>;
export type Knowledge = 'beginner' | 'intermediate' | 'advanced';
export type EsgPref = 'none' | 'aware' | 'strong';
export type ViewMode = 'guided' | 'advanced';

export interface Profile {
  objective: Objective;
  horizon: Horizon;
  comfort: Comfort;
  assetTypes: AssetInterest[];
  sectors: string[];
  regions: string[];
  esg: EsgPref;
  exclusions: string;
  knowledge: Knowledge;
}

export interface Asset {
  ticker: string;
  name: string;
  type: AssetType;
  typeLabel: string;
  region: string;
  regions: string[];
  currency: string;
  sectors: string[];
  keywords: string[];
  role: string;
  why: string;
  limitation: string;
  /** Illustrative annual expected return, percent. */
  expReturn: number;
  /** Illustrative annual volatility, percent. */
  vol: number;
  /** Illustrative maximum drawdown, percent (negative). */
  mdd: number;
  /** Expense ratio, percent, or null for individual stocks. */
  expense: number | null;
  /** Base weight in the proposed mix, percent. */
  baseWeight: number;
  /** Minutes since the example data was "updated". */
  updatedMinutesAgo: number;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  /** Assumed move per ticker, percent (hypothetical). */
  moves: Record<string, number>;
  explanation: string;
}

export interface Option<T extends string> {
  value: T;
  label: string;
  description?: string;
  phrase?: string;
}
