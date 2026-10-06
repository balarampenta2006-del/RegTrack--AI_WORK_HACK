import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import type { Source, SourceInput } from '../api/types';
import { Card, EmptyState, ErrorState, formatDate, Spinner } from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { useToast } from '../state/ToastContext';

const EMPTY: SourceInput = {
  code: '',
  name: '',
  agency: '',
  baseUrl: '',
  watchUrl: '',
  changeDetectionId: '',
  active: true,
};

type EditorMode = { kind: 'closed' } | { kind: 'new' } | { kind: 'edit'; id: number };

export function SourcesPage() {
  const toast = useToast();
  const sources = useAsync<Source[]>(() => api.get<Source[]>('/api/sources'), []);

  const [editor, setEditor] = useState<EditorMode>({ kind: 'closed' });
  const [form, setForm] = useState<SourceInput>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (editor.kind === 'edit') {
      const existing = (sources.data ?? []).find((source) => source.id === editor.id);
      if (existing) {
        setForm({
          code: existing.code,
          name: existing.name,
          agency: existing.agency ?? '',
          baseUrl: existing.baseUrl ?? '',
          watchUrl: existing.watchUrl ?? '',
          changeDetectionId: existing.changeDetectionId ?? '',
          active: existing.active ?? true,
        });
      }
    }
  }, [editor, sources.data]);

  function openNew() {
    setForm(EMPTY);
    setFieldErrors({});
    setEditor({ kind: 'new' });
  }

  function openEdit(source: Source) {
    setFieldErrors({});
    setEditor({ kind: 'edit', id: source.id });
  }

  function closeEditor() {
    setEditor({ kind: 'closed' });
    setFieldErrors({});
  }

  function update<K extends keyof SourceInput>(key: K, value: SourceInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFieldErrors({});
    const payload: SourceInput = {
      code: (form.code ?? '').trim(),
      name: (form.name ?? '').trim(),
      agency: form.agency ?? '',
      baseUrl: form.baseUrl ?? '',
      watchUrl: form.watchUrl ?? '',
      changeDetectionId: form.changeDetectionId ?? '',
      active: form.active ?? true,
    };
    try {
      if (editor.kind === 'new') {
        await api.post<Source>('/api/sources', payload);
        toast.success(`Source ${payload.code} created`);
      } else if (editor.kind === 'edit') {
        await api.put<Source>(`/api/sources/${editor.id}`, payload);
        toast.success(`Source ${payload.code} updated`);
      }
      closeEditor();
      sources.reload();
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fields ?? {});
        toast.error(error.message);
      } else {
        toast.error('Saving the source failed');
      }
    } finally {
      setSaving(false);
    }
  }

  async function removeSource(source: Source) {
    if (!window.confirm(`Delete source "${source.code}" (${source.name})? This cannot be undone.`)) {
      return;
    }
    setBusyId(source.id);
    try {
      await api.del(`/api/sources/${source.id}`);
      toast.success(`Source ${source.code} deleted`);
      if (editor.kind === 'edit' && editor.id === source.id) closeEditor();
      sources.reload();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : 'Deleting the source failed');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Sources</h1>
          <p className="muted">
            Regulator sites watched by the monitor pipeline. Writes are ADMIN-only.
          </p>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn btn-secondary" onClick={sources.reload}>
            Refresh
          </button>
          <button type="button" className="btn btn-primary" onClick={openNew}>
            New source
          </button>
        </div>
      </header>

      <div className={`two-col${editor.kind === 'closed' ? '' : ' two-col-wide'}`}>
        <Card title="Monitored sources">
          {sources.loading ? (
            <Spinner label="Loading sources…" />
          ) : sources.error ? (
            <ErrorState error={sources.error} onRetry={sources.reload} />
          ) : (sources.data ?? []).length === 0 ? (
            <EmptyState title="No sources configured" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Code</th>
                    <th scope="col">Name</th>
                    <th scope="col">Agency</th>
                    <th scope="col">Active</th>
                    <th scope="col">Created</th>
                    <th scope="col" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {(sources.data ?? []).map((source) => (
                    <tr key={source.id}>
                      <td>
                        <span className="badge badge-source">{source.code}</span>
                      </td>
                      <td>{source.name}</td>
                      <td>{source.agency ?? '—'}</td>
                      <td>
                        <span className={`badge ${source.active ? 'badge-active' : 'badge-inactive'}`}>
                          {source.active ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                      </td>
                      <td className="nowrap">{formatDate(source.createdAt)}</td>
                      <td className="row-actions">
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => openEdit(source)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-danger"
                          disabled={busyId === source.id}
                          onClick={() => removeSource(source)}
                        >
                          {busyId === source.id ? '…' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {editor.kind !== 'closed' ? (
          <Card title={editor.kind === 'new' ? 'Create source' : `Edit source #${editor.id}`}>
            <form className="form-grid" onSubmit={handleSubmit} noValidate>
              <label className="field">
                <span className="field-label">Code *</span>
                <input
                  type="text"
                  maxLength={32}
                  required
                  value={form.code ?? ''}
                  onChange={(event) => update('code', event.target.value)}
                  placeholder="RBI"
                />
                {fieldErrors.code ? <span className="field-error">{fieldErrors.code}</span> : null}
              </label>

              <label className="field">
                <span className="field-label">Name *</span>
                <input
                  type="text"
                  maxLength={190}
                  required
                  value={form.name ?? ''}
                  onChange={(event) => update('name', event.target.value)}
                  placeholder="Reserve Bank of India"
                />
                {fieldErrors.name ? <span className="field-error">{fieldErrors.name}</span> : null}
              </label>

              <label className="field">
                <span className="field-label">Agency</span>
                <input
                  type="text"
                  maxLength={64}
                  value={form.agency ?? ''}
                  onChange={(event) => update('agency', event.target.value)}
                  placeholder="RBI"
                />
              </label>

              <label className="field">
                <span className="field-label">Base URL</span>
                <input
                  type="url"
                  maxLength={255}
                  value={form.baseUrl ?? ''}
                  onChange={(event) => update('baseUrl', event.target.value)}
                  placeholder="https://www.rbi.org.in"
                />
              </label>

              <label className="field">
                <span className="field-label">Watch URL</span>
                <input
                  type="url"
                  maxLength={512}
                  value={form.watchUrl ?? ''}
                  onChange={(event) => update('watchUrl', event.target.value)}
                  placeholder="https://www.rbi.org.in/Notificationss.aspx"
                />
                {fieldErrors.watchUrl ? (
                  <span className="field-error">{fieldErrors.watchUrl}</span>
                ) : null}
              </label>

              <label className="field">
                <span className="field-label">changeDetection.io id</span>
                <input
                  type="text"
                  maxLength={128}
                  value={form.changeDetectionId ?? ''}
                  onChange={(event) => update('changeDetectionId', event.target.value)}
                  placeholder="optional watcher id"
                />
              </label>

              <label className="field field-checkbox">
                <input
                  type="checkbox"
                  checked={form.active ?? true}
                  onChange={(event) => update('active', event.target.checked)}
                />
                <span className="field-label">Active</span>
              </label>

              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : editor.kind === 'new' ? 'Create' : 'Save changes'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={closeEditor}>
                  Cancel
                </button>
              </div>
            </form>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
