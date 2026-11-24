// ============================================================
// JobPilot — App Shell Layout Wrapper & Route Guard
// ============================================================

import { Suspense, useEffect, useRef } from 'react';
import { Outlet, Navigate, useLocation } from 'react-router-dom';
import { Loader2, Menu } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { isDesktopViewport, useUIStore } from '../../stores/ui-store';
import { useAuth } from '../../hooks/use-auth';
import { useAutoScan } from '../../hooks/use-discovery';
import { APP_NAME, ROUTES, NAV_ITEMS } from '../../lib/constants';
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
  const pageName = NAV_ITEMS.find(item=>item.path===pathname)?.label || (pathname.startsWith('/applications/')?'Application workspace':'Workspace');
  const shellRef=useRef<HTMLDivElement>(null);
  const bodyRef=useRef<HTMLDivElement>(null);

  useEffect(()=>{
    if(!sidebarOpen||isDesktopViewport()||!isAuthenticated)return;
    const sidebar=shellRef.current?.querySelector<HTMLElement>('.sidebar');
    const previous=document.activeElement as HTMLElement|null;
    const body=bodyRef.current;
    if(body)body.inert=true;
    sidebar?.setAttribute('role','dialog');
    sidebar?.setAttribute('aria-modal','true');
    const focusable=()=>Array.from(sidebar?.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),[tabindex="0"]')??[]).filter(el=>el.getClientRects().length>0);
    focusable()[0]?.focus();
    const handle=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();setSidebarOpen(false);}
      if(event.key==='Tab'){
        const items=focusable(),first=items[0],last=items[items.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    };
    document.addEventListener('keydown',handle);
    const media=window.matchMedia('(min-width: 1024px)');
    const resize=()=>{if(media.matches)setSidebarOpen(false)};
    media.addEventListener('change',resize);
    return ()=>{document.removeEventListener('keydown',handle);media.removeEventListener('change',resize);if(body)body.inert=false;sidebar?.removeAttribute('role');sidebar?.removeAttribute('aria-modal');if(previous?.isConnected)previous.focus();};
  },[sidebarOpen,isAuthenticated,setSidebarOpen]);

  // On small screens the sidebar is a drawer: close it after navigating.
  useEffect(() => {
    if (!isDesktopViewport()) setSidebarOpen(false);
  }, [pathname, setSidebarOpen]);

  useEffect(()=>{
    const media=window.matchMedia('(min-width: 1024px)');
    const resize=()=>setSidebarOpen(media.matches);
    media.addEventListener('change',resize);
    return ()=>media.removeEventListener('change',resize);
  },[setSidebarOpen]);

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
    <div ref={shellRef} className={cn('app-shell', sidebarOpen && 'app-shell--sidebar-open')}>
      <a className="workspace-skip" href="#workspace-main">Skip to workspace</a>
      <Sidebar />
      <DiscoveryAutoScan />
      {sidebarOpen && <div className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={() => setSidebarOpen(false)} aria-hidden />}
      <div ref={bodyRef} className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3 lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="Open sidebar"
            aria-expanded={sidebarOpen}
          >
            <Menu size={18} />
          </button>
          <span className="text-sm font-semibold">{APP_NAME}</span>
        </div>
        {isChat ? (
          <main id="workspace-main" tabIndex={-1} className="min-h-0 flex-1">
            <Suspense fallback={fallback}>
              <Outlet />
            </Suspense>
          </main>
        ) : (
          <main id="workspace-main" tabIndex={-1} className="workspace-main min-h-0 flex-1 overflow-y-auto">
            <div className="workspace-context"><span>Career Desk</span><span aria-hidden="true">/</span><span>{pageName}</span><span className="workspace-context-note">AI preparation. Your decisions.</span></div>
            <div className="workspace-content @container mx-auto w-full max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
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
