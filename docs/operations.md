# Operations Runbook — Regulatory Update Tracking

Phase 5 + 7 operations: container bring-up, environment, smoke checks, teardown, and the
Windows dev-mode alternative. Contracts come from `.agents/PLAN.md`; n8n specifics live in
`n8n/README.md`.

## 1. Prerequisites

- Docker Desktop / Docker Engine with Compose v2 (`docker compose version`).
- Free host ports: **3307** (mysql, override with `MYSQL_PORT`), **8080** (backend),
  **8000** (extraction-worker), **5000/3000** (changedetection/playwright),
  **8101/8102/8103** (monitor/docproc/ai), **5678** (n8n), **5173** (frontend).
- No `.env` file is required — every variable has a PLAN.md default (table in §4).

## 2. Bring-up order

```powershell
cd D:\AI_Hack

# 1) foundation — mysql must be healthy before backend starts (depends_on)
docker compose up -d mysql backend
docker compose ps                      # regtrack-backend Up, regtrack-mysql healthy

# 2) pipeline services (Phase 2-4)
docker compose up -d monitor docproc ai
docker compose ps                      # all three "healthy" (healthchecks in Dockerfiles/compose)

# 3) n8n (Phase 5) — auto-imports n8n/workflows/regulatory-pipeline.json on FIRST start
#    (marker file /home/node/.n8n/.workflow-imported in the n8n-data volume)
docker compose up -d n8n
Start-Process http://localhost:5678    # create owner account, open the workflow, click Activate
                                       # + attach a Gmail credential (n8n/README.md §4)

# 4) frontend (Phase 6) — ONLY after frontend/Dockerfile exists (see §9)
docker compose up -d frontend
Start-Process http://localhost:5173
```

Everything at once (valid once `frontend/Dockerfile` exists):

```powershell
docker compose up -d --build
```

Notes:

- `n8n` `depends_on` monitor/docproc/ai (`service_healthy`) + backend (`service_started`),
  so `up -d n8n` will start them if they are not running yet.
- The workflow is imported **inactive** — activation is a manual one-time step (auditability).
- Re-importing the workflow creates a duplicate; see `n8n/README.md` §2.

## 3. Service map

| Service | Container | Host port | Health endpoint | Role |
|---|---|---|---|---|
| mysql | regtrack-mysql | 3307 | mysqladmin ping | DB |
| backend | regtrack-backend | 8080 | `/actuator/health` | REST API, webhook ingress |
| extraction-worker | regtrack-extraction-worker | 8000 | `/health` | Phase 2 extraction |
| monitor | regtrack-monitor | 8101 | `/health` | change detection → signed webhook |
| docproc | regtrack-docproc | 8102 | `/health` | PDF/HTML → `storage/processed` |
| ai | regtrack-ai | 8103 | `/health` | analysis → `storage/analysis` |
| n8n | regtrack-n8n | 5678 | `/healthz` | scheduled pipeline + email |
| frontend | regtrack-frontend | 5173 → 80 | `/` | React dashboard (nginx) |

## 4. Environment variables

### Shared (PLAN.md §2.1)

| Var | Default | Used by |
|---|---|---|
| `API_BASE` | `http://localhost:8080` (compose sets `http://backend:8080` in-container) | monitor, ai, n8n |
| `WEBHOOK_SECRET` | `dev-webhook-shared-secret-please-change` | monitor (signing), backend (verifying), n8n |
| `ADMIN_EMAIL` | `admin@regtrack.local` | ai, n8n workflow login, smoke tests |
| `ADMIN_PASSWORD` | `Admin@12345` | ai, n8n workflow login, smoke tests |
| `LLM_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | unset → stub mode | ai |
| `LLM_MODEL` | `gpt-4o-mini` | ai |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | ai |

### Compose-only

| Var | Default | Used by |
|---|---|---|
| `MYSQL_PORT` | `3307` | mysql host port (kept from Phase 1) |
| `JWT_SECRET` | dev value (see docker-compose.yml) | backend |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | backend |
| `FIRECRAWL_API_KEY` / `FIRECRAWL_API_URL` | empty / firecrawl default | extraction-worker, monitor (optional fetch backend) |
| `LLM_BASE_URL` | empty | ai (generic OpenAI-compatible endpoint) |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` (**required** — workflow reads `$env.ADMIN_*`) | n8n |
| `N8N_ENCRYPTION_KEY` | `dev-only-n8n-encryption-key-change-me` | n8n (encrypts stored credentials) |
| `N8N_SECURE_COOKIE` / `N8N_DIAGNOSTICS_ENABLED` | `false` | n8n |
| `TZ` / `GENERIC_TIMEZONE` | `UTC` | n8n schedule timezone |
| `VITE_API_BASE` | `http://localhost:8080` | frontend **build** arg (see §6) |

Secrets are passed only via env with defaults — no secrets are committed. For anything
non-prototype, put real values in an untracked `.env` next to docker-compose.yml
(compose reads it automatically) and change `WEBHOOK_SECRET`/`JWT_SECRET`/`N8N_ENCRYPTION_KEY`.

## 5. Smoke checks

### 5.1 Health

```powershell
Invoke-RestMethod http://localhost:8080/actuator/health   # backend {"status":"UP"}
Invoke-RestMethod http://localhost:8101/health             # monitor
Invoke-RestMethod http://localhost:8102/health             # docproc
Invoke-RestMethod http://localhost:8103/health             # ai
Invoke-RestMethod http://localhost:5678/healthz            # n8n
docker compose ps                                          # statuses / healthchecks
```

### 5.2 Login + authenticated read

```powershell
$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post `
  -ContentType 'application/json' `
  -Body '{"email":"admin@regtrack.local","password":"Admin@12345"}'
$login.token                                        # JWT
$h = @{ Authorization = "Bearer $($login.token)" }
Invoke-RestMethod -Uri http://localhost:8080/api/events -Headers $h   # change events
Invoke-RestMethod -Uri "http://localhost:8080/api/alerts?status=PENDING" -Headers $h
```

curl (Git-Bash / WSL):

```bash
TOKEN=$(curl -sS -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@regtrack.local","password":"Admin@12345"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sS http://localhost:8080/api/events -H "Authorization: Bearer $TOKEN"
```

### 5.3 Signed webhook (ingress ack — expect `202`)

Quick variant (token header, allowed by PLAN §1.2):

```bash
curl -sS -X POST http://localhost:8080/api/webhooks/changedetection \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Token: dev-webhook-shared-secret-please-change' \
  -d '{"url":"https://example.com/rbi/circulardemo","title":"Demo circular","source_code":"RBI","content":"<html><body>demo content v1</body></html>","timestamp":"2026-10-03T12:00:00Z"}'
# → {"eventId":..,"status":"RECEIVED","regulationId":..,"newVersionId":..,"receivedAt":..}
```

Proper HMAC signature variant:

```bash
BODY='{"url":"https://example.com/rbi/circulardemo","title":"Demo circular","source_code":"RBI","content":"<html><body>demo content v1</body></html>","timestamp":"2026-10-03T12:00:00Z"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "dev-webhook-shared-secret-please-change" | sed 's/^.* //')
curl -sS -X POST http://localhost:8080/api/webhooks/changedetection \
  -H 'Content-Type: application/json' \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

Same content posted twice ⇒ second call must NOT create a second event (backend dedupes).

PowerShell equivalent:

```powershell
$body = '{"url":"https://example.com/rbi/circulardemo","title":"Demo circular","source_code":"RBI","content":"<html><body>demo content v1</body></html>","timestamp":"2026-10-03T12:00:00Z"}'
$secret = 'dev-webhook-shared-secret-please-change'
$hmac = New-Object System.Security.Cryptography.HMACSHA256([Text.Encoding]::ASCII.GetBytes($secret))
$hash = [BitConverter]::ToString($hmac.ComputeHash([Text.Encoding]::ASCII.GetBytes($body))).Replace('-', '').ToLower()
Invoke-RestMethod -Uri http://localhost:8080/api/webhooks/changedetection -Method Post `
  -ContentType 'application/json' -Headers @{ 'X-Webhook-Signature' = "sha256=$hash" } -Body $body
```

### 5.4 Pipeline + egress ack (loop close)

```powershell
# 1) send the webhook above → event RECEIVED
# 2) n8n UI → "Regulatory Pipeline" → Execute workflow (or wait for the 15-min schedule)
# 3) execution graph shows: monitor run → login → events → docproc → ai → alerts → gmail → PATCH
# 4) egress ack: alert status must flip PENDING → SENT
$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body '{"email":"admin@regtrack.local","password":"Admin@12345"}'
Invoke-RestMethod -Uri http://localhost:8080/api/alerts -Headers @{ Authorization = "Bearer $($login.token)" } |
  Select-Object id, status, emailRecipients, regulationTitle
```

Until a Gmail credential is attached, sends land in the `Email Send Failed` branch and
alerts stay `PENDING` — that is the safe failure mode (no lost/duplicate acks).

## 6. Frontend API base — choice

**Baked at build time** (Vite inlines `VITE_API_BASE` into the bundle):

- Default `http://localhost:8080` — the value must be reachable from the **browser**, not
  from inside a container, so `backend:8080` would be wrong for host access.
- Matches backend `CORS_ALLOWED_ORIGINS` (`http://localhost:5173`).
- To override: `VITE_API_BASE=https://api.example.com docker compose build frontend`
  (requires the commented `build:` block in docker-compose.yml to be enabled).
- The `frontend.environment.VITE_API_BASE` passthrough is kept for the case where the
  frontend Dockerfile renders a runtime config (nginx `envsubst` template) instead; if the
  Dockerfile is static-only, that env has no effect. Runtime config would avoid rebuilds,
  but the frontend Dockerfile is owned by the frontend agent — see §9.

## 7. Teardown

```powershell
docker compose down                 # stop + remove containers, keep volumes (data kept)
docker compose stop n8n             # stop one service
docker compose logs -f monitor      # tail one service
docker compose down -v              # DESTRUCTIVE: also deletes mysql-data + n8n-data + changedetection-data
```

Port collisions (e.g., something already on 8080/3307) are the usual bring-up failure —
`docker compose ps` + `docker compose logs <service>` first.

## 8. Windows dev-mode alternative (no docker for app services)

Useful while iterating on code — MySQL stays in Docker (Phase 1 ground truth), everything
else runs directly on Windows:

```powershell
# 1) DB (Phase 1 container, host port 3307)
docker compose up -d mysql
# if the legacy regtrack-mysql container is running instead, it already listens on 3307

# 2) backend jar on 8080 (PLAN §1 — read-only reference, do not modify backend/)
cd D:\AI_Hack\backend
$env:DB_URL = 'jdbc:mysql://localhost:3307/regtrack?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC&characterEncoding=UTF-8'
$env:DB_USER = 'regtrack'; $env:DB_PASSWORD = 'regtrack'
$env:WEBHOOK_SECRET = 'dev-webhook-shared-secret-please-change'
.\mvnw.cmd spring-boot:run
#  or, if already built: java -jar target\regtrack-backend-0.0.1-SNAPSHOT.jar
#  (API on http://localhost:8080, defaults seeded: admin@regtrack.local / Admin@12345)

# 3) python services via the shared venv (each folder has its own README/CLI; HTTP wrappers:)
cd D:\AI_Hack\services\monitor
D:\AI_Hack\.venv\Scripts\uvicorn.exe monitor.service:app --port 8101      # + GET /health
cd D:\AI_Hack\services\docproc
D:\AI_Hack\.venv\Scripts\uvicorn.exe docproc.api:app --port 8102
cd D:\AI_Hack\services\ai
D:\AI_Hack\.venv\Scripts\uvicorn.exe ai.server:app --port 8103
# CLI equivalents: python -m monitor.main (see services/*/README.md)
# Remember: in dev mode API_BASE defaults to http://localhost:8080 (correct for host mode)

# 4) frontend dev server (Vite, 5173)
cd D:\AI_Hack\frontend
npm install
npm run dev                        # VITE_API_BASE from .env (default http://localhost:8080)

# 5) n8n — docker is the supported mode; on-host alternative:
npx n8n@latest start               # http://localhost:5678
npx n8n@latest import:workflow --input=D:\AI_Hack\n8n\workflows\regulatory-pipeline.json
# CAUTION: the workflow URLs use docker-internal DNS (monitor:8101, backend:8080, ...).
# On host mode they do not resolve — either keep n8n in docker, or edit the workflow URLs
# to localhost. The service ports are identical (8101/8102/8103/8080).
```

Checks in dev mode: `Invoke-RestMethod http://localhost:8080/actuator/health`, the three
service `/health` endpoints, and `Invoke-RestMethod http://localhost:5678/healthz`.

## 9. Known pending items

- **`frontend/Dockerfile` does not exist yet** (frontend agent owns `frontend/**`).
  The compose service is present with an `image: regtrack-frontend:local` placeholder and a
  **commented `build:` stanza** — enable it (and run `docker compose up -d frontend`) once
  the file lands. Expected shape: multi-stage `node:20-alpine` (`npm ci && npm run build`
  with `ARG VITE_API_BASE`) → `nginx:alpine` serving `dist/` on port 80.
  Until then, run the frontend with `npm run dev` (§8) or omit `frontend` from compose.
- `services/monitor`, `services/docproc`, `services/ai` all ship their own Dockerfiles
  (active `build:` stanzas in docker-compose.yml).
- n8n workflow requires a one-time Gmail credential attach + activation (`n8n/README.md` §4).
- Volumes hold state: `mysql-data`, `n8n-data` (workflow + watermark + credentials),
  `changedetection-data`, plus the host `./storage` tree (PLAN §2.3).
