// ============================================================
// JobPilot AI — App Shell Layout Wrapper
// ============================================================

import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '../../stores/ui-store';

export function AppShell() {
  const { sidebarCollapsed, sidebarOpen } = useUIStore();

  return (
    <div
      className={`app-shell ${
        sidebarCollapsed ? 'app-shell--collapsed' : ''
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
