import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { AuditEntry } from '../api/types';
import { Card, EmptyState, ErrorState, formatDateTime, Spinner } from '../components/ui';
import { useAsync } from '../hooks/useAsync';

const KNOWN_ACTIONS = [
  'LOGIN',
  'LOGIN_FAILED',
  'REGISTER',
  'ALERT_CREATED',
  'ALERT_STATUS_CHANGED',
  'COMPANY_CREATED',
  'COMPANY_UPDATED',
  'PROFILE_UPDATED',
  'SOURCE_CREATED',
  'SOURCE_UPDATED',
  'WEBHOOK_RECEIVED',
  'EXTRACTION_TRIGGERED',
  'SEED_ADMIN',
  'SEED_SOURCES',
];

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const action = searchParams.get('action') ?? 'ALL';

  const query = action && action !== 'ALL' ? `?action=${encodeURIComponent(action)}` : '';
  const entries = useAsync<AuditEntry[]>(() => api.get<AuditEntry[]>(`/api/audit${query}`), [query]);

  function changeAction(value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === 'ALL') next.delete('action');
    else next.set('action', value);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Audit trail</h1>
          <p className="muted">Immutable log of privileged operations. ADMIN only (GET /api/audit).</p>
        </div>
        <div className="page-header-actions">
          <label className="field field-inline">
            <span className="field-label">Action</span>
            <select value={action} onChange={(event) => changeAction(event.target.value)}>
              <option value="ALL">ALL</option>
              {KNOWN_ACTIONS.map((known) => (
                <option key={known} value={known}>
                  {known}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-secondary" onClick={entries.reload}>
            Refresh
          </button>
        </div>
      </header>

      <Card>
        {entries.loading ? (
          <Spinner label="Loading audit entries…" />
        ) : entries.error ? (
          <ErrorState error={entries.error} onRetry={entries.reload} />
        ) : (entries.data ?? []).length === 0 ? (
          <EmptyState title="No audit entries" hint="No entries match the selected action filter." />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">When</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Role</th>
                  <th scope="col">Action</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Details</th>
                  <th scope="col">IP</th>
                </tr>
              </thead>
              <tbody>
                {(entries.data ?? []).map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.id}</td>
                    <td className="nowrap">{formatDateTime(entry.createdAt)}</td>
                    <td>{entry.actorEmail ?? '—'}</td>
                    <td>{entry.actorRole ?? '—'}</td>
                    <td>
                      <span className="badge badge-action">{entry.action}</span>
                    </td>
                    <td className="nowrap">
                      {entry.entityType ?? '—'}
                      {entry.entityId != null ? ` #${entry.entityId}` : ''}
                    </td>
                    <td className="truncate" title={entry.details ?? ''}>
                      {entry.details ?? '—'}
                    </td>
                    <td className="nowrap">{entry.ipAddress ?? '—'}</td>
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
