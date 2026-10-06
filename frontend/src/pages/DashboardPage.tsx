import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Alert, ChangeEvent, Regulation } from '../api/types';
import { useAsync } from '../hooks/useAsync';
import { useAuth } from '../state/AuthContext';
import {
  Card,
  EmptyState,
  ErrorState,
  formatDate,
  RelevanceBadge,
  Spinner,
  StatusBadge,
} from '../components/ui';

const ALERTS_PREVIEW = 6;
const REGULATIONS_PREVIEW = 8;

export function DashboardPage() {
  const { user, isAdmin } = useAuth();

  const regulations = useAsync<Regulation[]>(() => api.get<Regulation[]>('/api/regulations'), []);
  const alerts = useAsync<Alert[]>(() => api.get<Alert[]>('/api/alerts'), []);
  const events = useAsync<ChangeEvent[]>(() => api.get<ChangeEvent[]>('/api/events'), []);

  const recentRegulations = [...(regulations.data ?? [])]
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))
    .slice(0, REGULATIONS_PREVIEW);

  const recentAlerts = (alerts.data ?? []).slice(0, ALERTS_PREVIEW);
  const unreadAlerts = (alerts.data ?? []).filter((alert) => alert.status !== 'READ').length;
  const highRelevance = (alerts.data ?? []).filter(
    (alert) => (alert.relevance ?? '').toUpperCase() === 'HIGH',
  ).length;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">
            Welcome back{user?.companyName ? ` — ${user.companyName}` : ''}. Latest regulatory
            activity across your monitored sources.
          </p>
        </div>
      </header>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Regulations tracked</span>
          <span className="stat-value">{regulations.loading ? '…' : (regulations.data ?? []).length}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Alerts</span>
          <span className="stat-value">{alerts.loading ? '…' : (alerts.data ?? []).length}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Unread / open</span>
          <span className="stat-value">{alerts.loading ? '…' : unreadAlerts}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">High relevance</span>
          <span className="stat-value">{alerts.loading ? '…' : highRelevance}</span>
        </div>
      </div>

      <div className="two-col">
        <Card
          title="Recent regulations"
          action={<Link className="card-link" to="/notifications">View alerts →</Link>}
        >
          {regulations.loading ? (
            <Spinner label="Loading regulations…" />
          ) : regulations.error ? (
            <ErrorState error={regulations.error} onRetry={regulations.reload} />
          ) : recentRegulations.length === 0 ? (
            <EmptyState
              title="No regulations yet"
              hint="Change events from monitored sources will populate this list."
            />
          ) : (
            <ul className="item-list">
              {recentRegulations.map((regulation) => (
                <li key={regulation.id} className="item-row">
                  <div className="item-main">
                    <Link className="item-title" to={`/regulations/${regulation.id}`}>
                      {regulation.title}
                    </Link>
                    <span className="item-meta">
                      {regulation.sourceCode ?? '—'} · {regulation.category ?? 'General'} ·
                      published {formatDate(regulation.publishedDate)}
                    </span>
                  </div>
                  <span className="badge badge-count" title="Version count">
                    v{regulation.versionCount ?? 1}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Recent alerts"
          action={<Link className="card-link" to="/notifications">Manage →</Link>}
        >
          {alerts.loading ? (
            <Spinner label="Loading alerts…" />
          ) : alerts.error ? (
            <ErrorState error={alerts.error} onRetry={alerts.reload} />
          ) : recentAlerts.length === 0 ? (
            <EmptyState
              title="No alerts"
              hint={isAdmin ? 'Alerts appear once relevance scoring produces them.' : 'No alerts for your company yet.'}
            />
          ) : (
            <ul className="item-list">
              {recentAlerts.map((alert) => (
                <li key={alert.id} className="item-row item-row-stacked">
                  <div className="item-main">
                    <span className="item-title">{alert.regulationTitle ?? `Alert #${alert.id}`}</span>
                    <span className="item-meta">{alert.summary ?? 'No summary'}</span>
                  </div>
                  <div className="item-badges">
                    <RelevanceBadge level={alert.relevance} />
                    <StatusBadge status={alert.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent change events">
        {events.loading ? (
          <Spinner label="Loading events…" />
        ) : events.error ? (
          <ErrorState error={events.error} onRetry={events.reload} />
        ) : (events.data ?? []).length === 0 ? (
          <EmptyState title="No change events yet" hint="The monitor webhook has not fired." />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Source</th>
                  <th scope="col">Regulation</th>
                  <th scope="col">Status</th>
                  <th scope="col">Received</th>
                </tr>
              </thead>
              <tbody>
                {(events.data ?? []).slice(0, 8).map((event) => (
                  <tr key={event.id}>
                    <td>{event.id}</td>
                    <td>{event.sourceCode ?? '—'}</td>
                    <td>
                      {event.regulationId ? (
                        <Link to={`/regulations/${event.regulationId}`}>#{event.regulationId}</Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <span className={`badge badge-event-${(event.status ?? 'unknown').toLowerCase()}`}>
                        {event.status ?? 'UNKNOWN'}
                      </span>
                    </td>
                    <td>{formatDate(event.receivedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
