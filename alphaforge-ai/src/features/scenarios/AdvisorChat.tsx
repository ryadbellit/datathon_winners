import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Bug, CheckCircle2, Loader2, Send, X, XCircle } from 'lucide-react';
import { analyze, type AgentEvent, type AnalysisResult, type Assessment, type Evidence } from '../../api/analyze';
import { answerChat, type ChatContext } from '../../lib/chat';
import { useAppStore } from '../../shared/store';
import { AgentGraph } from './AgentGraph';

const VERDICT: Record<Assessment, string> = {
  supported: 'Supported by the evidence',
  partially_supported: 'Partially supported',
  insufficient_evidence: 'Insufficient evidence',
};

interface Answer {
  question: string;
  text: string;
  report?: AnalysisResult;
  notice?: string;
}

const CHECK_STYLE = {
  ok: { icon: CheckCircle2, className: 'text-success', label: 'passed' },
  warn: { icon: AlertTriangle, className: 'text-caution', label: 'attention' },
  fail: { icon: XCircle, className: 'text-brand', label: 'not respected' },
} as const;

/** Deterministic profile checks computed by the backend (documented thresholds), shown before the agents' text. */
function ProfileChecks({ evidence }: { evidence: Evidence[] }) {
  const checks = evidence.filter((e) => e.kind === 'check' && e.check_status);
  if (checks.length === 0) return null;
  return (
    <div className="mb-2 rounded-lg border border-line bg-surface p-2" aria-label="Profile checks">
      <p className="mb-1 text-[11px] font-semibold text-ink-2">Profile checks</p>
      <ul className="space-y-0.5">
        {checks.map((c) => {
          const style = CHECK_STYLE[c.check_status ?? 'ok'];
          const Icon = style.icon;
          return (
            <li key={c.id} className="flex items-start gap-1.5 text-[11px] text-ink">
              <Icon className={`mt-px h-3.5 w-3.5 shrink-0 ${style.className}`} aria-label={style.label} />
              <span>
                <span className="font-medium">{c.reference}</span>
                <span className="text-ink-2"> · {c.claim.split(' — ').slice(1).join(' — ')}</span>
                <span className="text-ink-3"> [{c.id}]</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Inline Markdown: **bold** and _italic_ / *italic*. Text is rendered as React nodes, never as raw HTML. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|\*[^*]+\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
          <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
        ) : /^(_[^_]+_|\*[^*]+\*)$/.test(part) ? (
          <em key={i}>{part.slice(1, -1)}</em>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

/** Minimal Markdown renderer for backend answers: "#" headings, "- " / "1. " bullets, paragraphs, inline emphasis. */
function Markdown({ text }: { text: string }) {
  const blocks: { kind: 'h' | 'p' | 'ul'; lines: string[] }[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (heading) blocks.push({ kind: 'h', lines: [heading[1]] });
    else if (bullet) {
      const last = blocks[blocks.length - 1];
      if (last?.kind === 'ul') last.lines.push(bullet[1]);
      else blocks.push({ kind: 'ul', lines: [bullet[1]] });
    } else blocks.push({ kind: 'p', lines: [line] });
  }
  return (
    <div className="space-y-1.5 text-xs leading-relaxed text-ink">
      {blocks.map((b, i) =>
        b.kind === 'h' ? (
          <h3 key={i} className="pt-1 font-semibold">
            <Inline text={b.lines[0]} />
          </h3>
        ) : b.kind === 'ul' ? (
          <ul key={i} className="list-disc space-y-0.5 pl-4">
            {b.lines.map((l, j) => (
              <li key={j}>
                <Inline text={l} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Inline text={b.lines[0]} />
          </p>
        ),
      )}
    </div>
  );
}

/**
 * Slim chat bar at the bottom of the scenario card. Questions go to the agent team (/api/analyze/stream), whose
 * progress is drawn live by AgentGraph; if the API is unreachable the local simulated answer is used instead.
 * The answer opens in a box above the bar.
 */
export function AdvisorChat({ ctx }: { ctx: ChatContext | null }) {
  const navigate = useNavigate();
  const profile = useAppStore((s) => s.profile);
  const selectedIds = useAppStore((s) => s.selectedIds);
  const overrides = useAppStore((s) => s.weightOverrides);
  const horizonOverride = useAppStore((s) => s.horizonOverride);
  const suggestedQuestion = useAppStore((s) => s.suggestedQuestion);
  const [input, setInput] = useState(suggestedQuestion);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);

  const ask = async (raw: string) => {
    const question = raw.trim();
    if (!question || loading) return;
    setInput('');
    if (!ctx || !profile) {
      setAnswer({ question, text: 'Select assets in Discover first, so there is a portfolio to talk about.' });
      return;
    }
    setLoading(true);
    setAnswer(null);
    setEvents([]);
    try {
      const report = await analyze(question, profile, selectedIds, overrides, horizonOverride, (event) =>
        setEvents((previous) => [...previous, event]),
      );
      setAnswer({ question, text: report.answer, report });
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'unknown error';
      setAnswer({
        question,
        text: answerChat(question, ctx),
        notice: `Live analysis unavailable (${reason}). Showing a simulated answer.`,
      });
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(input);
  };

  return (
    <section aria-label="Ask about your portfolio" className="relative shrink-0 border-t border-line pt-3">
      {(answer || loading) && (
        <div
          role="status"
          aria-live="polite"
          className="absolute inset-x-0 bottom-full z-20 mb-2 max-h-[60vh] overflow-y-auto rounded-xl border border-line-strong bg-raised p-3 shadow-sm"
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] text-ink-3">
              {loading ? 'The agents are analysing your question…' : `You asked: ${answer?.question}`}
            </p>
            {!loading && (
              <div className="flex items-center gap-1">
                {answer?.report && (
                  <button
                    type="button"
                    onClick={() => {
                      sessionStorage.setItem('debugReport', JSON.stringify(answer.report));
                      navigate('/debug');
                    }}
                    aria-label="View agent details"
                    className="focus-ring -mr-1 -mt-1 rounded p-1 text-brand-hover hover:text-brand"
                    title="View detailed agent reasoning"
                  >
                    <Bug className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setAnswer(null)}
                  aria-label="Close answer"
                  className="focus-ring -mr-1 -mt-1 rounded p-1 text-ink-2 hover:text-ink"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
          {loading && events.length === 0 && <Loader2 className="mt-2 h-4 w-4 animate-spin text-ink-3" aria-hidden="true" />}
          {events.length > 0 && (loading || answer?.report) && <AgentGraph events={events} finished={!loading} />}
          {answer && (
            <div className="mt-1">
              {answer.notice && <p className="mb-1.5 text-[11px] text-ink-3">{answer.notice}</p>}
              {answer.report?.answer_mode === 'general_knowledge' ? (
                <p className="mb-1.5 text-[11px] font-semibold text-ink-2">
                  General knowledge · not verified by sources
                </p>
              ) : answer.report && (
                <p className="mb-1.5 text-[11px] font-semibold text-ink-2">
                  Verdict: {VERDICT[answer.report.assessment]} · {answer.report.debate_rounds} debate round(s)
                  {answer.report.failures.length > 0 && ` · unavailable: ${answer.report.failures.join(', ')}`}
                </p>
              )}
              {answer.report?.evidence && <ProfileChecks evidence={answer.report.evidence} />}
              <Markdown text={answer.text} />
            </div>
          )}
          <p className="mt-1.5 text-[10px] text-ink-3">Simulation only. Not financial advice.</p>
        </div>
      )}

      <form onSubmit={onSubmit} className="mx-auto flex w-full max-w-[640px] items-center gap-2">
        <label htmlFor="advisor-input" className="shrink-0 text-xs font-semibold text-ink">
          Ask
        </label>
        <input
          id="advisor-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Why did NVDA fall and what does it mean for my portfolio? · What is my worst case?"
          className="focus-ring min-w-0 flex-1 rounded-lg border border-line bg-raised px-3 py-1.5 text-xs text-ink placeholder:text-ink-3"
        />
        <button type="submit" disabled={loading} className="btn-primary shrink-0 px-3 py-1.5 text-xs disabled:opacity-60">
          <Send className="h-3.5 w-3.5" aria-hidden="true" />
          Send
        </button>
      </form>
    </section>
  );
}
