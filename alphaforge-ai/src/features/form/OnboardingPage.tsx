import { useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, Lock, Sparkles, TrendingDown, Info } from 'lucide-react';
import { useAppStore } from '../../shared/store';
import { Callout, Chip, HelpTip, ProgressBar, RadioCard } from '../../shared/ui';
import { DEFAULT_SELECTION } from '../../data/assets';
import {
  ASSET_INTERESTS,
  COMFORTS,
  ESG_OPTIONS,
  HORIZONS,
  KNOWLEDGE,
  OBJECTIVES,
  REGIONS,
  SECTORS,
} from '../../data/options';
import type { AssetInterest, Comfort, EsgPref, Horizon, Knowledge, Objective, Profile } from '../../data/types';
import { discoverAssets } from '../../lib/engine';

type Draft = Partial<Profile>;

const STEPS = ['Goals', 'Risk comfort', 'Preferences', 'Experience', 'Summary'];

function toggle<T>(list: T[] | undefined, value: T): T[] {
  const current = list ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

/** Returns the id of the first missing answer for a step, or null when the step is complete. */
function missingFor(step: number, d: Draft): string | null {
  if (step === 0) {
    if (!d.objective) return 'objective';
    if (!d.horizon) return 'horizon';
  }
  if (step === 1 && !d.comfort) return 'comfort';
  if (step === 2 && (!d.assetTypes || d.assetTypes.length === 0)) return 'assetTypes';
  if (step === 3 && !d.knowledge) return 'knowledge';
  return null;
}

const MISSING_MESSAGE: Record<string, string> = {
  objective: 'Choose the objective that fits you best.',
  horizon: 'Choose how long you plan to invest.',
  comfort: 'Choose the statement closest to how you feel about change.',
  assetTypes: 'Select at least one asset type to continue.',
  knowledge: 'Choose your knowledge level.',
};

function labelOf<T extends string>(opts: { value: T; label: string }[], v: T | undefined): string {
  return opts.find((o) => o.value === v)?.label ?? '';
}

function summarySentences(d: Draft): { first: string; second: string } {
  const objective = OBJECTIVES.find((o) => o.value === d.objective);
  const horizon = HORIZONS.find((h) => h.value === d.horizon);
  const comfort = COMFORTS.find((c) => c.value === d.comfort);
  const assets = (d.assetTypes ?? [])
    .filter((a) => a !== 'other')
    .map((a) => ASSET_INTERESTS.find((o) => o.value === a)?.label ?? '')
    .filter(Boolean);
  const assetText = assets.length ? assets.join(', ') : 'Other assets';
  return {
    first: objective && horizon ? `You're seeking ${objective.phrase} over the ${horizon.phrase}.` : '',
    second: comfort ? `${comfort.phrase}, while valuing diversification across ${assetText}.` : '',
  };
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const existing = useAppStore((s) => s.profile);
  const saveProfile = useAppStore((s) => s.saveProfile);

  const [draft, setDraft] = useState<Draft>(() => (existing ? { ...existing } : {}));
  const [step, setStep] = useState(0);
  const [showError, setShowError] = useState(false);
  const [returnToSummary, setReturnToSummary] = useState(false);

  const missing = missingFor(step, draft);
  const progress = ((step + 1) / STEPS.length) * 100;

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setShowError(false);
  };

  const next = () => {
    if (missing) {
      setShowError(true);
      return;
    }
    setShowError(false);
    if (returnToSummary) {
      setReturnToSummary(false);
      setStep(4);
      return;
    }
    setStep((s) => Math.min(4, s + 1));
  };

  const back = () => {
    setShowError(false);
    setReturnToSummary(false);
    setStep((s) => Math.max(0, s - 1));
  };

  const editFrom = (target: number) => {
    setShowError(false);
    setReturnToSummary(true);
    setStep(target);
  };

  const finish = () => {
    const profile: Profile = {
      objective: draft.objective as Objective,
      horizon: draft.horizon as Horizon,
      comfort: draft.comfort as Comfort,
      assetTypes: (draft.assetTypes ?? []) as AssetInterest[],
      sectors: draft.sectors ?? [],
      regions: draft.regions ?? [],
      esg: (draft.esg ?? 'none') as EsgPref,
      exclusions: draft.exclusions ?? '',
      knowledge: draft.knowledge as Knowledge,
    };
    // The prototype ships with four starting assets; keep only those the profile allows.
    const allowed = new Set(discoverAssets(profile).map((a) => a.ticker));
    const initial = DEFAULT_SELECTION.filter((t) => allowed.has(t));
    saveProfile(profile, initial);
    navigate('/');
  };

  const sentences = useMemo(() => summarySentences(draft), [draft]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-page">
      <header className="flex shrink-0 items-center justify-between border-b border-line px-5 py-3 md:px-10">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="text-base font-semibold text-ink">AlphaForge AI</span>
        </div>
        <Link to="/welcome" className="focus-ring inline-flex items-center gap-1.5 rounded-lg text-sm text-ink-2 hover:text-ink">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to welcome
        </Link>
      </header>

      <div className="mx-auto grid min-h-0 w-full max-w-[1120px] flex-1 gap-8 overflow-hidden px-5 py-6 md:px-10 lg:grid-cols-[360px_1fr]">
        {/* Left column: framing, stepper, privacy. */}
        <aside>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-3">Create your investor profile</p>
          <h1 className="mt-3 text-[32px] font-semibold leading-tight text-ink">Let's make the analysis relevant to you.</h1>
          <p className="mt-3 text-sm text-ink-2">Your knowledge level and comfort with risk are considered separately.</p>

          {/* Full stepper on wide screens, compact progress on small screens. */}
          <ol className="mt-8 hidden flex-col gap-5 lg:flex" aria-label="Form steps">
            {STEPS.map((label, i) => {
              const done = i < step;
              const current = i === step;
              return (
                <li key={label} className="flex items-center gap-3" aria-current={current ? 'step' : undefined}>
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                      done
                        ? 'border-success bg-success text-page'
                        : current
                          ? 'border-brand bg-brand text-white'
                          : 'border-line-strong text-ink-3'
                    }`}
                    aria-hidden="true"
                  >
                    {done ? <Check className="h-4 w-4" /> : i + 1}
                  </span>
                  <span className={`text-sm ${current ? 'font-semibold text-ink' : done ? 'text-ink' : 'text-ink-3'}`}>
                    {label}
                    {done && <span className="sr-only"> (completed)</span>}
                  </span>
                </li>
              );
            })}
          </ol>

          <div className="mt-10 rounded-2xl border border-line bg-surface p-5">
            <div className="flex gap-3">
              <Lock className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
              <div className="text-sm text-ink-2">
                <p className="font-semibold text-ink">Privacy by design.</p>
                <p>No income, account numbers, or identity documents are needed.</p>
              </div>
            </div>
          </div>
        </aside>

        {/* Right column: progress, step content, footer. */}
        <section className="flex min-h-0 min-w-0 flex-col">
          <div className="mb-8">
            <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.16em] text-ink-3">
              <span>
                Step {step + 1} of {STEPS.length}
              </span>
              <span>{Math.round(progress)}%</span>
            </div>
            <ProgressBar value={progress} label="Profile progress" />
            <p className="mt-3 text-sm text-ink-2 lg:hidden">{STEPS[step]}</p>
          </div>

          <div key={step} className="step-enter min-h-0 flex-1 overflow-hidden">
            {step === 0 && <GoalsStep draft={draft} update={update} showError={showError} />}
            {step === 1 && <ComfortStep draft={draft} update={update} showError={showError} />}
            {step === 2 && <PreferencesStep draft={draft} update={update} showError={showError} />}
            {step === 3 && <ExperienceStep draft={draft} update={update} showError={showError} />}
            {step === 4 && (
              <SummaryStep
                draft={draft}
                sentences={sentences}
                onEdit={editFrom}
                onFinish={finish}
              />
            )}
          </div>

          {step < 4 && (
            <footer className="mt-10 flex items-center justify-between gap-4 border-t border-line pt-6">
              <button type="button" className="btn-secondary" onClick={back} disabled={step === 0}>
                Back
              </button>
              <button type="button" className="btn-primary" onClick={next}>
                Continue
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </button>
            </footer>
          )}
          {step === 4 && (
            <footer className="mt-10 flex items-center justify-between gap-4 border-t border-line pt-6">
              <button type="button" className="btn-secondary" onClick={back}>
                Back
              </button>
            </footer>
          )}
        </section>
      </div>
    </div>
  );
}

/* ---------- Steps ---------- */

interface StepProps {
  draft: Draft;
  update: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
  showError: boolean;
}

function StepHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-[22px] font-semibold text-ink">{title}</h2>
      <p className="mt-1 text-sm text-ink-2">{subtitle}</p>
    </div>
  );
}

function InlineError({ id, show, field }: { id: string; show: boolean; field: string }) {
  if (!show || !MISSING_MESSAGE[field]) return null;
  return (
    <p id={id} role="alert" className="mt-3 text-sm text-caution">
      {MISSING_MESSAGE[field]}
    </p>
  );
}

function Question({ label, children, help }: { label: string; children: ReactNode; help?: string }) {
  return (
    <fieldset className="mb-8">
      <legend className="mb-3 flex items-center gap-2 text-[15px] font-medium text-ink">
        {label}
        {help && <HelpTip text={help} />}
      </legend>
      {children}
    </fieldset>
  );
}

function GoalsStep({ draft, update, showError }: StepProps) {
  return (
    <>
      <StepHeading title="Your goals" subtitle="Start with what you want your investments to do." />
      <Question label="What is your main objective?">
        <div role="radiogroup" aria-label="Main objective" className="grid gap-3 sm:grid-cols-2">
          {OBJECTIVES.map((o) => (
            <RadioCard
              key={o.value}
              name="objective"
              checked={draft.objective === o.value}
              onSelect={() => update('objective', o.value)}
              title={o.label}
              description={o.description}
            />
          ))}
        </div>
        <InlineError id="err-objective" show={showError} field="objective" />
      </Question>
      <Question
        label="What is your investment horizon?"
        help="The time you expect to keep your money invested. Longer horizons can absorb more short-term movement."
      >
        <div role="radiogroup" aria-label="Investment horizon" className="grid gap-3 sm:grid-cols-3">
          {HORIZONS.map((h) => (
            <RadioCard
              key={h.value}
              name="horizon"
              checked={draft.horizon === h.value}
              onSelect={() => update('horizon', h.value)}
              title={h.label}
              description={h.description}
            />
          ))}
        </div>
        <InlineError id="err-horizon" show={showError} field="horizon" />
      </Question>
    </>
  );
}

function ComfortStep({ draft, update, showError }: StepProps) {
  return (
    <>
      <StepHeading title="Comfort with change" subtitle="There is no right answer. Choose what feels realistic." />
      <div className="mb-6">
        <Callout tone="info">Higher potential returns generally involve more risk. Taking more risk does not guarantee a better result.</Callout>
      </div>
      <Question label="Which statement describes you best?">
        <div role="radiogroup" aria-label="Comfort with change" className="flex flex-col gap-3">
          {COMFORTS.map((c) => (
            <RadioCard
              key={c.value}
              name="comfort"
              checked={draft.comfort === c.value}
              onSelect={() => update('comfort', c.value)}
              title={c.label}
              description={c.description}
            />
          ))}
        </div>
        <InlineError id="err-comfort" show={showError} field="comfort" />
      </Question>
      <Callout tone="caution" title="Imagine a hypothetical portfolio falls 15% over several months." icon={<TrendingDown className="h-5 w-5 shrink-0 text-caution" aria-hidden="true" />}>
        Your answer should reflect how you would feel, not what you think an expert would choose.
      </Callout>
    </>
  );
}

function PreferencesStep({ draft, update, showError }: StepProps) {
  const assetTypes = draft.assetTypes ?? [];
  const sectors = draft.sectors ?? [];
  const regions = draft.regions ?? [];
  return (
    <>
      <StepHeading title="Investment interests" subtitle="Select the areas you want AlphaForge to explore." />
      <Question label="Which asset types interest you?">
        <div className="flex flex-wrap gap-2.5" role="group" aria-label="Asset types">
          {ASSET_INTERESTS.map((a) => (
            <Chip key={a.value} selected={assetTypes.includes(a.value)} onToggle={() => update('assetTypes', toggle(assetTypes, a.value))}>
              {a.label}
            </Chip>
          ))}
        </div>
        <InlineError id="err-assets" show={showError} field="assetTypes" />
      </Question>
      <Question label="Preferred sectors">
        <div className="flex flex-wrap gap-2.5" role="group" aria-label="Preferred sectors">
          {SECTORS.map((s) => (
            <Chip key={s} selected={sectors.includes(s)} onToggle={() => update('sectors', toggle(sectors, s))}>
              {s}
            </Chip>
          ))}
        </div>
      </Question>
      <Question label="Preferred regions">
        <div className="flex flex-wrap gap-2.5" role="group" aria-label="Preferred regions">
          {REGIONS.map((r) => (
            <Chip key={r} selected={regions.includes(r)} onToggle={() => update('regions', toggle(regions, r))}>
              {r}
            </Chip>
          ))}
        </div>
      </Question>
      <Question label="ESG preferences">
        <label className="sr-only" htmlFor="esg">
          ESG preferences
        </label>
        <select
          id="esg"
          value={draft.esg ?? 'none'}
          onChange={(e) => update('esg', e.target.value as EsgPref)}
          className="focus-ring w-full max-w-md rounded-xl border border-line bg-surface px-4 py-3 text-[15px] text-ink"
        >
          {ESG_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs text-ink-3">No ESG scores are included in this prototype.</p>
      </Question>
      <Question label="Anything to exclude?">
        <input
          id="exclusions"
          type="text"
          value={draft.exclusions ?? ''}
          onChange={(e) => update('exclusions', e.target.value)}
          placeholder="None"
          aria-describedby="exclusions-hint"
          className="focus-ring w-full max-w-md rounded-xl border border-line bg-surface px-4 py-3 text-[15px] text-ink placeholder:text-ink-3"
        />
        <p id="exclusions-hint" className="mt-2 text-xs text-ink-3">
          For example: Fossil fuels, tobacco
        </p>
      </Question>
    </>
  );
}

function ExperienceStep({ draft, update, showError }: StepProps) {
  return (
    <>
      <StepHeading title="Knowledge level" subtitle="This changes how concepts are explained, not how much risk you can take." />
      <div role="radiogroup" aria-label="Knowledge level" className="grid gap-3">
        {KNOWLEDGE.map((k) => (
          <RadioCard
            key={k.value}
            name="knowledge"
            checked={draft.knowledge === k.value}
            onSelect={() => update('knowledge', k.value)}
            title={k.label}
            description={k.description}
          />
        ))}
      </div>
      <InlineError id="err-knowledge" show={showError} field="knowledge" />
      <p className="mt-6 flex items-start gap-2 text-xs text-ink-3">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Guided explains concepts in plain language. Advanced shows numbers such as volatility.
      </p>
    </>
  );
}

function SummaryStep({
  draft,
  sentences,
  onEdit,
  onFinish,
}: {
  draft: Draft;
  sentences: { first: string; second: string };
  onEdit: (step: number) => void;
  onFinish: () => void;
}) {
  const rows: { label: string; value: string; step: number }[] = [
    { label: 'Main objective', value: labelOf(OBJECTIVES, draft.objective), step: 0 },
    { label: 'Time horizon', value: labelOf(HORIZONS, draft.horizon), step: 0 },
    { label: 'Risk preference', value: labelOf(COMFORTS, draft.comfort), step: 1 },
    {
      label: 'Asset interests',
      value: (draft.assetTypes ?? []).map((a) => labelOf(ASSET_INTERESTS, a)).join(', '),
      step: 2,
    },
    { label: 'Regions', value: (draft.regions ?? []).join(', '), step: 2 },
    { label: 'Knowledge level', value: labelOf(KNOWLEDGE, draft.knowledge), step: 3 },
  ];
  if ((draft.sectors ?? []).length) rows.push({ label: 'Sectors', value: (draft.sectors ?? []).join(', '), step: 2 });
  if (draft.esg && draft.esg !== 'none') rows.push({ label: 'ESG', value: labelOf(ESG_OPTIONS, draft.esg), step: 2 });
  if (draft.exclusions && draft.exclusions.trim()) rows.push({ label: 'Exclusions', value: draft.exclusions, step: 2 });

  return (
    <>
      <StepHeading title="Your profile summary" subtitle="Review the context AlphaForge will use for discovery." />

      <div className="mb-6 flex gap-3 rounded-2xl border border-brand/40 bg-raised p-5">
        <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
        <p className="text-[15px] text-ink">
          {sentences.first} <span className="text-ink-2">{sentences.second}</span>
        </p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-line">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Your answers. Use Edit to change a row.</caption>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-b border-line last:border-0">
                <th scope="row" className="w-1/3 px-4 py-3 font-medium text-ink-2">
                  {r.label}
                </th>
                <td className="px-4 py-3 text-ink">{r.value || 'Not set'}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" onClick={() => onEdit(r.step)} className="focus-ring rounded text-sm text-brand-hover hover:underline">
                    Edit<span className="sr-only"> {r.label}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 flex items-start gap-2 text-sm text-ink-2">
        <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        This profile guides educational analysis. It is not a suitability assessment or financial advice.
      </p>

      <div className="mt-8 flex justify-end">
        <button type="button" className="btn-primary" onClick={onFinish} disabled={!draft.knowledge}>
          Discover Opportunities
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </>
  );
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" role="img" aria-label="AlphaForge logo">
      <rect width="32" height="32" rx="8" fill="#16181D" />
      <rect x="7" y="16" width="4" height="9" fill="#E1251B" />
      <rect x="14" y="11" width="4" height="14" fill="#E1251B" />
      <rect x="21" y="6" width="4" height="19" fill="#E1251B" />
    </svg>
  );
}
