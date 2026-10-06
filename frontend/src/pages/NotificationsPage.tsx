import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Alert } from '../api/types';
import {
  Card,
  EmptyState,
  ErrorState,
  formatDateTime,
  RelevanceBadge,
  Spinner,
  StatusBadge,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { useToast } from '../state/ToastContext';

const FILTERS = ['ALL', 'PENDING', 'SENT', 'FAILED', 'READ'] as const;
type Filter = (typeof FILTERS)[number];

export function NotificationsPage() {
  const toast = useToast();
  const source = useAsync<Alert[]>(() => api.get<Alert[]>('/api/alerts'), []);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [items, setItems] = useState<Alert[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    setItems(source.data ?? []);
  }, [source.data]);

  const visible =
    filter === 'ALL' ? items : items.filter((alert) => (alert.status ?? '').toUpperCase() === filter);

  async function changeStatus(alert: Alert, status: 'READ' | 'SENT') {
    setBusyId(alert.id);
    try {
      const updated = await api.patch<Alert>(`/api/alerts/${alert.id}/status`, { status });
      setItems((current) => current.map((item) => (item.id === alert.id ? updated : item)));
      toast.success(`Alert #${alert.id} marked ${status}`);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : `Could not update alert #${alert.id}`,
      );
    } finally {
      setBusyId(null);
    }
  }

  const counts = FILTERS.reduce<Record<string, number>>((acc, key) => {
    acc[key] =
      key === 'ALL'
        ? items.length
        : items.filter((alert) => (alert.status ?? '').toUpperCase() === key).length;
    return acc;
  }, {});

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Notifications</h1>
          <p className="muted">Relevance-scored alerts for your company. Mark items read or sent.</p>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn btn-secondary" onClick={source.reload}>
            Refresh
          </button>
        </div>
      </header>

      <div className="filter-bar" role="tablist" aria-label="Filter alerts by status">
        {FILTERS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            className={`chip-button${filter === key ? ' chip-button-active' : ''}`}
            onClick={() => setFilter(key)}
          >
            {key} <span className="chip-count">{counts[key] ?? 0}</span>
          </button>
        ))}
      </div>

      <Card>
        {source.loading ? (
          <Spinner label="Loading alerts…" />
        ) : source.error ? (
          <ErrorState error={source.error} onRetry={source.reload} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={filter === 'ALL' ? 'No alerts yet' : `No ${filter} alerts`}
            hint="Alerts are created by the analysis pipeline when a monitored source changes."
          />
        ) : (
          <ul className="item-list item-list-divided">
            {visible.map((alert) => (
              <li key={alert.id} className="alert-row">
                <div className="alert-main">
                  <div className="alert-headline">
                    <span className="alert-title">
                      {alert.regulationTitle ?? `Alert #${alert.id}`}
                    </span>
                    <RelevanceBadge level={alert.relevance} />
                    <StatusBadge status={alert.status} />
                    {alert.sourceCode ? <span className="badge badge-source">{alert.sourceCode}</span> : null}
                  </div>
                  {alert.summary ? <p className="alert-summary">{alert.summary}</p> : null}
                  <div className="alert-meta">
                    <span>Company: {alert.companyName ?? `#${alert.companyId}`}</span>
                    <span>Effective: {alert.effectiveDate ?? '—'}</span>
                    <span>Created: {formatDateTime(alert.createdAt)}</span>
                    {alert.emailSentAt ? <span>Sent: {formatDateTime(alert.emailSentAt)}</span> : null}
                  </div>
                  {alert.requiredAction ? (
                    <p className="alert-action">
                      <strong>Required action:</strong> {alert.requiredAction}
                    </p>
                  ) : null}
                </div>
                <div className="alert-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busyId === alert.id || alert.status === 'READ'}
                    onClick={() => changeStatus(alert, 'READ')}
                  >
                    Mark read
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busyId === alert.id || alert.status === 'SENT'}
                    onClick={() => changeStatus(alert, 'SENT')}
                  >
                    Mark sent
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
