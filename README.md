# RegTrack — Regulatory Update Tracking for Legal/Compliance Teams

Continuously monitors official government sources (MCA / RBI / SEBI) for regulatory
changes, versions documents (new vs. old), runs AI analysis (what changed, who is
affected, effective date, required action), scores relevance against your company
profile, and alerts the right compliance team by email — all behind a secured API
and React dashboard.

## Architecture

```
        ┌─────────────────────────────────────────────────────────┐
        │                  Official regulators (MCA/RBI/SEBI)       │
        └──────┬──────────────────────┬──────────────────────┬─────┘
               │                      │                      │
      ChangeDetection.io        monitor (8101)         extraction-worker (8000)
               │                      │  (hourly poll + HMAC webhook)
               ▼                      ▼
                          POST /api/webhooks/changedetection
                                        │  (HMAC-SHA256 signed)
                                        ▼
                    ┌────────────────────────────────────┐
                    │  backend (Spring Boot, :8080)        │
                    │  JWT API · webhook · versions ·      │
                    │  alerts · audit · event store        │
                    └───────┬──────────────┬─────────────┘
                            │              │
                     MySQL 8.4        docproc (8102)
                     (3307 host)   PyMuPDF + OCR + clean
                            │              │
                            │              ▼ storage/processed
                            │         ai (8103)
                            │      LLM + RAG (ChromaDB) + relevance
                            │              │
                            ▼              ▼
                 n8n (5678): schedule → monitor → docproc → ai → Gmail → mark SENT
                            │
                            ▼
             frontend (:5173) — dashboards, analysis, audit, company profile
```

## Stack

| Layer | Tech |
|---|---|
| Backend | Java 21 · Spring Boot 4.1 · Spring Security 7 · Flyway |
| Database | MySQL 8.4 (compose), JPA entities + `validate` |
| Change detection | ChangeDetection.io · custom `services/monitor` (httpx+BS4, optional Playwright/Firecrawl) |
| Web extraction | `extraction-worker` (BS4 + Firecrawl + Playwright) |
| Documents | `services/docproc` (PyMuPDF, Tesseract OCR, cleaning/normalization) |
| AI | `services/ai`: OpenAI/Gemini-compatible LLM client, ChromaDB RAG, relevance scoring, stub fallback without keys |
| Automation | n8n (`n8n/workflows/regulatory-pipeline.json`), Gmail node |
| Dashboard | React 19 + TS + Vite, nginx in Docker |
| Security | JWT (jjwt), HMAC-SHA256 webhook auth, role-based access (ADMIN / COMPLIANCE_OFFICER / VIEWER), BCrypt |
| Packaging | Docker + docker-compose (10 services) |

## Quickstart

```powershell
cd D:\AI_Hack
docker compose up -d --build      # first run builds all images
docker compose ps                 # verify all healthy
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8080 (`/actuator/health`)
- n8n: http://localhost:5678 (first visit → create owner account → workflow
  *Regulatory Pipeline* is pre-imported but inactive: activate + attach Gmail
  credentials)
- ChangeDetection.io: http://localhost:5000
- Default admin login: `admin@regtrack.local` / `Admin@12345` (dev only)
- Webhook test signing secret: `dev-webhook-shared-secret-please-change`

Trigger a manual pipeline run: `POST http://localhost:8101/run` (monitor),
or call the signed webhook directly — see `docs/monitoring.md`.

## Configuration (env, compose defaults shown)

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | dev-only value | HMAC key for API tokens — **change for deploy** |
| `WEBHOOK_SECRET` | dev-only value | shared secret for webhook signatures |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | above | seeded admin + service calls |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | unset | real LLM analysis; unset → deterministic stub mode |
| `LLM_MODEL` | `gpt-4o-mini` | model name |
| `FIRECRAWL_API_KEY` | unset | Firecrawl-backed extraction |
| `MYSQL_PORT` | `3307` | host port for MySQL (local MySQL on 3306 is unaffected) |

## Development (no Docker for backend)

```powershell
# terminal 1: MySQL only
docker compose up -d mysql
# terminal 2: backend (dev defaults match compose)
cd backend; .\mvnw.cmd spring-boot:run
# frontend dev server
cd frontend; npm install; npm run dev
# python services
D:\AI_Hack\.venv\Scripts\python.exe -m uvicorn monitor.service:app --port 8101
```

## Testing

```powershell
# backend unit tests
cd backend; .\mvnw.cmd test
# API end-to-end (33 checks, idempotent)
powershell -File scripts\e2e-phase1.ps1
# python contract/accuracy/security suites — see docs\test-report.md
D:\AI_Hack\.venv\Scripts\python.exe -m pytest tests -q
```

## Security model

- All endpoints authenticated except `/api/auth/*`, `/api/webhooks/*`, `/actuator/health`.
- Webhook authenticity via per-request HMAC-SHA256 of the raw body (timing-safe compare).
- Roles: `ADMIN` (everything), `COMPLIANCE_OFFICER` (own company data), `VIEWER`.
- BCrypt password hashing, audit log for logins/webhook receipts/alert lifecycle.
- ⚠ Known gaps before production: dev-default secrets, no TLS/WAF, local-only admin.
  Full review with severity ratings: `docs/security-review.md`.

## Repository layout

```
backend/               Spring Boot API (Phase 1)
frontend/              React dashboard (Phase 6)
services/monitor/      Phase 2 change detection
services/docproc/      Phase 3 document extraction
services/ai/           Phase 4 analysis/RAG/relevance
extraction-worker/     BS4/Firecrawl/Playwright extraction API
n8n/workflows/         Phase 5 pipeline definition
tests/                 pytest contract, security, accuracy suites
scripts/e2e-phase1.ps1 full API verification (33 checks)
docs/                  per-phase docs + security review + test report
.agents/PLAN.md        parallel-agent build coordination (see below)
```

## Docs index

`docs/monitoring.md` · `docs/document-processing.md` · `docs/ai-analysis.md` ·
`docs/dashboard.md` · `docs/operations.md` · `docs/security-review.md` ·
`docs/test-report.md` · `docs/known-issues.md`

## Multi-agent build note

This codebase was assembled by 6 parallel opencode subagents (`monitor`, `docproc`,
`ai`, `frontend`, `ops`, `qa`) coordinated via `.agents/PLAN.md` with per-agent
status files in `.agents/status/` (all `DONE`). 14 agent definitions are installed
globally at `~/.config/opencode/agents/` — restart opencode to use them by name.

## Roadmap

- [ ] Rotate dev secrets + TLS ingress (production profile)
- [ ] Activate + Gmail-pair the n8n workflow; run a live 15-min cycle
- [ ] LLM keys in env for real analysis; tune `services/ai` relevance thresholds
- [ ] ChangeDetection.io watches provisioned with HMAC webhook →
      `{API_BASE}/api/webhooks/changedetection`
- [ ] Prometheus/Grafana dashboards (actuator metrics)
