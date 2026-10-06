import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import type { CompanyProfile, CompanyProfileInput } from '../api/types';
import { Card, EmptyState, ErrorState, formatDateTime, Spinner } from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';

const EMPTY: CompanyProfileInput = {
  industrySectors: '',
  regulatoryBodies: '',
  jurisdictions: '',
  complianceContactEmail: '',
  notificationEnabled: true,
  notes: '',
};

export function CompanyProfilePage() {
  const { user } = useAuth();
  const toast = useToast();
  const companyId = user?.companyId ?? null;

  const profile = useAsync<{ profile: CompanyProfile | null }>(
    async () => {
      if (companyId == null) return { profile: null };
      try {
        const result = await api.get<CompanyProfile>(`/api/companies/${companyId}/profile`);
        return { profile: result };
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return { profile: null };
        throw error;
      }
    },
    [companyId],
  );

  const [form, setForm] = useState<CompanyProfileInput>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null);

  useEffect(() => {
    if (profile.data && profile.data.profile && loadedFrom !== profile.data.profile.id) {
      const stored = profile.data.profile;
      setForm({
        industrySectors: stored.industrySectors ?? '',
        regulatoryBodies: stored.regulatoryBodies ?? '',
        jurisdictions: stored.jurisdictions ?? '',
        complianceContactEmail: stored.complianceContactEmail ?? '',
        notificationEnabled: stored.notificationEnabled ?? true,
        notes: stored.notes ?? '',
      });
      setLoadedFrom(stored.id);
    }
  }, [profile.data, loadedFrom]);

  function update<K extends keyof CompanyProfileInput>(key: K, value: CompanyProfileInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (companyId == null) return;
    setSaving(true);
    setFieldErrors({});
    try {
      const saved = await api.put<CompanyProfile>(`/api/companies/${companyId}/profile`, {
        ...form,
        industrySectors: form.industrySectors ?? '',
        regulatoryBodies: form.regulatoryBodies ?? '',
        jurisdictions: form.jurisdictions ?? '',
        complianceContactEmail: form.complianceContactEmail ?? '',
        notes: form.notes ?? '',
      });
      setLoadedFrom(saved.id);
      profile.reload();
      toast.success('Company profile saved');
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fields ?? {});
        toast.error(error.message);
      } else {
        toast.error('Saving the profile failed');
      }
    } finally {
      setSaving(false);
    }
  }

  if (companyId == null) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>Company profile</h1>
        </header>
        <Card>
          <EmptyState
            title="No company linked to this account"
            hint="Your user has no companyId, so there is no profile to edit. Register with a companyName or ask an admin to assign one."
          />
        </Card>
      </div>
    );
  }

  if (profile.loading) {
    return (
      <div className="page">
        <Spinner label="Loading profile…" />
      </div>
    );
  }

  if (profile.error) {
    return (
      <div className="page">
        <ErrorState error={profile.error} onRetry={profile.reload} />
      </div>
    );
  }

  const stored = profile.data?.profile ?? null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Company profile</h1>
          <p className="muted">
            {user?.companyName ?? 'Company'} · used by the relevance engine to score regulations.
          </p>
        </div>
        <div className="page-header-actions">
          <span className="muted small">
            {stored ? `Last updated ${formatDateTime(stored.updatedAt)}` : 'Not created yet'}
          </span>
        </div>
      </header>

      <Card title="Editable profile fields">
        <form onSubmit={handleSubmit} className="form-grid" noValidate>
          <label className="field">
            <span className="field-label">Industry sectors</span>
            <textarea
              rows={3}
              value={form.industrySectors ?? ''}
              onChange={(event) => update('industrySectors', event.target.value)}
              placeholder="e.g. Banking, NBFC, Digital payments"
            />
            {fieldErrors.industrySectors ? (
              <span className="field-error">{fieldErrors.industrySectors}</span>
            ) : null}
            <span className="field-hint">Comma or newline separated — drives HIGH/MEDIUM/LOW relevance.</span>
          </label>

          <label className="field">
            <span className="field-label">Regulatory bodies</span>
            <input
              type="text"
              value={form.regulatoryBodies ?? ''}
              onChange={(event) => update('regulatoryBodies', event.target.value)}
              placeholder="e.g. RBI, SEBI, MCA"
            />
            {fieldErrors.regulatoryBodies ? (
              <span className="field-error">{fieldErrors.regulatoryBodies}</span>
            ) : null}
          </label>

          <label className="field">
            <span className="field-label">Jurisdictions</span>
            <input
              type="text"
              value={form.jurisdictions ?? ''}
              onChange={(event) => update('jurisdictions', event.target.value)}
              placeholder="e.g. India, Singapore"
            />
            {fieldErrors.jurisdictions ? (
              <span className="field-error">{fieldErrors.jurisdictions}</span>
            ) : null}
          </label>

          <label className="field">
            <span className="field-label">Compliance contact</span>
            <input
              type="email"
              value={form.complianceContactEmail ?? ''}
              onChange={(event) => update('complianceContactEmail', event.target.value)}
              placeholder="compliance@example.com"
            />
            {fieldErrors.complianceContactEmail ? (
              <span className="field-error">{fieldErrors.complianceContactEmail}</span>
            ) : null}
          </label>

          <label className="field field-checkbox">
            <input
              type="checkbox"
              checked={form.notificationEnabled ?? true}
              onChange={(event) => update('notificationEnabled', event.target.checked)}
            />
            <span className="field-label">Email notifications enabled</span>
          </label>

          <label className="field">
            <span className="field-label">Notes</span>
            <textarea
              rows={5}
              value={form.notes ?? ''}
              onChange={(event) => update('notes', event.target.value)}
              placeholder="Internal compliance notes…"
            />
            {fieldErrors.notes ? <span className="field-error">{fieldErrors.notes}</span> : null}
          </label>

          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save profile'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={saving}
              onClick={() => {
                setForm(EMPTY);
                setFieldErrors({});
              }}
            >
              Reset
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
