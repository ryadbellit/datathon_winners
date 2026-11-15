import type { Profile } from './types';

/**
 * The three reference personas of the datathon brief, with a fictive portfolio drawn from the starter universe
 * and the question that tests each one. Loading a persona replaces the current profile and selection.
 */
export interface Persona {
  id: 'amira' | 'mateo' | 'robert';
  name: string;
  summary: string;
  /** What the brief says this persona tests. */
  tests: string;
  profile: Profile;
  /** Fictive weights, percent (sum to 100). */
  weights: Record<string, number>;
  question: string;
}

export const PERSONAS: Persona[] = [
  {
    id: 'amira',
    name: 'Amira, 26',
    summary: 'Software engineer · high risk · 15+ years · AI, growth and crypto',
    tests: '"High risk" must not mean "anything goes": diversification still matters.',
    profile: {
      objective: 'growth',
      horizon: 'long',
      comfort: 'fluctuations',
      assetTypes: ['stock', 'etf', 'bond', 'other'],
      sectors: ['Technology'],
      regions: ['United States', 'Canada', 'Global'],
      esg: 'none',
      exclusions: '',
      knowledge: 'intermediate',
    },
    weights: { QQQ: 25, NVDA: 15, 'SHOP.TO': 10, 'BTC-USD': 15, 'ETH-USD': 5, 'XIU.TO': 15, AGG: 15 },
    question: 'Mon portefeuille est-il assez diversifié pour mon profil ?',
  },
  {
    id: 'mateo',
    name: 'Mateo, 41',
    summary: 'Operations manager · moderate risk · 8 to 12 years · strong ESG preferences',
    tests: 'Can the system weigh non-financial criteria, not only return and risk?',
    profile: {
      objective: 'balanced',
      horizon: 'long',
      comfort: 'ups-downs',
      assetTypes: ['stock', 'etf', 'bond'],
      sectors: [],
      regions: ['Canada', 'United States'],
      esg: 'strong',
      exclusions: '',
      knowledge: 'intermediate',
    },
    weights: { ESGV: 30, 'XIU.TO': 15, 'XBB.TO': 25, AGG: 10, 'ENB.TO': 10, MSFT: 10 },
    question: 'Mon portefeuille respecte-t-il mes préférences ESG ?',
  },
  {
    id: 'robert',
    name: 'Robert, 59',
    summary: 'Health professional · low to moderate risk · 3 to 5 years · capital preservation',
    tests: 'Can the system question a request that does not fit the profile, instead of agreeing?',
    profile: {
      objective: 'preservation',
      horizon: 'medium',
      comfort: 'stability',
      assetTypes: ['stock', 'etf', 'bond'],
      sectors: ['Healthcare', 'Consumer', 'Financials'],
      regions: ['Canada', 'United States'],
      esg: 'none',
      exclusions: '',
      knowledge: 'advanced',
    },
    weights: { 'XBB.TO': 30, 'ZST.TO': 15, AGG: 15, JNJ: 10, PG: 10, 'RY.TO': 10, SPY: 10 },
    question: "Je pense acheter du Tesla. Est-ce une bonne idée pour moi ?",
  },
];
