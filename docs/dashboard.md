# Compliance Dashboard — Page ↔ API Mapping

Frontend: `frontend/**` (Vite + React 19 + TypeScript, plain CSS).
Backend base URL comes from `VITE_API_BASE` (default `http://localhost:8080`).
All requests carry `Authorization: Bearer <token>` from `localStorage` except
`POST /api/auth/login`.

## Pages → endpoints

| Page (route) | Method | Endpoint | Notes |
|---|---|---|---|
| **Login** (`/login`) | POST | `/api/auth/login` | `{email,password}` → `{token,expiresInSeconds,user{id,email,role,companyId,companyName}}`. 401 shows an error toast (no redirect loop). |
| session bootstrap (all pages) | GET | `/api/me` | Runs on load when a token exists; sets `role` used for role-aware nav. |
| **Dashboard** (`/`) | GET | `/api/regulations` | Recent regulations (sorted by `createdAt`, top 8) with `versionCount` badge. |
| | GET | `/api/alerts` | Recent alerts (top 6) with relevance + status badges; drives the stat cards. |
| | GET | `/api/events` | Last 50 change events → "Recent change events" table (links to regulation detail). |
| **Regulation detail** (`/regulations/:id`) | GET | `/api/regulations/{id}` | Title, source, category, dates. |
| | GET | `/api/regulations/{id}/versions` | Version history list; current version selected by default. |
| | GET | `/api/regulations/{id}/versions/{vid}` | Version content viewer (`content`, `contentHash`, `storagePath`, `fetchedAt`). |
| | GET | `/api/alerts` + `/api/events` | Joined on `changeEventId → regulationId` to derive the analysis panel when no analysis endpoint exists. |
| | GET | `/api/analyses/{id}` | *Optional / absent today.* Attempted best-effort; a 404/500 degrades to the alert-derived + placeholder panel (PLAN §2.4 contract). |
| **Company profile** (`/profile`) | GET | `/api/companies/{companyId}/profile` | 404 → renders a blank "not created yet" form. |
| | PUT | `/api/companies/{companyId}/profile` | Editable `industrySectors`, `regulatoryBodies`, `jurisdictions`, `complianceContactEmail`, `notificationEnabled`, `notes`. Validation `fields` shown inline. |
| **Notifications** (`/notifications`) | GET | `/api/alerts[?status=PENDING\|SENT\|FAILED\|READ]` | Client-side chip filter over PENDING / SENT / FAILED / READ + ALL counts. |
| | PATCH | `/api/alerts/{id}/status` | Body `{status:"READ"}` or `{status:"SENT"}`; row updated in place. |
| **Audit trail** (`/audit`, ADMIN) | GET | `/api/audit[?action=LOGIN]` | Action filter synced to the `?action=` query param. 403 for non-admins (route guard redirects to `/`). |
| **Sources** (`/sources`, ADMIN) | GET | `/api/sources` | Table of monitored sources. |
| | POST | `/api/sources` | Create (code, name, agency, baseUrl, watchUrl, changeDetectionId, active). |
| | PUT | `/api/sources/{id}` | Update. |
| | DELETE | `/api/sources/{id}` | Delete with confirmation. |
| shared | GET | `/actuator/health` | Not called by the UI; referenced for ops checks. |

## Error handling contract

Backend errors are `{timestamp,status,error,message[,fields]}`.

- `message` → toast title (or inline banner).
- `fields` → inline per-field validation errors (login, profile, source form).
- `401` on an authenticated call → clear token + user, dispatch `regtrack:unauthorized`,
  redirect to `/login`.
- Network failure (backend down) → `ApiError(status 0)` with a readable message.

## AI analysis rendering (PLAN §2.4)

`src/components/AnalysisPanel.tsx` renders, in priority order:

1. **Full analysis JSON** if `GET /api/analyses/{regulationId}` ever becomes available:
   `summary`, `key_changes`, `affected_entities`, `effective_date`, `required_actions`,
   `relevance[] {company_id, company_name, level, rationale}`, `risk_level`,
   `analysis_mode`/`model`, `generated_at`.
2. **Alert-derived subset** — alerts joined to the regulation through
   `/api/events` supply `summary`, `requiredAction → required_actions`,
   `effectiveDate → effective_date`, `relevance`, `affectedAreas → affected_entities`.
3. **Placeholder panel** explaining that
   `storage/analysis/<regulationId>/v<n>.json` (ai role output) is not yet exposed
   by an endpoint.

## Roles & navigation

| Nav item | COMPLIANCE_OFFICER | ADMIN |
|---|---|---|
| Dashboard | ✓ | ✓ |
| Notifications | ✓ (own company only, backend-scoped) | ✓ (all) |
| Company profile | ✓ (own company) | ✓ |
| Audit trail | hidden + route guard | ✓ |
| Sources | hidden + route guard | ✓ |

## Run

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
npm run build                                 # tsc --noEmit && vite build
```
