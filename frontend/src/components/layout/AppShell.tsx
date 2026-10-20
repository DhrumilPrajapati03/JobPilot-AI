// ============================================================
// JobPilot — App Shell Layout Wrapper & Route Guard
// ============================================================

import { Suspense, useEffect } from 'react';
import { Outlet, Navigate, useLocation } from 'react-router-dom';
import { Loader2, Menu } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { isDesktopViewport, useUIStore } from '../../stores/ui-store';
import { useAuth } from '../../hooks/use-auth';
import { useAutoScan } from '../../hooks/use-discovery';
import { APP_NAME, ROUTES } from '../../lib/constants';
import { cn } from '@/lib/utils';

/** Keeps the job feed fresh: scans followed boards on open when the last scan is stale. */
function DiscoveryAutoScan() {
  useAutoScan();
  return null;
}

export function AppShell() {
  const { sidebarOpen, setSidebarOpen } = useUIStore();
  const { isAuthenticated, loading } = useAuth();
  const { pathname } = useLocation();
  const isChat = pathname.startsWith(ROUTES.CHAT);

  // On small screens the sidebar is a drawer: close it after navigating.
  useEffect(() => {
    if (!isDesktopViewport()) setSidebarOpen(false);
  }, [pathname, setSidebarOpen]);

  if (loading) {
    return (
      <div className="auth-loading-screen">
        <Loader2 size={28} className="animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} replace />;
  }

  const fallback = (
    <div className="flex h-[40vh] items-center justify-center">
      <Loader2 size={20} className="animate-spin text-muted-foreground" />
    </div>
  );

  return (
    <div className={cn('app-shell', sidebarOpen && 'app-shell--sidebar-open')}>
      <Sidebar />
      <DiscoveryAutoScan />
      {sidebarOpen && <div className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={() => setSidebarOpen(false)} aria-hidden />}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3 lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
          <span className="text-sm font-semibold">{APP_NAME}</span>
        </div>
        {isChat ? (
          <main className="min-h-0 flex-1">
            <Suspense fallback={fallback}>
              <Outlet />
            </Suspense>
          </main>
        ) : (
          <main className="min-h-0 flex-1 overflow-y-auto">
            <div className="@container mx-auto w-full max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
              <Suspense fallback={fallback}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        )}
      </div>
    </div>
  );
}
