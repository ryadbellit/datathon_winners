export type Objective = 'growth' | 'balanced' | 'preservation' | 'income';
export type Horizon = 'short' | 'medium' | 'long';
export type Comfort = 'stability' | 'ups-downs' | 'fluctuations';
export type AssetInterest = 'stock' | 'etf' | 'bond' | 'other';
export type AssetType = AssetInterest; // 'other' = gold and crypto
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
  /** Historical annualised return over the dataset window, percent (past, not expected). */
  expReturn: number;
  /** Historical return over the last 12 months, percent. */
  return1y: number;
  /** Historical annualised volatility over the dataset window, percent. */
  vol: number;
  /** Historical maximum drawdown over the dataset window, percent (negative). */
  mdd: number;
  /** Expense ratio, percent, or null when not available. */
  expense: number | null;
  /** Base weight in the proposed mix, percent. */
  baseWeight: number;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  /** Historical window replayed (YYYY-MM-DD). */
  start: string;
  end: string;
  /** Actual move per ticker over the window, percent (USD, adjusted). */
  moves: Record<string, number>;
  explanation: string;
}

export interface Option<T extends string> {
  value: T;
  label: string;
  description?: string;
  phrase?: string;
}
