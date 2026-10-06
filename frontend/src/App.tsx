import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Spinner } from './components/ui';
import { AuditPage } from './pages/AuditPage';
import { CompanyProfilePage } from './pages/CompanyProfilePage';
import { DashboardPage } from './pages/DashboardPage';
import { LoginPage } from './pages/LoginPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { RegulationDetailPage } from './pages/RegulationDetailPage';
import { SourcesPage } from './pages/SourcesPage';
import { useAuth } from './state/AuthContext';
import type { ReactNode } from 'react';

function FullScreen({ label }: { label: string }) {
  return (
    <div className="full-screen">
      <Spinner label={label} />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <FullScreen label="Restoring session…" />;
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="regulations/:id" element={<RegulationDetailPage />} />
        <Route path="profile" element={<CompanyProfilePage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route
          path="audit"
          element={
            <RequireAdmin>
              <AuditPage />
            </RequireAdmin>
          }
        />
        <Route
          path="sources"
          element={
            <RequireAdmin>
              <SourcesPage />
            </RequireAdmin>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
