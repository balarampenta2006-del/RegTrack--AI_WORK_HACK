---
role: frontend
status: DONE
updated: 2026-10-03T00:00:00Z
---
## Artifacts
- frontend/package.json — Vite + React 19 + TS app manifest (deps: react, react-dom, react-router-dom; dev: vite 7.3.6, @vitejs/plugin-react 5.2, typescript 5.9). No CSS framework — plain CSS.
- frontend/tsconfig.json — strict, noUnusedLocals/Parameters, verbatimModuleSyntax, noEmit; `npm run build` = `tsc --noEmit && vite build`.
- frontend/vite.config.ts — react plugin, port 5173, manualChunks vendor split (react / router).
- frontend/index.html, frontend/.env.example, frontend/.gitignore, frontend/README.md — scaffolding + run instructions.
- frontend/src/api/client.ts — API client: `VITE_API_BASE` (default http://localhost:8080), Bearer token from localStorage (`regtrack.token`), auto 401 → clear + `regtrack:unauthorized` event → redirect /login, JSON error `{message, fields?}` → toast + inline field errors, network failure → ApiError(0).
- frontend/src/api/types.ts — DTOs mirroring backend records + PLAN §2.4 `Analysis` shape.
- frontend/src/state/AuthContext.tsx — session bootstrap GET /api/me, login/logout, `isAdmin`.
- frontend/src/state/ToastContext.tsx — success/error/info toast stack.
- frontend/src/hooks/useAsync.ts — loading/error/reload loader hook with unmount guard.
- frontend/src/components/Layout.tsx — role-aware responsive nav (sidebar → mobile drawer): Dashboard, Notifications, Company profile, + Audit trail & Sources (ADMIN only).
- frontend/src/components/ui.tsx — Spinner/EmptyState/ErrorState/Card/Relevance/Status/Risk badges + date formatters.
- frontend/src/components/AnalysisPanel.tsx — §2.4 renderer: full analysis JSON → alert-derived subset → placeholder panel.
- frontend/src/pages/{LoginPage,DashboardPage,RegulationDetailPage,CompanyProfilePage,NotificationsPage,AuditPage,SourcesPage,NotFoundPage}.tsx — 8 routes (see docs/dashboard.md).
- frontend/src/App.tsx, src/main.tsx, src/styles.css — router with RequireAuth/RequireAdmin guards, plain-CSS responsive theme.
- frontend/dist/** — production build output (react 221.7 kB / router 39.1 kB / app 40.8 kB / css 15.2 kB).
- docs/dashboard.md — full page → endpoint mapping, error contract, analysis fallback chain, role matrix.

## Verification
- `cd D:\AI_Hack\frontend; npm install --no-fund --no-audit` → `added 73 packages in 10s`, **EXIT=0**.
- `cd D:\AI_Hack\frontend; npm run build` (fresh dist) → **EXIT=0**. Exact output tail:
  ```
  vite v7.3.6 building client environment for production...
  transforming...
  ✓ 56 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                   1.06 kB │ gzip:  0.57 kB
  dist/assets/index-Cszhm3Ik.css   15.18 kB │ gzip:  3.76 kB
  dist/assets/router-JuVrK38A.js   39.13 kB │ gzip: 14.11 kB
  dist/assets/index-BFbXJppX.js    40.77 kB │ gzip: 10.96 kB
  dist/assets/react-YWPnaJPF.js   221.70 kB │ gzip: 68.96 kB
  ✓ built in 1.11s
  BUILD_EXIT=0
  ```
  (`npm run build` runs `tsc --noEmit` first, so typecheck passes under strict mode.)
- Live smoke vs `http://localhost:8080` (backend up, read-only):
  - `POST /api/auth/login` {admin@regtrack.local / Admin@12345} → **200**, role=ADMIN, id=1, tokenLen=258.
  - Authenticated `GET /api/sources` → **200**, 8 sources (MCA, RBI, SEBI, EDCI, …).
  - Also 200: `GET /api/me`, `/api/regulations`, `/api/alerts`, `/api/events`, `/api/audit`, `/api/companies`.
  - No backend data created or deleted.
- Built bundle served: `npm run preview -- --port 4173` → `GET /` **200**, `GET /assets/index-BFbXJppX.js` **200**; port closed afterwards.

## Handoff notes
- **env vars ops must set** (build/runtime): `VITE_API_BASE` (build-time inlined by Vite; default `http://localhost:8080`; docker build → `http://backend:8080`). Nothing else is read by the UI. Seeded creds `ADMIN_EMAIL`/`ADMIN_PASSWORD` are only a login convenience, not read by the frontend.
- **CORS**: backend `regtrack.cors.allowed-origins` must include the origin that serves the SPA (default `http://localhost:5173,http://localhost:3000`). If ops serves on another port/host, extend that property.
- **docker serve suggestion** (ops owns `docker-compose.yml`): add a `frontend` service — `build: ./frontend` with `ARG VITE_API_BASE`/`ENV VITE_API_BASE`, `npm ci && npm run build`, then an `nginx:alpine` runtime serving `dist/` with `try_files $uri /index.html;` (SPA fallback for `/regulations/:id`), expose **8104** (ports list §2.2 is otherwise full) and set `regtrack.cors.allowed-origins=http://localhost:8104`.
- **Assumption (PLAN §0.5)**: no analysis endpoint exists in the live backend (grepped `backend/src`), so the regulation-detail panel probes `GET /api/analyses/{id}` and falls back to alert-derived data joined via `/api/events`, then to a placeholder explaining `storage/analysis/<regId>/v<n>.json`. If the ai role exposes an endpoint, drop it into `fetchAnalysis()` in `frontend/src/pages/RegulationDetailPage.tsx` — the renderer already accepts the full §2.4 shape.
- Alert statuses modelled as PENDING/SENT/FAILED/READ; relevance HIGH/MEDIUM/LOW/NONE (verified against backend enums).
- Non-admin hitting `/audit` or `/sources` is redirected to `/` by a route guard before the backend 403.

## Extra deps / unresolved issues
- Extra npm deps: none beyond react / react-dom / react-router-dom (+vite, plugin-react, typescript, @types/*). No Tailwind, no UI kit, no data-fetching library — keeps install at 73 packages / ~10 s.
- Not configured (out of DoD scope): ESLint/Prettier config, unit tests / React Testing Library (no test framework was mandated for frontend; QA owns `tests/**`).
- `npm warn install-scripts esbuild@0.28.2 (postinstall)` — npm 11.19 `allowScripts` notice; build succeeds regardless (EXIT 0).
- Source **delete** and **create** UIs are implemented but deliberately not exercised (smoke rules forbid creating/deleting backend data).
- localStorage-based token (XSS-relevant) noted for the QA security review; no refresh-token support — session ends when the JWT expires (`expiresInSeconds`) via the 401 handler.
