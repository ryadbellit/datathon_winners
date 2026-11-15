import { useState, type FormEvent } from 'react';
import { Send, X } from 'lucide-react';
import { answerChat, type ChatContext } from '../../lib/chat';

/**
 * Slim chat bar at the bottom of the scenario card. The answer opens in a box just
 * above the bar, and can be closed. It covers part of the card only while open.
 */
export function AdvisorChat({ ctx }: { ctx: ChatContext | null }) {
  const [input, setInput] = useState('');
  const [answer, setAnswer] = useState<{ question: string; text: string } | null>(null);

  const ask = (raw: string) => {
    const question = raw.trim();
    if (!question) return;
    const text = ctx ? answerChat(question, ctx) : 'Select assets in Discover first, so there is a portfolio to talk about.';
    setAnswer({ question, text });
    setInput('');
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(input);
  };

  return (
    <section aria-label="Ask about your portfolio" className="relative shrink-0 border-t border-line pt-3">
      {answer && (
        <div
          role="status"
          aria-live="polite"
          className="absolute inset-x-0 bottom-full z-20 mb-2 rounded-xl border border-line-strong bg-raised p-3 shadow-sm"
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] text-ink-3">You asked: {answer.question}</p>
            <button
              type="button"
              onClick={() => setAnswer(null)}
              aria-label="Close answer"
              className="focus-ring -mr-1 -mt-1 rounded p-1 text-ink-2 hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="mt-1 text-xs text-ink">{answer.text}</p>
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
          placeholder="What if I save $300 a month for 10 years? · What is my worst case? · What if I invest for 3 years?"
          className="focus-ring min-w-0 flex-1 rounded-lg border border-line bg-raised px-3 py-1.5 text-xs text-ink placeholder:text-ink-3"
        />
        <button type="submit" className="btn-primary shrink-0 px-3 py-1.5 text-xs">
          <Send className="h-3.5 w-3.5" aria-hidden="true" />
          Send
        </button>
      </form>
    </section>
  );
}
