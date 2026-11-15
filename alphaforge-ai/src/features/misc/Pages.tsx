import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck, UserRound } from 'lucide-react';
import { PERSONAS } from '../../data/personas';
import { Card, Eyebrow, PageHeader } from '../../shared/ui';
import { useAppStore } from '../../shared/store';

export function WelcomePage() {
  const profile = useAppStore((s) => s.profile);
  const loadPersona = useAppStore((s) => s.loadPersona);
  const navigate = useNavigate();
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-page">
      <header className="flex items-center justify-between px-5 py-4 md:px-10">
        <span className="text-base font-semibold text-ink">AlphaForge AI</span>
        {profile && (
          <Link to="/" className="text-sm text-ink-2 hover:text-ink">
            Go to your workspace
          </Link>
        )}
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center overflow-y-auto px-5 py-10">
        <Eyebrow>Investment decision guide</Eyebrow>
        <h1 className="mt-3 text-[32px] font-semibold leading-tight text-ink md:text-[40px]">
          Understand your investing situation before you explore.
        </h1>
        <p className="mt-4 text-[15px] text-ink-2">
          AlphaForge shows an example mix of assets that could fit your profile, explains why each one appears, and tests the mix against real past market episodes such as 2022.
        </p>
        <Card className="mt-8">
          <div className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            <p className="text-sm text-ink-2">
              <span className="font-semibold text-ink">Privacy by design.</span> No income, account numbers, or identity documents are needed.
            </p>
          </div>
        </Card>
        <p className="mt-4 text-xs text-ink-3">Simulation only. Historical public market data, no real transactions and no personalized financial advice.</p>
        <div className="mt-8">
          <Link to="/onboarding" className="btn-primary">
            {profile ? 'Update your profile' : 'Create your investor profile'}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
        <section aria-label="Reference personas" className="mt-8">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-3">Or try a reference persona</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {PERSONAS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  loadPersona(p);
                  navigate('/scenarios');
                }}
                className="focus-ring rounded-xl border border-line bg-raised p-3 text-left transition hover:border-line-strong"
              >
                <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  <UserRound className="h-4 w-4 text-ink-3" aria-hidden="true" />
                  {p.name}
                </span>
                <span className="mt-1 block text-xs text-ink-2">{p.summary}</span>
                <span className="mt-1.5 block text-[11px] text-ink-3">Tests: {p.tests}</span>
              </button>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

export function ComingSoonPage({ title, text }: { title: string; text: string }) {
  return (
    <>
      <PageHeader eyebrow="Coming soon" title={title} subtitle={text} />
      <Card>
        <p className="text-sm text-ink-2">This section is a placeholder in the prototype. The other screens are fully working.</p>
      </Card>
    </>
  );
}
