import type { Analysis, Alert, ChangeEvent } from '../api/types';
import { Card, formatDate, RiskBadge, RelevanceBadge, Spinner } from './ui';

interface AnalysisPanelProps {
  regulationId: number;
  regulationTitle: string | null | undefined;
  analysis: Analysis | null;
  analysisLoading: boolean;
  alerts: Alert[];
  events: ChangeEvent[];
}

function hasContent(analysis: Analysis | null): analysis is Analysis {
  if (!analysis) return false;
  return Boolean(
    analysis.summary ||
      (analysis.key_changes && analysis.key_changes.length > 0) ||
      (analysis.required_actions && analysis.required_actions.length > 0),
  );
}

function joinList(items: Array<string | null | undefined> | undefined): string[] {
  if (!items) return [];
  return items.filter((item): item is string => Boolean(item && item.trim()));
}

export function AnalysisPanel({
  regulationId,
  regulationTitle,
  analysis,
  analysisLoading,
  alerts,
  events,
}: AnalysisPanelProps) {
  const eventRegulationIds = new Map<number, number>();
  for (const event of events) {
    if (event.regulationId != null) eventRegulationIds.set(event.id, event.regulationId);
  }

  const relatedAlerts = alerts.filter((alert) => {
    const mapped = eventRegulationIds.get(alert.changeEventId);
    if (mapped != null) return mapped === regulationId;
    return Boolean(regulationTitle) && alert.regulationTitle === regulationTitle;
  });

  const derived = relatedAlerts[0];
  const derivedActions = joinList(derived?.requiredAction?.split('\n'));
  const derivedEntities = joinList(derived?.affectedAreas?.split(/[;,]/));

  if (analysisLoading) {
    return (
      <Card title="AI analysis">
        <Spinner label="Loading analysis…" />
      </Card>
    );
  }

  const fullAnalysis = hasContent(analysis) ? analysis : null;

  return (
    <Card
      title="AI analysis"
      action={
        fullAnalysis ? (
          <span className="muted small">
            {fullAnalysis.analysis_mode === 'llm' ? 'LLM' : 'Stub'} · {fullAnalysis.model ?? 'n/a'}
          </span>
        ) : (
          <span className="muted small">PLAN §2.4 contract</span>
        )
      }
    >
      {fullAnalysis ? (
        <div className="analysis">
          <div className="analysis-meta">
            <RiskBadge level={fullAnalysis.risk_level} />
            <span className="muted small">
              v{fullAnalysis.version_no ?? '?'} · {fullAnalysis.generated_at ?? ''}
            </span>
          </div>
          <p className="analysis-summary">{fullAnalysis.summary}</p>

          {joinList(fullAnalysis.key_changes).length > 0 ? (
            <div className="analysis-block">
              <h3>Key changes</h3>
              <ul>
                {joinList(fullAnalysis.key_changes).map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {joinList(fullAnalysis.affected_entities).length > 0 ? (
            <div className="analysis-block">
              <h3>Affected entities</h3>
              <ul className="chip-row">
                {joinList(fullAnalysis.affected_entities).map((item, index) => (
                  <li key={index} className="chip">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="analysis-grid">
            <div>
              <h3>Effective date</h3>
              <p>{formatDate(fullAnalysis.effective_date ?? null)}</p>
            </div>
            <div>
              <h3>Relevance</h3>
              <div className="chip-row">
                {(fullAnalysis.relevance ?? []).map((entry, index) => (
                  <span key={index} className="chip">
                    <RelevanceBadge level={entry.level} /> {entry.company_name ?? `Company #${entry.company_id}`}
                  </span>
                ))}
                {(fullAnalysis.relevance ?? []).length === 0 ? <span className="muted">—</span> : null}
              </div>
            </div>
          </div>

          {joinList(fullAnalysis.required_actions).length > 0 ? (
            <div className="analysis-block">
              <h3>Required actions</h3>
              <ol>
                {joinList(fullAnalysis.required_actions).map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : derived ? (
        <div className="analysis">
          <div className="analysis-meta">
            <RelevanceBadge level={derived.relevance} />
            <span className="muted small">Derived from alert #{derived.id}</span>
          </div>
          <p className="analysis-summary">{derived.summary ?? 'No summary recorded.'}</p>
          <div className="analysis-grid">
            <div>
              <h3>Effective date</h3>
              <p>{formatDate(derived.effectiveDate)}</p>
            </div>
            <div>
              <h3>Affected areas</h3>
              <p>{derivedEntities.length > 0 ? derivedEntities.join(', ') : '—'}</p>
            </div>
          </div>
          {derivedActions.length > 0 ? (
            <div className="analysis-block">
              <h3>Required actions</h3>
              <ol>
                {derivedActions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="analysis analysis-placeholder">
          <p>
            <strong>No analysis available yet.</strong>
          </p>
          <p className="muted">
            The ai role writes the full analysis JSON (summary, key_changes, affected_entities,
            effective_date, required_actions, relevance) to
            <code> storage/analysis/&lt;regulationId&gt;/v&lt;n&gt;.json</code>. Once an endpoint
            exposes it, this panel renders it using the PLAN §2.4 contract. Until then, alert-derived
            summary and required actions are shown when alerts exist.
          </p>
        </div>
      )}
    </Card>
  );
}
