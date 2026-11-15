import { useState } from 'react';
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  Compass,
  FileText,
  FlaskConical,
  GitCompare,
  Info,
  Menu,
  Plus,
  Settings,
  UserRound,
  X,
} from 'lucide-react';
import { useAppStore } from './store';
import { Toasts } from './ui';
import { ViewToggle } from './ViewToggle';

const WORKSPACE = [
  { to: '/', label: 'Discover and Build', icon: Compass, title: 'Discover and Build' },
  { to: '/compare', label: 'Compare Assets', icon: GitCompare, title: 'Compare Assets' },
  { to: '/scenarios', label: 'Scenario Analysis', icon: FlaskConical, title: 'Scenario Analysis' },
  { to: '/reports', label: 'Analysis Reports', icon: FileText, title: 'Analysis Reports' },
];

const ACCOUNT = [
  { to: '/onboarding', label: 'Investor Profile', icon: UserRound, title: 'Investor Profile' },
  { to: '/settings', label: 'Settings', icon: Settings, title: 'Settings' },
];

function pageTitle(pathname: string): { eyebrow: string; title: string } {
  const all = [...WORKSPACE, ...ACCOUNT];
  const hit = all.find((i) => i.to === pathname) ?? all[0];
  return { eyebrow: 'AlphaForge workspace', title: hit.title };
}

export function Layout() {
  const profile = useAppStore((s) => s.profile);
  const selectedCount = useAppStore((s) => s.selectedIds.length);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!profile) return <Navigate to="/welcome" replace />;

  const heading = pageTitle(location.pathname);

  const navItem = (item: (typeof WORKSPACE)[number] | (typeof ACCOUNT)[number]) => {
    const Icon = item.icon;
    const badge = 'badge' in item && item.badge ? selectedCount : 0;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === '/'}
        onClick={() => setMobileOpen(false)}
        className={({ isActive }) =>
          `focus-ring flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition duration-200 ${
            isActive
              ? 'bg-raised text-ink shadow-[inset_3px_0_0_var(--color-brand)]'
              : 'text-ink-2 hover:bg-raised hover:text-ink'
          }`
        }
        aria-label={item.label}
      >
        <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className="hidden flex-1 truncate xl:inline">{item.label}</span>
        {badge > 0 && (
          <span className="ml-auto hidden rounded-full bg-brand px-2 text-xs font-semibold text-white xl:inline" aria-label={`${badge} selected`}>
            {badge}
          </span>
        )}
        {badge > 0 && <span className="sr-only">, {badge} selected</span>}
      </NavLink>
    );
  };

  const sidebar = (
    <nav aria-label="Main" className="flex h-full flex-col gap-6 overflow-hidden p-3 xl:p-5">
      <div className="flex items-center gap-2.5 px-1">
        <Logo />
        <span className="hidden text-base font-semibold text-ink xl:inline">AlphaForge AI</span>
      </div>

      <button
        type="button"
        onClick={() => {
          clearSelection();
          setMobileOpen(false);
          navigate('/');
        }}
        className="btn-outline-brand justify-center xl:justify-start"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        <span className="hidden xl:inline">New discovery</span>
        <span className="sr-only xl:hidden">New discovery</span>
      </button>

      <div>
        <p className="mb-2 hidden px-3 text-xs uppercase tracking-[0.16em] text-ink-3 xl:block">Workspace</p>
        <div className="flex flex-col gap-1">{WORKSPACE.map(navItem)}</div>
      </div>

      <div>
        <p className="mb-2 hidden px-3 text-xs uppercase tracking-[0.16em] text-ink-3 xl:block">Account</p>
        <div className="flex flex-col gap-1">{ACCOUNT.map(navItem)}</div>
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <div className="rounded-xl border border-line bg-raised p-3">
          <div className="flex items-center gap-2 text-sm text-ink">
            <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
            <span className="hidden xl:inline">Agent system online</span>
            <span className="sr-only xl:hidden">Agent system online</span>
          </div>
          <p className="mt-1 hidden text-xs text-ink-3 xl:block">Validation active</p>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-line p-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-raised text-sm font-semibold text-ink">AM</span>
          <div className="hidden min-w-0 xl:block">
            <p className="truncate text-sm font-medium text-ink">Alex Morgan</p>
            <p className="text-xs text-ink-3">Learning profile</p>
          </div>
        </div>

        <div className="hidden rounded-xl border border-line p-3 text-xs text-ink-2 xl:block">
          <p className="flex items-center gap-1.5 font-semibold text-ink">
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
            Simulation only. Not financial advice.
          </p>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-page">
      {/* Desktop and tablet sidebar: full width on wide screens, icons only on tablets. */}
      <aside className="hidden shrink-0 border-r border-line bg-surface md:sticky md:top-0 md:block md:h-screen md:w-20 xl:w-64">
        {sidebar}
      </aside>

      {/* Mobile sidebar as an overlay. */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/60" aria-label="Close menu" onClick={() => setMobileOpen(false)} tabIndex={-1} />
          <aside className="relative h-full w-72 max-w-[85%] border-r border-line bg-surface">{sidebar}</aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-line bg-page/95 px-4 py-3 backdrop-blur md:px-8">
          <button
            type="button"
            className="focus-ring rounded-lg p-2 text-ink-2 hover:text-ink md:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-3">{heading.eyebrow}</p>
            <p className="truncate text-base font-semibold text-ink">{heading.title}</p>
          </div>
          <span className="hidden items-center gap-1.5 rounded-full border border-line px-3 py-1 text-xs text-ink-2 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-model" aria-hidden="true" />
            Historical data
          </span>
          <ViewToggle />
          <button type="button" className="focus-ring relative rounded-full p-2 text-ink-2 hover:text-ink" aria-label="Notifications, 1 unread">
            <Bell className="h-5 w-5" aria-hidden="true" />
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand" aria-hidden="true" />
          </button>
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-raised text-xs font-semibold text-ink" aria-hidden="true">
            AM
          </span>
        </header>

        <main className="mx-auto flex min-h-0 w-full max-w-[1280px] flex-1 flex-col overflow-hidden px-4 py-5 md:px-8">
          <Outlet />
        </main>

      </div>

      <Toasts />
    </div>
  );
}

function Logo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" role="img" aria-label="AlphaForge logo">
      <rect width="32" height="32" rx="8" fill="#16181D" />
      <rect x="7" y="16" width="4" height="9" fill="#E1251B" />
      <rect x="14" y="11" width="4" height="14" fill="#E1251B" />
      <rect x="21" y="6" width="4" height="19" fill="#E1251B" />
    </svg>
  );
}
