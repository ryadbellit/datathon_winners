import type { AssetInterest, Comfort, EsgPref, Horizon, Knowledge, Objective, Option } from './types';

export const OBJECTIVES: Option<Objective>[] = [
  { value: 'growth', label: 'Long-term growth', description: 'Focus on increasing value over many years', phrase: 'long-term growth' },
  { value: 'balanced', label: 'Balanced growth and stability', description: 'Pursue growth while reducing some ups and downs', phrase: 'balanced growth and stability' },
  { value: 'preservation', label: 'Capital preservation', description: 'Prioritize protecting value over higher growth', phrase: 'capital preservation' },
  { value: 'income', label: 'Income generation', description: 'Focus on assets that may provide regular income', phrase: 'income generation' },
];

export const HORIZONS: Option<Horizon>[] = [
  { value: 'short', label: 'Short term', description: 'Under 3 years', phrase: 'short term' },
  { value: 'medium', label: 'Medium term', description: '3-7 years', phrase: 'medium term' },
  { value: 'long', label: 'Long term', description: '7+ years', phrase: 'long term' },
];

export const COMFORTS: Option<Comfort>[] = [
  { value: 'stability', label: 'I prefer stability, even if growth is slower.', description: 'Smaller changes are more important to me than maximum growth.', phrase: 'You prefer stability, even if growth is slower' },
  { value: 'ups-downs', label: 'I can accept some ups and downs for potential growth.', description: 'I understand that value may fall temporarily.', phrase: 'You can accept some market movement' },
  { value: 'fluctuations', label: 'I can tolerate significant fluctuations for potentially higher long-term growth.', description: 'Large changes would not make me abandon my long-term plan.', phrase: 'You can tolerate significant fluctuations' },
];

export const ASSET_INTERESTS: Option<AssetInterest>[] = [
  { value: 'stock', label: 'Stocks' },
  { value: 'etf', label: 'ETFs' },
  { value: 'bond', label: 'Bonds' },
  { value: 'other', label: 'Other assets' },
];

export const SECTORS = ['Technology', 'Healthcare', 'Consumer', 'Energy', 'Financials'];

export const REGIONS = ['Global', 'Canada', 'United States', 'Europe', 'Asia', 'Emerging markets'];

export const ESG_OPTIONS: Option<EsgPref>[] = [
  { value: 'none', label: 'No strong preference' },
  { value: 'aware', label: 'Prefer ESG-aware options' },
  { value: 'strong', label: 'Strong ESG requirement' },
];

export const KNOWLEDGE: Option<Knowledge>[] = [
  { value: 'beginner', label: 'Beginner', description: 'I am still learning the basics.' },
  { value: 'intermediate', label: 'Intermediate', description: 'I understand common investment concepts.' },
  { value: 'advanced', label: 'Advanced', description: 'I am comfortable interpreting financial metrics.' },
];

export const PRESET_QUESTIONS = [
  'Why this mix?',
  'What is my worst case?',
  'What if 2022 repeats?',
  'What drives the risk?',
];
