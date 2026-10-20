// ============================================================
// JobPilot — Sidebar: new chat, chat history, workspace links, account
// ============================================================

import { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { LogOut, Monitor, Moon, PenSquare, Sun, Trash2 } from 'lucide-react';
import { NAV_ITEMS, APP_NAME, ROUTES } from '../../lib/constants';
import { useAuth } from '../../hooks/use-auth';
import { useChatStore, type Thread } from '../../agent/store';
import { getThemePreference, setThemePreference, type ThemePreference } from '../../lib/theme';
import { cn } from '@/lib/utils';

const DAY = 86_400_000;

function groupThreads(threads: Thread[]) {
  const now = Date.now();
  const groups: { label: string; items: Thread[] }[] = [
    { label: 'Today', items: [] },
    { label: 'Previous 7 days', items: [] },
    { label: 'Older', items: [] },
  ];
  threads
    .filter((t) => t.messages.length > 0)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .forEach((t) => {
      const age = now - new Date(t.updatedAt).getTime();
      groups[age < DAY ? 0 : age < 7 * DAY ? 1 : 2].items.push(t);
    });
  return groups.filter((g) => g.items.length);
}

const THEME_ICON: Record<ThemePreference, typeof Sun> = { system: Monitor, light: Sun, dark: Moon };
const NEXT_THEME: Record<ThemePreference, ThemePreference> = { system: 'light', light: 'dark', dark: 'system' };

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const { threads, activeId, streaming, startThread, selectThread, deleteThread } = useChatStore();
  const [theme, setTheme] = useState<ThemePreference>(getThemePreference);
  const displayName = user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email?.split('@')[0] || 'You';
  const onChat = location.pathname.startsWith(ROUTES.CHAT);
  const ThemeIcon = THEME_ICON[theme];

  const newChat = () => {
    startThread();
    navigate(ROUTES.CHAT);
  };

  const cycleTheme = () => {
    const next = NEXT_THEME[theme];
    setTheme(next);
    setThemePreference(next);
  };

  return (
    <aside className="sidebar" aria-label="Sidebar">
      <div className="flex h-12 shrink-0 items-center gap-2 px-4">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-[11px] font-bold text-primary-foreground">JP</span>
        <span className="text-sm font-semibold tracking-tight">{APP_NAME}</span>
      </div>

      <div className="px-3 pt-1">
        <button
          type="button"
          onClick={newChat}
          disabled={streaming}
          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-50"
        >
          <PenSquare size={16} />
          New chat
        </button>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-2" aria-label="Chats">
        {groupThreads(threads).map((group) => (
          <div key={group.label} className="mb-3">
            <p className="px-2.5 pb-1 pt-2 text-[11px] font-medium text-muted-foreground">{group.label}</p>
            <ul>
              {group.items.map((t) => {
                const active = onChat && t.id === activeId;
                return (
                  <li key={t.id} className="group relative">
                    <button
                      type="button"
                      disabled={streaming}
                      onClick={() => {
                        selectThread(t.id);
                        navigate(ROUTES.CHAT);
                      }}
                      className={cn(
                        'block w-full truncate rounded-lg py-1.5 pl-2.5 pr-8 text-left text-sm disabled:opacity-60',
                        active ? 'bg-secondary font-medium' : 'text-muted-foreground hover:bg-secondary/70 hover:text-foreground',
                      )}
                      aria-current={active ? 'page' : undefined}
                    >
                      {t.title}
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteThread(t.id)}
                      disabled={streaming}
                      className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 hover:text-destructive focus:opacity-100 group-hover:opacity-100"
                      aria-label={`Delete chat: ${t.title}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {threads.every((t) => t.messages.length === 0) && (
          <p className="px-2.5 py-2 text-xs text-muted-foreground">Your chats will appear here.</p>
        )}
      </nav>

      <nav className="border-t px-3 py-2" aria-label="Workspace">
        <p className="px-2.5 pb-1 pt-1 text-[11px] font-medium text-muted-foreground">Workspace</p>
        <ul>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm',
                      isActive ? 'bg-secondary font-medium text-foreground' : 'text-muted-foreground hover:bg-secondary/70 hover:text-foreground',
                    )
                  }
                >
                  <Icon size={15} />
                  {item.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {user && (
        <div className="flex items-center gap-2.5 border-t px-4 py-3">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-secondary text-sm font-semibold">
            {displayName.charAt(0).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{displayName}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{user.email}</span>
          </span>
          <button
            type="button"
            onClick={cycleTheme}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title={`Theme: ${theme}`}
            aria-label={`Theme: ${theme}. Switch to ${NEXT_THEME[theme]}`}
          >
            <ThemeIcon size={15} />
          </button>
          <button
            type="button"
            onClick={signOut}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={15} />
          </button>
        </div>
      )}
    </aside>
  );
}
