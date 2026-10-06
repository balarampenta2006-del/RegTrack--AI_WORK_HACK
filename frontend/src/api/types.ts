export type Role = 'ADMIN' | 'COMPLIANCE_OFFICER';

export interface User {
  id: number;
  email: string;
  fullName?: string | null;
  role: Role | string;
  companyId: number | null;
  companyName: string | null;
}

export interface AuthResponse {
  token: string;
  type?: string;
  expiresInSeconds: number;
  user: User;
}

export interface Regulation {
  id: number;
  sourceId: number | null;
  sourceCode: string | null;
  title: string;
  identifier: string | null;
  url: string | null;
  category: string | null;
  publishedDate: string | null;
  effectiveDate: string | null;
  versionCount: number | null;
  currentVersionId: number | null;
  createdAt: string | null;
}

export interface VersionSummary {
  id: number;
  regulationId: number;
  versionNo: number;
  contentHash: string | null;
  sourceUrl: string | null;
  fetchedAt: string | null;
  current: boolean | null;
}

export interface VersionDetail extends VersionSummary {
  content: string | null;
  storagePath: string | null;
}

export type AlertStatus = 'PENDING' | 'SENT' | 'FAILED' | 'READ';
export type RelevanceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';

export interface Alert {
  id: number;
  companyId: number | null;
  companyName: string | null;
  changeEventId: number;
  relevance: RelevanceLevel | string | null;
  summary: string | null;
  affectedAreas: string | null;
  effectiveDate: string | null;
  requiredAction: string | null;
  status: AlertStatus | string;
  emailRecipients: string | null;
  emailSentAt: string | null;
  regulationTitle: string | null;
  regulationUrl: string | null;
  sourceCode: string | null;
  createdAt: string | null;
}

export interface ChangeEvent {
  id: number;
  sourceId: number | null;
  sourceCode: string | null;
  regulationId: number | null;
  status: string | null;
  payloadUrl: string | null;
  oldVersionId: number | null;
  newVersionId: number | null;
  error: string | null;
  receivedAt: string | null;
  processedAt: string | null;
}

export interface AuditEntry {
  id: number;
  actorEmail: string | null;
  actorRole: string | null;
  action: string;
  entityType: string | null;
  entityId: number | null;
  details: string | null;
  ipAddress: string | null;
  createdAt: string | null;
}

export interface Source {
  id: number;
  code: string;
  name: string;
  agency: string | null;
  baseUrl: string | null;
  watchUrl: string | null;
  changeDetectionId: string | null;
  active: boolean | null;
  createdAt: string | null;
}

export interface SourceInput {
  code: string;
  name: string;
  agency?: string | null;
  baseUrl?: string | null;
  watchUrl?: string | null;
  changeDetectionId?: string | null;
  active?: boolean | null;
}

export interface Company {
  id: number;
  name: string;
  industry: string | null;
  website: string | null;
  description: string | null;
  jurisdictions: string | null;
  createdAt: string | null;
}

export interface CompanyProfile {
  id: number;
  companyId: number;
  industrySectors: string | null;
  regulatoryBodies: string | null;
  jurisdictions: string | null;
  complianceContactEmail: string | null;
  notificationEnabled: boolean | null;
  notes: string | null;
  updatedAt: string | null;
}

export interface CompanyProfileInput {
  industrySectors?: string | null;
  regulatoryBodies?: string | null;
  jurisdictions?: string | null;
  complianceContactEmail?: string | null;
  notificationEnabled?: boolean | null;
  notes?: string | null;
}

/** Analysis contract, PLAN.md §2.4 (produced by the ai role). */
export interface RelevanceEntry {
  company_id: number;
  company_name?: string;
  level: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE' | string;
  rationale?: string;
}

export interface Analysis {
  regulation_id?: number;
  version_no?: number;
  event_id?: number;
  analysis_mode?: 'llm' | 'stub' | string;
  model?: string;
  summary?: string;
  key_changes?: string[];
  affected_entities?: string[];
  effective_date?: string | null;
  required_actions?: string[];
  risk_level?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  relevance?: RelevanceEntry[];
  generated_at?: string;
  old_version_missing?: boolean;
}

/** Partial analysis surfaced through an alert row (PLAN.md §2.4 subset). */
export interface AlertDerivedAnalysis {
  source: 'alert';
  summary?: string | null;
  affected_entities?: string[];
  effective_date?: string | null;
  required_actions?: string[];
  relevance?: RelevanceEntry[];
  risk_level?: string;
}
