import type { ReactNode } from 'react';
import type { RelevanceLevel } from '../api/types';

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <p className="empty-title">{title}</p>
      {hint ? <p className="empty-hint">{hint}</p> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <p className="error-title">Something went wrong</p>
      <p className="error-detail">{error.message}</p>
      {onRetry ? (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Card({
  title,
  action,
  children,
  className = '',
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`.trim()}>
      {title || action ? (
        <header className="card-header">
          <h2 className="card-title">{title}</h2>
          {action}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function RelevanceBadge({ level }: { level?: string | null }) {
  const normalized = (level ?? 'NONE').toUpperCase();
  return <span className={`badge badge-${normalized.toLowerCase()}`}>{normalized}</span>;
}

export function StatusBadge({ status }: { status?: string | null }) {
  const normalized = (status ?? 'PENDING').toUpperCase();
  return <span className={`badge badge-status-${normalized.toLowerCase()}`}>{normalized}</span>;
}

export function RiskBadge({ level }: { level?: string | null }) {
  const normalized = (level ?? '—').toUpperCase();
  return <span className={`badge badge-${normalized.toLowerCase()}`}>{normalized}</span>;
}

export const RELEVANCE_LEVELS: RelevanceLevel[] = ['HIGH', 'MEDIUM', 'LOW', 'NONE'];

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

export function shortHash(value: string | null | undefined): string {
  if (!value) return '—';
  return value.length > 14 ? `${value.slice(0, 14)}…` : value;
}
