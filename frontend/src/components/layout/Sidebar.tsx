// ============================================================
// JobPilot AI — Sidebar Navigation
// ============================================================

import { NavLink, useLocation } from 'react-router-dom';
import { NAV_ITEMS, APP_NAME } from '../../lib/constants';
import { useUIStore } from '../../stores/ui-store';
import { Rocket, ChevronLeft, ChevronRight, LogOut } from 'lucide-react';
import { useAuth } from '../../hooks/use-auth';

export function Sidebar() {
  const location = useLocation();
  const { sidebarCollapsed, setSidebarCollapsed } = useUIStore();
  const { user, signOut } = useAuth();

  return (
    <aside className={`sidebar ${sidebarCollapsed ? 'sidebar--collapsed' : ''}`}>
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <Rocket size={22} />
          </div>
          {!sidebarCollapsed && <span className="sidebar-logo-text">{APP_NAME}</span>}
        </div>
        <button
          className="sidebar-collapse-btn"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <ul className="sidebar-nav-list">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path ||
              (item.path !== '/dashboard' && location.pathname.startsWith(item.path));

            return (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className={`sidebar-nav-item ${isActive ? 'sidebar-nav-item--active' : ''}`}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon size={20} className="sidebar-nav-icon" />
                  {!sidebarCollapsed && <span className="sidebar-nav-label">{item.label}</span>}
                  {isActive && <div className="sidebar-nav-indicator" />}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User Section */}
      <div className="sidebar-footer">
        {user && (
          <div className="sidebar-user">
            <div className="sidebar-user-avatar">
              {user.name?.charAt(0).toUpperCase() || 'U'}
            </div>
            {!sidebarCollapsed && (
              <div className="sidebar-user-info">
                <span className="sidebar-user-name">{user.name}</span>
                <span className="sidebar-user-email">{user.email}</span>
              </div>
            )}
            <button
              className="sidebar-logout-btn"
              onClick={signOut}
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
