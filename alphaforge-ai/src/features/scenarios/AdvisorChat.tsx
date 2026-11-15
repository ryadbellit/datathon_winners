import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Send, X, Bug } from 'lucide-react';
import { analyze, type AnalysisResult, type Assessment } from '../../api/analyze';
import { answerChat, type ChatContext } from '../../lib/chat';
import { useAppStore } from '../../shared/store';

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

/** The backend answer is Markdown with "## " section headings. */
function Sections({ text }: { text: string }) {
  const blocks = text.split(/^## /m).filter((b) => b.trim());
  return (
    <div className="space-y-2">
      {blocks.map((block, i) => {
        const [title, ...body] = block.split('\n');
        return (
          <div key={i}>
            <h3 className="text-xs font-semibold text-ink">{title}</h3>
            <p className="whitespace-pre-line text-xs text-ink">{body.join('\n').trim()}</p>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Slim chat bar at the bottom of the scenario card. Questions go to the 5-agent backend (/api/analyze);
 * if it is unreachable the local simulated answer is used instead. The answer opens in a box above the bar.
 */
export function AdvisorChat({ ctx }: { ctx: ChatContext | null }) {
  const navigate = useNavigate();
  const profile = useAppStore((s) => s.profile);
  const selectedIds = useAppStore((s) => s.selectedIds);
  const overrides = useAppStore((s) => s.weightOverrides);
  const horizonOverride = useAppStore((s) => s.horizonOverride);
  const [input, setInput] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);

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
    try {
      const report = await analyze(question, profile, selectedIds, overrides, horizonOverride);
      console.log('Analysis complete, report has agent data:', {
        hasResearch: !!report.research,
        hasEvents: !!report.events,
        hasPortfolio: !!report.portfolio,
        hasConspiracy: !!report.conspiracy,
        hasDevil: !!report.devil,
        hasGovernance: !!report.governance,
        reportKeys: Object.keys(report),
      });
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
          {loading && <Loader2 className="mt-2 h-4 w-4 animate-spin text-ink-3" aria-hidden="true" />}
          {answer && (
            <div className="mt-1">
              {answer.notice && <p className="mb-1.5 text-[11px] text-ink-3">{answer.notice}</p>}
              {answer.report && (
                <p className="mb-1.5 text-[11px] font-semibold text-ink-2">
                  Verdict: {VERDICT[answer.report.assessment]} · {answer.report.debate_rounds} debate round(s)
                  {answer.report.failures.length > 0 && ` · unavailable: ${answer.report.failures.join(', ')}`}
                </p>
              )}
              {answer.report ? <Sections text={answer.text} /> : <p className="text-xs text-ink">{answer.text}</p>}
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
