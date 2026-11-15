import { ChevronRight } from 'lucide-react';
import type { AgentEvent } from '../../api/analyze';

type NodeState = 'idle' | 'running' | 'done' | 'failed' | 'skipped';

/** Columns of the LangGraph workflow (alphaforge/team/graph.py), left to right; nodes in a column run in parallel. */
const COLUMNS: { id: string; label: string }[][] = [
  [{ id: 'research', label: 'Research' }],
  [
    { id: 'event_hunter', label: 'Event hunter' },
    { id: 'portfolio_storyteller', label: 'Storyteller' },
    { id: 'conspiracy_theorist', label: 'Conspiracy' },
  ],
  [{ id: 'devils_advocate', label: "Devil's advocate" }],
  [{ id: 'rebuttal', label: 'Rebuttals' }],
  [{ id: 'governance', label: 'Governance' }],
  [{ id: 'synthesis', label: 'Synthesis' }],
];

const STYLE: Record<NodeState, string> = {
  idle: 'border-line text-ink-3',
  running: 'border-model bg-model/15 text-ink animate-pulse',
  done: 'border-success bg-success/10 text-ink',
  failed: 'border-brand bg-brand/10 text-brand',
  skipped: 'border-dashed border-line text-ink-3 opacity-50',
};

/** "event_hunter:rebuttal" -> "rebuttal": the three round-2 answers share one node. */
const nodeOf = (agent: string) => (agent.endsWith(':rebuttal') ? 'rebuttal' : agent);

/** Replays the event stream into one state per node; once finished, nodes that never ran are shown as skipped. */
function nodeStates(events: AgentEvent[], finished: boolean): Record<string, NodeState> {
  const running: Record<string, number> = {};
  const states: Record<string, NodeState> = {};
  for (const { type, agent, status } of events) {
    const node = nodeOf(agent);
    if (type === 'agent_start') {
      running[node] = (running[node] ?? 0) + 1;
      states[node] = 'running';
    } else {
      running[node] = (running[node] ?? 1) - 1;
      const ended: NodeState = status === 'failed' ? 'failed' : status === 'no_evidence' || status === 'skipped' ? 'skipped' : 'done';
      if (states[node] !== 'failed' && running[node] <= 0) states[node] = ended;
      if (ended === 'failed') states[node] = 'failed';
    }
  }
  if (finished) for (const column of COLUMNS) for (const { id } of column) states[id] ??= 'skipped';
  return states;
}

/** Live view of the agent team: each agent lights up while it works, then shows whether it succeeded. */
export function AgentGraph({ events, finished }: { events: AgentEvent[]; finished: boolean }) {
  const states = nodeStates(events, finished);
  return (
    <div className="overflow-x-auto py-1" aria-label="Agent workflow progress">
      <ol className="flex min-w-max items-center gap-1">
        {COLUMNS.map((column, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3 shrink-0 text-ink-3" aria-hidden="true" />}
            <div className="flex flex-col gap-1">
              {column.map(({ id, label }) => {
                const state = states[id] ?? 'idle';
                return (
                  <span
                    key={id}
                    title={`${label}: ${state}`}
                    className={`rounded-md border px-2 py-0.5 text-center text-[10px] font-medium transition-colors ${STYLE[state]}`}
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
