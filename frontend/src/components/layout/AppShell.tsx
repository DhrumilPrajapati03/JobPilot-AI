// ============================================================
// JobPilot AI — App Shell Layout Wrapper & Route Guard
// ============================================================

import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '../../stores/ui-store';
import { useAuth } from '../../hooks/use-auth';
import { ROUTES } from '../../lib/constants';
import { Loader2 } from 'lucide-react';

export function AppShell() {
  const { sidebarCollapsed, sidebarOpen } = useUIStore();
  const { isAuthenticated, loading } = useAuth();

  // 1. If we are still checking local storage for a token, show a loading spinner
  if (loading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-content">
          <Loader2 size={48} className="animate-spin text-primary" />
          <p>Verifying credentials...</p>
        </div>
      </div>
    );
  }

  // 2. If session verification completes and the user is NOT authenticated,
  // redirect them to the login screen.
  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} replace />;
  }

  // 3. Otherwise, render the main layout and dashboard contents (Outlet)
  return (
    <div
      className={`app-shell ${sidebarCollapsed ? 'app-shell--collapsed' : ''
        } ${!sidebarOpen ? 'app-shell--sidebar-hidden' : ''}`}
    >
      <Sidebar />
      <div className="app-main">
        <Header />
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
