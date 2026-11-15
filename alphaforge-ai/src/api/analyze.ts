import { ASSETS } from '../data/assets';
import type { Profile } from '../data/types';

export type Assessment = 'supported' | 'partially_supported' | 'insufficient_evidence';

/** Backend TeamReport as used by the UI (chat + Debug page). */
export interface AnalysisResult {
  answer: string;
  assessment: Assessment;
  sources: string[];
  debate_rounds: number;
  failures: string[];
  estimated_cost_usd: number | null;
  /** evidence: 5 agents + debate; general_knowledge: no data found, the LLM answered from general knowledge (unverified). */
  answer_mode?: 'evidence' | 'general_knowledge' | 'incomplete';
  /** Full report, shown by the Debug page (/debug). */
  evidence?: Evidence[];
  research?: AgentOutput;
  events?: AgentOutput;
  portfolio?: AgentOutput;
  conspiracy?: AgentOutput;
  devil?: AgentOutput;
  governance?: AgentOutput;
  rebuttals?: Rebuttal[];
  agent_results?: AgentResult[];
}

export interface Evidence {
  id: string;
  kind: 'news' | 'price' | 'metric' | 'check' | 'document' | 'knowledge_base'; // metric / check: computed by code
  claim: string;
  source: string;
  reference: string;
  date: string | null;
  excerpt: string;
  value: number | null;
  unit: string | null;
  validation: 'verified' | 'undated';
  /** Profile check outcome (kind === 'check'). */
  check_status?: 'ok' | 'warn' | 'fail' | null;
}

export interface AgentOutput {
  schema_version?: string;
  confidence: number;
  status: 'ok' | 'partial' | 'no_evidence' | 'skipped' | 'failed';
  error?: string | null;
  [key: string]: unknown; // fields specific to each agent
}

export interface Rebuttal {
  agent: string;
  objection: string;
  response: string;
  evidence_ids: string[];
  missing_evidence: string | null;
  concedes: boolean;
}

export interface AgentResult {
  agent: string;
  summary: string;
  confidence: number;
  model_id: string | null;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number };
  estimated_cost_usd: number | null;
  sources: string[];
  error: string | null;
}

/** Current selection as portfolio lines, weights normalised to 100 % (the backend never invents weights). */
function toHoldings(selectedIds: string[], overrides: Record<string, number>) {
  const picked = ASSETS.filter((a) => selectedIds.includes(a.ticker));
  const raw = picked.map((a) => Math.max(0, overrides[a.ticker] ?? a.baseWeight));
  const total = raw.reduce((sum, w) => sum + w, 0);
  return picked.map((a, i) => ({
    ticker: a.ticker,
    name: a.name,
    weight_pct: total > 0 ? (raw[i] / total) * 100 : 0,
    sector: a.sectors[0] ?? null,
  }));
}

/** Progress of one agent, streamed by /api/analyze/stream while the analysis runs. */
export interface AgentEvent {
  type: 'agent_start' | 'agent_end';
  agent: string; // e.g. "research", "portfolio_storyteller", "event_hunter:rebuttal", "synthesis"
  status?: string; // on agent_end: ok | partial | no_evidence | skipped | failed ...
}

type StreamEvent = AgentEvent | { type: 'report'; report: AnalysisResult } | { type: 'error'; error: string; detail?: string };

/** Runs the agent team on the question; `onEvent` is called each time an agent starts or finishes. */
export async function analyze(
  question: string,
  profile: Profile,
  selectedIds: string[],
  overrides: Record<string, number>,
  horizonYears: number | null,
  onEvent: (event: AgentEvent) => void = () => {},
): Promise<AnalysisResult> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 180_000); // the agent team with debate takes a while
  try {
    const response = await fetch('/api/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        profile: { objective: profile.objective, horizon: profile.horizon, comfort: profile.comfort, esg: profile.esg, exclusions: profile.exclusions },
        holdings: toHoldings(selectedIds, overrides),
        horizon_years: horizonYears,
      }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error ?? `HTTP ${response.status}`);
    }
    // Server-Sent Events over POST: read "data: {...}" blocks separated by a blank line.
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        if (!block.startsWith('data: ')) continue;
        const event = JSON.parse(block.slice('data: '.length)) as StreamEvent;
        if (event.type === 'report') return event.report;
        if (event.type === 'error') throw new Error(event.error);
        onEvent(event);
      }
    }
    throw new Error('Analysis stream ended without a report');
  } finally {
    window.clearTimeout(timer);
  }
}
