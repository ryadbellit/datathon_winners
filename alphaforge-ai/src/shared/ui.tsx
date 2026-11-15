import { useEffect, useId, useRef, type ReactNode } from 'react';
import { AlertTriangle, Check, CheckCircle2, Info, X } from 'lucide-react';
import { provenance, type ProvenanceKind } from './tokens';
import { useAppStore } from './store';

export function Card({
  className = '',
  children,
  dense = false,
}: {
  className?: string;
  children: ReactNode;
  /** Tighter padding for dashboard panels that must fit on one screen. */
  dense?: boolean;
}) {
  return (
    <section className={`rounded-2xl border border-line bg-surface ${dense ? 'p-4' : 'p-6'} ${className}`}>
      {children}
    </section>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-3">{children}</p>;
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  right,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="mt-2 text-[32px] font-semibold leading-tight text-ink md:text-[36px]">{title}</h1>
        {subtitle && <p className="mt-2 text-[15px] text-ink-2">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

/** Colored dot plus text label. Colour is never the only signal. */
export function ProvenanceTag({ kind }: { kind: ProvenanceKind }) {
  const p = provenance[kind];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs text-ink-2">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color }} aria-hidden="true" />
      {p.label}
    </span>
  );
}

export function Callout({
  tone = 'info',
  title,
  children,
  icon,
}: {
  tone?: 'info' | 'caution' | 'success';
  title?: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  const styles = {
    info: 'border-[#6C8CBF]/40 bg-[#6C8CBF]/10',
    caution: 'border-caution/40 bg-caution/10',
    success: 'border-success/40 bg-success/10',
  }[tone];
  const defaultIcon = {
    info: <Info className="h-5 w-5 shrink-0 text-data-slate" aria-hidden="true" />,
    caution: <AlertTriangle className="h-5 w-5 shrink-0 text-caution" aria-hidden="true" />,
    success: <CheckCircle2 className="h-5 w-5 shrink-0 text-success" aria-hidden="true" />,
  }[tone];
  return (
    <div className={`flex gap-3 rounded-xl border p-4 ${styles}`} role={tone === 'caution' ? 'note' : undefined}>
      {icon ?? defaultIcon}
      <div className="text-sm text-ink-2">
        {title && <p className="font-semibold text-ink">{title}</p>}
        {children}
      </div>
    </div>
  );
}

/** Radio card with a check icon. Uses radio group semantics. */
export function RadioCard({
  checked,
  onSelect,
  title,
  description,
  name,
}: {
  checked: boolean;
  onSelect: () => void;
  title: string;
  description?: string;
  name: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      data-name={name}
      onClick={onSelect}
      className={`focus-ring flex w-full items-start gap-3 rounded-xl border p-4 text-left transition duration-200 hover:bg-raised ${
        checked ? 'border-brand bg-raised' : 'border-line bg-surface'
      }`}
    >
      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
          checked ? 'border-brand bg-brand text-white' : 'border-line-strong text-transparent'
        }`}
        aria-hidden="true"
      >
        <Check className="h-3 w-3" />
      </span>
      <span>
        <span className="block text-[15px] font-medium text-ink">{title}</span>
        {description && <span className="mt-1 block text-sm text-ink-2">{description}</span>}
      </span>
    </button>
  );
}

export function Chip({
  selected,
  onToggle,
  children,
}: {
  selected: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      onClick={onToggle}
      className={`focus-ring inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition duration-200 ${
        selected ? 'border-brand bg-raised text-ink' : 'border-line text-ink-2 hover:text-ink'
      }`}
    >
      {selected && <Check className="h-3.5 w-3.5 text-brand" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const v = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v)}
      className="h-1 w-full overflow-hidden rounded-full bg-line"
    >
      <div className="h-full bg-brand transition-[width] duration-300" style={{ width: `${v}%` }} />
    </div>
  );
}

export function SegmentedToggle<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-line bg-surface p-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`focus-ring rounded-full px-3.5 py-1.5 text-sm font-medium transition duration-200 ${
              on ? 'bg-brand text-white' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Small help icon with a tooltip shown on hover and keyboard focus. */
export function HelpTip({ text }: { text: string }) {
  const id = useId();
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-describedby={id}
        aria-label="More information"
        className="focus-ring inline-flex h-5 w-5 items-center justify-center rounded-full text-ink-3 hover:text-ink"
      >
        <Info className="h-4 w-4" aria-hidden="true" />
      </button>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded-lg border border-line-strong bg-raised p-3 text-left text-xs text-ink-2 opacity-0 shadow-sm transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

/** Right-side drawer. Works as a dialog: Escape closes, focus moves inside on open. */
export function Drawer({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    panelRef.current?.querySelector<HTMLElement>('button')?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close drawer"
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative flex h-full w-full flex-col overflow-y-auto border-l border-line bg-surface p-6 shadow-sm ${
          wide ? 'max-w-2xl' : 'max-w-md'
        }`}
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-xl font-semibold text-ink">
            {title}
          </h2>
          <button type="button" onClick={onClose} className="focus-ring rounded-lg p-1 text-ink-2 hover:text-ink" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-line-strong p-8">
      <p className="text-lg font-semibold text-ink">{title}</p>
      <p className="max-w-lg text-sm text-ink-2">{body}</p>
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} className="btn-primary mt-2">
          {actionLabel}
        </button>
      )}
    </div>
  );
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-raised ${className}`} aria-hidden="true" />;
}

export function Toasts() {
  const toast = useAppStore((s) => s.toast);
  const dismiss = useAppStore((s) => s.dismissToast);
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(dismiss, 2800);
    return () => window.clearTimeout(t);
  }, [toast, dismiss]);
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-xl border border-line-strong bg-raised px-4 py-3 text-sm text-ink shadow-sm">
      {toast.message}
    </div>
  );
}

/** Shared disclaimer shown under charts and scenario results. */
export function Disclaimer({ children }: { children: ReactNode }) {
  return <p className="mt-4 text-xs text-ink-3">{children}</p>;
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'caution' }) {
  const cls = {
    neutral: 'border-line-strong text-ink-2',
    success: 'border-success/50 text-success',
    caution: 'border-caution/60 text-caution',
  }[tone];
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}
