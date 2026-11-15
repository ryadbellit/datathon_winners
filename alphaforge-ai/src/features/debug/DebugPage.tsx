import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ChevronRight, MessageSquare, Users } from 'lucide-react';
import type { AnalysisResult, AgentOutput, Evidence, Rebuttal } from '../../api/analyze';
import { Card, EmptyState } from '../../shared/ui';

type AgentType = 'research' | 'event_hunter' | 'portfolio_storyteller' | 'conspiracy_theorist' | 'devils_advocate' | 'governance';

const AGENTS: { id: AgentType; label: string; description: string }[] = [
  { id: 'research', label: 'Research', description: 'Gathers and validates evidence' },
  { id: 'event_hunter', label: 'Event Hunter', description: 'Identifies market events' },
  { id: 'portfolio_storyteller', label: 'Portfolio Storyteller', description: 'Explains portfolio impact' },
  { id: 'conspiracy_theorist', label: 'Conspiracy Theorist', description: 'Alternative interpretations' },
  { id: 'devils_advocate', label: "Devil's Advocate", description: 'Challenges assumptions' },
  { id: 'governance', label: 'Governance', description: 'Final arbitration and validation' },
];

export function DebugPage() {
  const navigate = useNavigate();
  const [selectedAgent, setSelectedAgent] = useState<AgentType>('research');
  const [view, setView] = useState<'agents' | 'debate' | 'evidence'>('agents');
  const [report, setReport] = useState<AnalysisResult | null>(null);

  useEffect(() => {
    const reportJson = sessionStorage.getItem('debugReport');
    if (reportJson) {
      try {
        setReport(JSON.parse(reportJson));
      } catch (e) {
        console.error('Failed to parse debug report:', e);
        setReport(null);
      }
    }
  }, []);

  if (!report) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-ink">Agent Debug View</h1>
            <p className="text-xs text-ink-2">Detailed reasoning from each agent</p>
          </div>
          <button type="button" className="btn-secondary px-3 py-1.5 text-sm" onClick={() => navigate('/scenarios')}>
            <ArrowLeft className="h-4 w-4" />
            Back to Chat
          </button>
        </header>
        <EmptyState
          title="No analysis to debug"
          body="Ask a question in the Scenario chat, wait for the answer, then click the bug icon (🐛) to see detailed agent reasoning."
          actionLabel="Go to Scenario Chat"
          onAction={() => navigate('/scenarios')}
        />
      </div>
    );
  }

  // Debug: Log what we have to help troubleshoot
  console.log('Debug report loaded:', {
    hasReport: !!report,
    hasEvidence: !!report?.evidence,
    hasResearch: !!report?.research,
    hasEvents: !!report?.events,
    hasPortfolio: !!report?.portfolio,
    hasConspiracy: !!report?.conspiracy,
    hasDevil: !!report?.devil,
    hasGovernance: !!report?.governance,
    reportKeys: report ? Object.keys(report) : [],
  });

  const agentData = {
    research: report.research,
    event_hunter: report.events,
    portfolio_storyteller: report.portfolio,
    conspiracy_theorist: report.conspiracy,
    devils_advocate: report.devil,
    governance: report.governance,
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Agent Debug View</h1>
          <p className="text-xs text-ink-2">
            Verdict: {report.assessment} · {report.debate_rounds} debate round(s) · {report.failures.length} failure(s)
          </p>
        </div>
        <button type="button" className="btn-secondary px-3 py-1.5 text-sm" onClick={() => navigate('/scenarios')}>
          <ArrowLeft className="h-4 w-4" />
          Back to Chat
        </button>
      </header>

      {/* View tabs */}
      <div role="tablist" className="mb-3 flex gap-2 border-b border-line">
        {[
          { id: 'agents' as const, label: 'Agents', icon: Users },
          { id: 'debate' as const, label: 'Debate', icon: MessageSquare },
          { id: 'evidence' as const, label: 'Evidence', icon: ChevronRight },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={view === id}
            onClick={() => setView(id)}
            className={`focus-ring -mb-px flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-sm transition ${
              view === id ? 'border-brand text-ink' : 'border-transparent text-ink-2 hover:text-ink'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[280px_1fr]">
        {/* Sidebar */}
        {view === 'agents' && (
          <Card dense className="flex min-h-0 flex-col overflow-y-auto">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Agents</h2>
            <div className="space-y-1">
              {AGENTS.map((agent) => {
                const data = agentData[agent.id];
                const selected = selectedAgent === agent.id;
                const status = data?.status || 'skipped';
                const failed = status === 'failed';
                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => setSelectedAgent(agent.id)}
                    className={`focus-ring w-full rounded-lg border px-3 py-2 text-left transition ${
                      selected ? 'border-brand bg-raised' : 'border-line hover:bg-raised'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-ink">{agent.label}</span>
                      <StatusBadge status={status} />
                    </div>
                    <p className="text-xs text-ink-2">{agent.description}</p>
                    {failed && data?.error && <p className="mt-1 text-xs text-caution">Error: {data.error}</p>}
                  </button>
                );
              })}
            </div>
          </Card>
        )}

        {/* Main content */}
        <Card dense className="min-h-0 overflow-y-auto">
          {view === 'agents' && <AgentDetail agent={selectedAgent} data={agentData[selectedAgent]} />}
          {view === 'debate' && <DebateView devil={report.devil} rebuttals={report.rebuttals || []} governance={report.governance} />}
          {view === 'evidence' && <EvidenceView evidence={report.evidence || []} />}
        </Card>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors = {
    ok: 'bg-success/10 text-success',
    partial: 'bg-caution/10 text-caution',
    failed: 'bg-brand/10 text-brand',
    skipped: 'bg-ink-3/10 text-ink-3',
    no_evidence: 'bg-ink-3/10 text-ink-3',
  };
  const color = colors[status as keyof typeof colors] || colors.skipped;
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${color}`}>{status}</span>;
}

function AgentDetail({ agent, data }: { agent: AgentType; data?: AgentOutput }) {
  const agentInfo = AGENTS.find((a) => a.id === agent);

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <p className="text-sm text-ink-2">No data available for {agentInfo?.label}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-1 text-lg font-semibold text-ink">{agentInfo?.label}</h2>
        <div className="flex items-center gap-2">
          <StatusBadge status={data.status} />
          <span className="text-xs text-ink-2">Confidence: {(data.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>

      {data.error && (
        <div className="rounded-lg border border-caution/20 bg-caution/5 p-3">
          <p className="text-xs font-semibold text-caution">Error</p>
          <p className="mt-1 text-xs text-ink">{data.error}</p>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Complete Output</h3>
        <pre className="overflow-x-auto rounded-lg bg-surface p-3 text-[11px] leading-relaxed text-ink">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function DebateView({ devil, rebuttals, governance }: { devil?: AgentOutput; rebuttals: Rebuttal[]; governance?: AgentOutput }) {
  if (!devil || devil.status === 'skipped') {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <p className="text-sm text-ink-2">No debate occurred for this analysis</p>
      </div>
    );
  }

  const challenges = (devil as any).challenged_claims || [];
  const conspiracyReview = (governance as any)?.conspiracy_review || [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-3 text-lg font-semibold text-ink">Debate Flow</h2>
        <p className="text-xs text-ink-2">
          The Devil's Advocate challenges agent conclusions. Agents respond with evidence or concede.
        </p>
      </div>

      {/* Devil's Advocate Challenges */}
      <section>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
          <MessageSquare className="h-4 w-4" />
          Challenges ({challenges.length})
        </h3>
        <div className="space-y-3">
          {challenges.map((challenge: any, i: number) => (
            <div key={i} className="rounded-lg border border-line bg-raised p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold text-ink">Target: {challenge.target}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                    challenge.severity === 'high'
                      ? 'bg-brand/10 text-brand'
                      : challenge.severity === 'medium'
                        ? 'bg-caution/10 text-caution'
                        : 'bg-ink-3/10 text-ink-3'
                  }`}
                >
                  {challenge.severity}
                </span>
              </div>
              <p className="mb-1 text-xs text-ink">
                <span className="font-semibold">Claim:</span> {challenge.claim}
              </p>
              <p className="text-xs text-ink">
                <span className="font-semibold">Objection:</span> {challenge.objection}
              </p>
              {challenge.evidence_ids?.length > 0 && (
                <p className="mt-1 text-[11px] text-ink-3">Evidence: {challenge.evidence_ids.join(', ')}</p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Rebuttals */}
      {rebuttals.length > 0 && (
        <section>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
            <ChevronRight className="h-4 w-4" />
            Rebuttals ({rebuttals.length})
          </h3>
          <div className="space-y-3">
            {rebuttals.map((rebuttal, i) => (
              <div key={i} className="rounded-lg border border-line bg-raised p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink">{rebuttal.agent}</span>
                  {rebuttal.concedes && <span className="text-[10px] font-semibold uppercase text-caution">Concedes</span>}
                </div>
                <p className="mb-1 text-xs text-ink-2">
                  <span className="font-semibold">Objection:</span> {rebuttal.objection}
                </p>
                <p className="mb-1 text-xs text-ink">
                  <span className="font-semibold">Response:</span> {rebuttal.response}
                </p>
                {rebuttal.evidence_ids.length > 0 && (
                  <p className="mt-1 text-[11px] text-ink-3">Evidence cited: {rebuttal.evidence_ids.join(', ')}</p>
                )}
                {rebuttal.missing_evidence && (
                  <p className="mt-1 text-[11px] text-caution">Missing: {rebuttal.missing_evidence}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Conspiracy Theory Review */}
      {conspiracyReview.length > 0 && (
        <section>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
            <ChevronRight className="h-4 w-4" />
            Conspiracy Theory Review ({conspiracyReview.length})
          </h3>
          <div className="space-y-3">
            {conspiracyReview.map((review: any, i: number) => (
              <div key={i} className="rounded-lg border border-line bg-raised p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                      review.verdict === 'rejected' ? 'bg-brand/10 text-brand' : 'bg-caution/10 text-caution'
                    }`}
                  >
                    {review.verdict}
                  </span>
                </div>
                <p className="mb-1 text-xs text-ink">{review.theory}</p>
                <p className="text-xs text-ink-2">
                  <span className="font-semibold">Reason:</span> {review.reason}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Alternative Hypotheses */}
      {(devil as any).alternative_hypotheses?.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">Alternative Hypotheses</h3>
          <ul className="space-y-2">
            {(devil as any).alternative_hypotheses.map((hyp: any, i: number) => (
              <li key={i} className="rounded-lg border border-line bg-raised p-2 text-xs text-ink">
                {hyp.text}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function EvidenceView({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <p className="text-sm text-ink-2">No evidence available</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-1 text-lg font-semibold text-ink">Evidence ({evidence.length})</h2>
        <p className="text-xs text-ink-2">All evidence gathered and validated by the research agent</p>
      </div>

      <div className="space-y-3">
        {evidence.map((item) => (
          <div key={item.id} className="rounded-lg border border-line bg-raised p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-ink">{item.id}</span>
              <div className="flex items-center gap-2">
                <span className="rounded bg-ink-3/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-ink-3">{item.kind}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                    item.validation === 'verified' ? 'bg-success/10 text-success' : 'bg-caution/10 text-caution'
                  }`}
                >
                  {item.validation}
                </span>
              </div>
            </div>
            <p className="mb-1 text-xs font-medium text-ink">{item.claim}</p>
            <p className="mb-2 text-xs text-ink-2">{item.excerpt}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-3">
              <span>Source: {item.source}</span>
              {item.date && <span>Date: {item.date}</span>}
              {item.value !== null && (
                <span>
                  Value: {item.value}
                  {item.unit}
                </span>
              )}
            </div>
            <p className="mt-1 truncate text-[11px] text-ink-3">Ref: {item.reference}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
