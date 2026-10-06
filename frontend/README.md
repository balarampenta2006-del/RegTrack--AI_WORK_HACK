# RegTrack Frontend — Compliance Dashboard

Vite + React 19 + TypeScript SPA for the regulatory-update-tracking prototype.

## Requirements

- Node.js ≥ 20.19 (tested on Node 26) and npm ≥ 10
- Backend running on `http://localhost:8080` (Spring Boot jar, see `../backend`)

## Quick start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Production build (type-check + bundle):

```bash
npm run build        # tsc --noEmit && vite build  →  frontend/dist
npm run preview      # serve the built dist locally
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE` | `http://localhost:8080` | Base URL of the Spring Boot API |

Set it in `frontend/.env.local` (see `.env.example`) or in the environment at build time:

```bash
VITE_API_BASE=http://backend:8080 npm run build
```

The backend must allow the front-end origin in CORS (`regtrack.cors.allowed-origins`,
default `http://localhost:5173,http://localhost:3000`).

## Seeded login

| Email | Password | Role |
|---|---|---|
| `admin@regtrack.local` | `Admin@12345` | ADMIN (sees Audit trail + Sources) |

Compliance officers register through `POST /api/auth/register` (optionally with a
`companyName`, which creates the company + profile).

## Routes

| Route | Page | Access |
|---|---|---|
| `/login` | Email/password sign-in | public |
| `/` | Dashboard — recent regulations, alerts, change events | any |
| `/regulations/:id` | Version history, version content viewer, AI analysis panel | any |
| `/notifications` | Alert list, status filter, mark READ / SENT | any |
| `/profile` | Company profile editor (GET/PUT `/api/companies/{id}/profile`) | any |
| `/audit` | Audit trail with `?action=` filter | ADMIN |
| `/sources` | Source CRUD | ADMIN |

## Architecture

```
src/
  api/client.ts       fetch wrapper: VITE_API_BASE, Bearer token from localStorage,
                      automatic 401 → logout + redirect, JSON error shape {message, fields?}
  api/types.ts        DTO types mirroring the backend records (+ PLAN §2.4 Analysis)
  state/AuthContext   session bootstrap via GET /api/me, role, login/logout
  state/ToastContext  success/error toasts
  hooks/useAsync      loader hook with loading/error/reload + unmount guard
  components/         Layout (role-aware responsive nav), ui primitives, AnalysisPanel
  pages/              one file per route above
  styles.css          plain CSS (no CSS framework, minimal dependency footprint)
```

Auth token (`regtrack.token`) and cached user (`regtrack.user`) live in `localStorage`.
A 401 on any authenticated call clears them and dispatches `regtrack:unauthorized`, which
the auth context turns into a redirect to `/login`.

## API surface consumed

See `../docs/dashboard.md` for the full page → endpoint mapping.
