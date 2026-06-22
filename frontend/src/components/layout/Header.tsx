// ============================================================
// JobPilot AI — Top Header Bar
// ============================================================

import { useLocation } from 'react-router-dom';
import { useUIStore } from '../../stores/ui-store';
import { Bell, Search, Menu } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/applications': 'Application Tracker',
  '/applications/new': 'New Application',
  '/profile': 'Identity Vault',
  '/templates': 'Templates Library',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
};

export function Header() {
  const location = useLocation();
  const { notificationCount, setSidebarOpen, sidebarOpen } = useUIStore();

  // Resolve page title from path
  const pageTitle =
    PAGE_TITLES[location.pathname] ||
    (location.pathname.startsWith('/applications/') ? 'Application Detail' : 'JobPilot AI');

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="header-menu-btn"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          aria-label="Toggle sidebar"
        >
          <Menu size={20} />
        </button>
        <div className="header-title-section">
          <h1 className="header-title">{pageTitle}</h1>
        </div>
      </div>

      <div className="header-right">
        {/* Search */}
        <div className="header-search">
          <Search size={16} className="header-search-icon" />
          <Input
            type="text"
            placeholder="Search applications..."
            className="header-search-input"
          />
        </div>

        {/* Notifications */}
        <button className="header-notification-btn" aria-label="Notifications">
          <Bell size={20} />
          {notificationCount > 0 && (
            <Badge variant="destructive" className="header-notification-badge">
              {notificationCount}
            </Badge>
          )}
        </button>
      </div>
    </header>
  );
}
