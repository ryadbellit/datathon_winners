import { Link } from 'react-router-dom';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { Card, Eyebrow, PageHeader } from '../../shared/ui';
import { useAppStore } from '../../shared/store';

export function WelcomePage() {
  const profile = useAppStore((s) => s.profile);
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
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-5 py-10">
        <Eyebrow>Investment decision guide</Eyebrow>
        <h1 className="mt-3 text-[32px] font-semibold leading-tight text-ink md:text-[40px]">
          Understand your investing situation before you explore.
        </h1>
        <p className="mt-4 text-[15px] text-ink-2">
          AlphaForge shows an example mix of assets that could fit your profile, explains why each one appears, and tests the mix against hypothetical market events.
        </p>
        <Card className="mt-8">
          <div className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            <p className="text-sm text-ink-2">
              <span className="font-semibold text-ink">Privacy by design.</span> No income, account numbers, or identity documents are needed.
            </p>
          </div>
        </Card>
        <p className="mt-4 text-xs text-ink-3">Simulation only. No real transactions, no real market data and no personalized financial advice.</p>
        <div className="mt-8">
          <Link to="/onboarding" className="btn-primary">
            {profile ? 'Update your profile' : 'Create your investor profile'}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
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
