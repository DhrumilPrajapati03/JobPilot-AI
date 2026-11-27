// ============================================================
// JobDots — Sidebar: the expert roster, then the places you supervise from (plan section 6)
// ============================================================
// Roster, not history: each expert with its live avatar and one line of what it is doing.
// The JobPilot pages (copilot chat, job feed, applications…) stay reachable under "More".

import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Bot, Contact, Gauge, Inbox, LayoutList, LogOut, MessagesSquare, Monitor, Moon, Sun, X } from 'lucide-react';
import { NAV_ITEMS, ROUTES } from '../../lib/constants';
import { useAuth } from '../../hooks/use-auth';
import { getThemePreference, setThemePreference, type ThemePreference } from '../../lib/theme';
import { cn } from '@/lib/utils';
import { Brand } from '../ui/brand';
import { useUIStore } from '../../stores/ui-store';
import { ExpertAvatar } from '../experts/ExpertAvatar';
import { usePending, useRoster } from '../../jobdots/api';

const THEME_ICON: Record<ThemePreference, typeof Sun> = { system: Monitor, light: Sun, dark: Moon };
const NEXT_THEME: Record<ThemePreference, ThemePreference> = { system: 'light', light: 'dark', dark: 'system' };

const PLACES = [
  { label: 'Command', path: ROUTES.HOME, icon: Bot },
  { label: 'Cases', path: ROUTES.CASES, icon: LayoutList },
  { label: 'Approvals', path: ROUTES.APPROVALS, icon: Inbox },
  { label: 'Contacts', path: ROUTES.CONTACTS, icon: Contact },
  { label: 'Answer bank', path: ROUTES.ANSWERS, icon: MessagesSquare },
  { label: 'Dashboard', path: ROUTES.DASHBOARD, icon: Gauge },
];

const close = () => useUIStore.getState().setSidebarOpen(false);
const link = ({ isActive }: { isActive: boolean }) =>
  cn('sidebar-link flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm',
     isActive ? 'bg-secondary font-medium text-foreground' : 'text-muted-foreground hover:bg-secondary/70 hover:text-foreground');

export function Sidebar() {
  const { user, signOut } = useAuth();
  const [theme, setTheme] = useState<ThemePreference>(getThemePreference);
  const roster = useRoster();
  const pending = usePending();
  const waiting = (pending.data ?? []).filter(a => a.status === 'reviewed').length;
  const displayName = user?.email?.split('@')[0] || 'You';
  const ThemeIcon = THEME_ICON[theme];
  const experts = (roster.data ?? []).filter(e => e.status !== 'draft');

  const cycleTheme = () => {
    const next = NEXT_THEME[theme];
    setTheme(next);
    setThemePreference(next);
  };

  return (
    <aside className="sidebar" aria-label="Sidebar">
      <div className="sidebar-brand-row"><NavLink to={ROUTES.HOME} className="sidebar-brand" aria-label="JobDots command"><Brand /></NavLink>
        <button type="button" className="sidebar-close lg:hidden" aria-label="Close sidebar" onClick={close}><X size={19} /></button></div>

      <nav className="px-3 pt-1" aria-label="Places">
        <ul>{PLACES.map(p => <li key={p.path}><NavLink to={p.path} end={p.path === ROUTES.HOME} className={link}>
          <p.icon size={15} />{p.label}
          {p.path === ROUTES.APPROVALS && waiting > 0 && <span className="jd-count-pill" aria-label={`${waiting} waiting`}>{waiting}</span>}
        </NavLink></li>)}</ul>
      </nav>

      <nav className="jd-roster min-h-0 overflow-y-auto px-3 py-3" aria-label="Experts">
        <p className="px-2.5 pb-1 text-xs font-medium text-muted-foreground">Your experts</p>
        <ul>{experts.map(e => <li key={e.id}>
          <NavLink to={`/experts/${e.id}`} className={({ isActive }) => cn('jd-roster-row', isActive && 'jd-on')}>
            <ExpertAvatar expert={e.id} name={e.name} state={e.state} step={e.step} approvals={e.approvals} size={26} />
            <span><strong>{e.name}</strong><small>{e.approvals ? `${e.approvals} to approve` : e.state === 'working' ? e.step || 'Working' : e.step || e.role}</small></span>
          </NavLink></li>)}</ul>

        <details className="jd-more">
          <summary className="px-2.5 text-xs font-medium text-muted-foreground">More (JobPilot pages)</summary>
          <ul>{NAV_ITEMS.map(item => <li key={item.path}><NavLink to={item.path} end className={link}><item.icon size={15} />{item.label}</NavLink></li>)}</ul>
        </details>
      </nav>

      {user && (
        <div className="flex items-center gap-2.5 border-t px-4 py-3">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-secondary text-sm font-semibold">{displayName.charAt(0).toUpperCase()}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{displayName}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{user.email}</span>
          </span>
          <button type="button" onClick={cycleTheme} className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                  title={`Theme: ${theme}`} aria-label={`Theme: ${theme}. Switch to ${NEXT_THEME[theme]}`}><ThemeIcon size={15} /></button>
          <button type="button" onClick={signOut} className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
                  title="Sign out" aria-label="Sign out"><LogOut size={15} /></button>
        </div>
      )}
    </aside>
  );
}
