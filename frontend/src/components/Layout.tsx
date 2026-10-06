import { useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../state/AuthContext';

interface NavItem {
  to: string;
  label: string;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard' },
  { to: '/notifications', label: 'Notifications' },
  { to: '/profile', label: 'Company profile' },
  { to: '/audit', label: 'Audit trail', adminOnly: true },
  { to: '/sources', label: 'Sources', adminOnly: true },
];

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? 'nav-link nav-link-active' : 'nav-link';
}

export function Layout({ children }: { children?: ReactNode }) {
  const { user, isAdmin, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const items = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);
  const currentLabel =
    NAV_ITEMS.find((item) => item.to === location.pathname)?.label ?? 'Regulation detail';

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          type="button"
          className="menu-toggle"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
        <span className="topbar-context">{currentLabel}</span>
        <div className="topbar-user">
          <span className="user-email" title={user?.email ?? ''}>
            {user?.email ?? 'Signed out'}
          </span>
          <span className={`badge badge-role-${isAdmin ? 'admin' : 'officer'}`}>
            {isAdmin ? 'ADMIN' : 'OFFICER'}
          </span>
          <button type="button" className="btn btn-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <div className="app-body">
        <nav className={`sidebar${menuOpen ? ' sidebar-open' : ''}`} aria-label="Primary">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              ✓
            </span>
            <span className="brand-text">RegTrack</span>
          </div>
          <ul className="nav-list">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={navClass}
                  onClick={() => setMenuOpen(false)}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="sidebar-footer">
            <div className="sidebar-user">
              <span className="sidebar-user-name">{user?.companyName ?? 'RegTrack'}</span>
              <span className="sidebar-user-role">{user?.role ?? ''}</span>
            </div>
          </div>
        </nav>

        {menuOpen ? (
          <button
            type="button"
            className="sidebar-backdrop"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          />
        ) : null}

        <main className="content" id="main">
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
}
