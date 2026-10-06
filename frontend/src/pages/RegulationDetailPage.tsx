import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { Alert, Analysis, ChangeEvent, Regulation, VersionDetail, VersionSummary } from '../api/types';
import { AnalysisPanel } from '../components/AnalysisPanel';
import {
  Card,
  EmptyState,
  ErrorState,
  formatDate,
  formatDateTime,
  shortHash,
  Spinner,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';

/**
 * Best-effort lookup of a full §2.4 analysis document. The backend shipped in
 * Phase 1 has no analysis endpoint, so a 404/500 simply degrades to the
 * alert-derived / placeholder panel.
 */
async function fetchAnalysis(regulationId: number): Promise<Analysis | null> {
  try {
    return await api.get<Analysis>(`/api/analyses/${regulationId}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 500)) return null;
    if (error instanceof ApiError && error.status === 0) return null;
    return null;
  }
}

export function RegulationDetailPage() {
  const params = useParams();
  const regulationId = Number(params.id);

  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [versionIdNonce, setVersionIdNonce] = useState(0);

  const regulation = useAsync<Regulation>(
    () => api.get<Regulation>(`/api/regulations/${regulationId}`),
    [regulationId],
  );
  const versions = useAsync<VersionSummary[]>(
    () => api.get<VersionSummary[]>(`/api/regulations/${regulationId}/versions`),
    [regulationId],
  );
  const alerts = useAsync<Alert[]>(() => api.get<Alert[]>('/api/alerts'), [regulationId]);
  const events = useAsync<ChangeEvent[]>(() => api.get<ChangeEvent[]>('/api/events'), [regulationId]);
  const analysis = useAsync<Analysis | null>(() => fetchAnalysis(regulationId), [regulationId]);

  const versionList = useMemo(() => {
    const list = [...(versions.data ?? [])];
    list.sort((a, b) => b.versionNo - a.versionNo);
    return list;
  }, [versions.data]);

  useEffect(() => {
    if (selectedVersionId != null) return;
    const current = versionList.find((version) => version.current) ?? versionList[0];
    if (current) setSelectedVersionId(current.id);
  }, [versionList, selectedVersionId]);

  const detail = useAsync<VersionDetail | null>(
    async () => {
      if (selectedVersionId == null) return null;
      return api.get<VersionDetail>(
        `/api/regulations/${regulationId}/versions/${selectedVersionId}`,
      );
    },
    [regulationId, selectedVersionId, versionIdNonce],
  );

  if (Number.isNaN(regulationId)) {
    return (
      <div className="page">
        <ErrorState error={new Error('Invalid regulation id')} />
      </div>
    );
  }

  if (regulation.loading || versions.loading) {
    return (
      <div className="page">
        <Spinner label="Loading regulation…" />
      </div>
    );
  }

  if (regulation.error) {
    return (
      <div className="page">
        <ErrorState error={regulation.error} onRetry={regulation.reload} />
      </div>
    );
  }

  const data = regulation.data;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="breadcrumb">
            <Link to="/">Dashboard</Link> <span aria-hidden="true">/</span> Regulation #
            {regulationId}
          </p>
          <h1>{data?.title ?? `Regulation #${regulationId}`}</h1>
          <p className="muted">
            {data?.sourceCode ?? '—'} · {data?.category ?? 'General'} · identifier{' '}
            {data?.identifier ?? '—'}
          </p>
        </div>
        <div className="page-header-actions">
          <span className="badge badge-count">{versionList.length} versions</span>
          {data?.url ? (
            <a className="btn btn-secondary" href={data.url} target="_blank" rel="noreferrer">
              Open source ↗
            </a>
          ) : null}
        </div>
      </header>

      <div className="two-col two-col-wide">
        <Card title="Version history">
          {versions.error ? (
            <ErrorState error={versions.error} onRetry={versions.reload} />
          ) : versionList.length === 0 ? (
            <EmptyState title="No versions recorded" />
          ) : (
            <ul className="version-list">
              {versionList.map((version) => {
                const selected = version.id === selectedVersionId;
                return (
                  <li key={version.id}>
                    <button
                      type="button"
                      className={`version-item${selected ? ' version-item-active' : ''}`}
                      onClick={() => {
                        setSelectedVersionId(version.id);
                        setVersionIdNonce((value) => value + 1);
                      }}
                      aria-pressed={selected}
                    >
                      <span className="version-no">v{version.versionNo}</span>
                      <span className="version-meta">
                        {formatDateTime(version.fetchedAt)} · {shortHash(version.contentHash)}
                      </span>
                      {version.current ? <span className="badge badge-current">current</span> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card
          title="Version content"
          action={
            detail.data ? (
              <span className="muted small">
                {detail.data.content?.length ?? 0} chars · {shortHash(detail.data.contentHash)}
              </span>
            ) : null
          }
        >
          {selectedVersionId == null ? (
            <EmptyState title="Select a version" hint="Choose a version from the history list." />
          ) : detail.loading ? (
            <Spinner label="Loading content…" />
          ) : detail.error ? (
            <ErrorState error={detail.error} onRetry={detail.reload} />
          ) : detail.data?.content ? (
            <pre className="content-viewer">{detail.data.content}</pre>
          ) : (
            <EmptyState
              title="No content stored"
              hint="This version has no extracted text yet."
            />
          )}
        </Card>
      </div>

      <AnalysisPanel
        regulationId={regulationId}
        regulationTitle={data?.title}
        analysis={analysis.data}
        analysisLoading={analysis.loading}
        alerts={alerts.data ?? []}
        events={events.data ?? []}
      />

      <Card title="Regulation metadata">
        <dl className="meta-grid">
          <div>
            <dt>Published</dt>
            <dd>{formatDate(data?.publishedDate)}</dd>
          </div>
          <div>
            <dt>Effective</dt>
            <dd>{formatDate(data?.effectiveDate)}</dd>
          </div>
          <div>
            <dt>Versions</dt>
            <dd>{data?.versionCount ?? versionList.length}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatDateTime(data?.createdAt)}</dd>
          </div>
          <div>
            <dt>Source URL</dt>
            <dd className="truncate">
              {data?.url ? (
                <a href={data.url} target="_blank" rel="noreferrer">
                  {data.url}
                </a>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
