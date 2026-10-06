# Parallel Agent Coordination Plan — Regulatory Update Tracking
Project root: `D:\AI_Hack` · Created by the orchestrator for parallel background execution.

## 0. ACK PROTOCOL (mandatory for every agent)

1. READ this entire file before any other work.
2. FIRST write action: create `.agents/status/<your-role>.md` with `status: STARTED` (template §5).
3. Only write inside paths you OWN (§4). Never edit another role's files or status file.
4. LAST action before finishing: flip your status file to `DONE` (or `BLOCKED`) with artifacts, verification run, handoff notes, unresolved issues.
5. Do NOT wait/blocked on upstream agents — build strictly against the contracts in §2.
   If upstream is not DONE, assume the contract holds and record the assumption.
6. Python deps live in shared venv `D:\AI_Hack\.venv` (pre-installed). Do NOT run pip install;
   if you need an extra package, write `extra-deps:` in your status file instead.
7. This shared file system is the ONLY channel between agents. Files = acknowledgement.

## 1. SYSTEM GROUND TRUTH (Phase 1 — already built, do not modify `backend/`)

- Backend: Spring Boot 4.1.1, Java 21, source `D:\AI_Hack\backend`, jar
  `backend/target/regtrack-backend-0.0.1-SNAPSHOT.jar`, runs on **http://localhost:8080** (live during dev).
- MySQL: docker container `regtrack-mysql`, host port **3307**, db/user/pass `regtrack`.
- Seeded admin: `admin@regtrack.local` / `Admin@12345` (role ADMIN).
- Seeded sources: codes `MCA`, `RBI`, `SEBI`.
- Units already verified by `scripts/e2e-phase1.ps1` (31/33; known non-idempotent test-data bug — QA owns the fix).

### 1.1 Backend API (Bearer JWT)
| Method | Path | Notes |
|---|---|---|
| POST | /api/auth/login | {email,password} → {token,expiresInSeconds,user{id,email,role,companyId,companyName}} |
| POST | /api/auth/register | optional companyName creates company + profile |
| GET | /api/me | current user |
| GET/POST/PUT | /api/companies, /{id}, /{id}/profile | POST/PUT company = ADMIN; profile PUT = owner or ADMIN |
| GET/POST/PUT | /api/sources, /{id} | write = ADMIN |
| GET | /api/regulations[?source=RBI], /{id}, /{id}/versions, /{id}/versions/{vid} | version detail includes full `content` |
| GET | /api/events | last 50 change events |
| GET/POST | /api/alerts, PATCH /{id}/status {status} | scoping: officer=own company, ADMIN=all |
| GET | /api/audit?action=LOGIN | ADMIN only |
| GET | /actuator/health | public |

Errors: JSON `{timestamp,status,error,message[,fields]}`. 401 unauth, 403 forbidden, 404 not found, 409 conflict.

### 1.2 Secured webhook (used by monitor role)
```
POST {API_BASE}/api/webhooks/changedetection
Headers: X-Webhook-Signature: sha256=<hex hmac-sha256(rawBody, WEBHOOK_SECRET)>
   (or X-Webhook-Token: <WEBHOOK_SECRET>)
Body (JSON, ASCII-safe):
{"url":"https://www.rbi.org.in/...","title":"...","source_code":"RBI",
 "content":"<html or extracted text>","timestamp":"2026-10-03T12:00:00Z"}
→ 202 {"eventId","status","regulationId","newVersionId","receivedAt"}
```
Same content+hash twice ⇒ no new version (backend dedupes). `WEBHOOK_SECRET` default:
`dev-webhook-shared-secret-please-change`.

## 2. CROSS-ROLE CONTRACTS

### 2.1 Env vars (shared)
| Var | Default | Used by |
|---|---|---|
| API_BASE | http://localhost:8080 (docker: http://backend:8080) | all |
| WEBHOOK_SECRET | dev-webhook-shared-secret-please-change | monitor |
| ADMIN_EMAIL / ADMIN_PASSWORD | admin@regtrack.local / Admin@12345 | ai, n8n, frontend smoke |
| LLM_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY | unset → stub mode | ai |
| LLM_MODEL | gpt-4o-mini | ai |
| GEMINI_BASE_URL | https://generativelanguage.googleapis.com/v1beta/openai/ | ai |

### 2.2 Ports
8080 backend · 3307 mysql · 5173 frontend dev · 8101 monitor · 8102 docproc · 8103 ai · 5678 n8n.

### 2.3 Storage layout (shared, own only your subfolder)
```
D:\AI_Hack\storage\
  snapshots\<source-code>\          monitor: latest.txt/html + history
  raw\                             docproc: downloaded originals
  processed\<regulationId>\v<n>.txt docproc output (+ manifest.json, see below)
  analysis\<regulationId>\v<n>.json ai output
  chroma\                          ai: vector persist dir
  logs\
```
manifest.json (docproc → ai):
```json
{"regulation_id":1,"version_no":2,"source":"RBI","source_url":"https://...",
 "method":"html|pdf|ocr","content_path":"storage/processed/1/v2.txt",
 "content_sha256":"...","char_count":1234,"ocr_used":false,
 "extracted_at":"2026-10-03T12:00:00Z","pipeline_version":"1.0"}
```

### 2.4 Analysis contract (ai → frontend / alerts)
```json
{"regulation_id":1,"version_no":2,"event_id":7,"analysis_mode":"llm|stub",
 "model":"gpt-4o-mini|stub-rules","summary":"...",
 "key_changes":["..."],"affected_entities":["..."],
 "effective_date":"YYYY-MM-DD|null","required_actions":["..."],
 "risk_level":"HIGH|MEDIUM|LOW",
 "relevance":[{"company_id":1,"company_name":"...","level":"HIGH|MEDIUM|LOW|NONE",
 "rationale":"..."}],
 "generated_at":"2026-10-03T12:00:00Z"}
```
Old text for diff = `storage/processed/<regId>/v<n-1>.txt` (if missing: analyze v<n> alone, note `old_version_missing:true`).

### 2.5 Service HTTP surface (thin FastAPI wrapper over each CLI; docker-internal names in parens)
- monitor (8101): `POST /run` → `{"checked":n,"changed":[url...]}`, `GET /health`
- docproc (8102): `POST /process` `{input, regulation_id, version_no, source}` → manifest JSON
- ai (8103): `POST /analyze` `{regulation_id, version_no, event_id?}` → analysis JSON

## 3. ROLE ASSIGNMENTS (6 parallel agents)

| role | persona (installed) | phase | scope |
|---|---|---|---|
| monitor | `~/.config/opencode/agents/python-pro.md` | 2 | change detection & retrieval |
| docproc | `~/.config/opencode/agents/python-pro.md` | 3 | PDF/OCR extraction & cleaning |
| ai | `~/.config/opencode/agents/ai-engineer.md` + `llm-architect.md` | 4 | LLM analysis, RAG, relevance |
| frontend | `~/.config/opencode/agents/react-specialist.md` | 6 | React dashboard |
| ops | `~/.config/opencode/agents/devops-engineer.md` | 5+7 | n8n workflow, docker compose |
| qa | `~/.config/opencode/agents/test-automator.md` + `security-auditor.md` | 7 | tests, security review, report |

Read your persona file for style/checklists; this plan defines WHAT to build.

## 4. OWNERSHIP (write only here)
```
services/monitor/**            → monitor        (incl. its Dockerfile, requirements.txt, README)
services/docproc/**            → docproc
services/ai/**                 → ai
frontend/**                    → frontend
docker-compose.yml, n8n/**     → ops            (ops may ADD services/*/Dockerfile only if missing, note it)
tests/**, docs/security-review.md, docs/known-issues.md, docs/test-report.md → qa
docs/monitoring.md, docs/document-processing.md, docs/ai-analysis.md,
docs/dashboard.md, docs/operations.md                      → respective role above
.storage owned per §2.3 subfolders. backend/**, scripts/e2e-phase1.ps1 → OFF LIMITS (read-only).
```

## 5. STATUS FILE TEMPLATE — `D:\AI_Hack\.agents\status\<role>.md`
```markdown
---
role: <role>
status: STARTED | DONE | BLOCKED
updated: <ISO-8601>
---
## Artifacts
- path — what it is
## Verification
- exact commands run + results
## Handoff notes
- what downstream roles must know / assumptions made
## Extra deps / unresolved issues
- (or "none")
```

## 6. VERIFICATION COMMANDS
```powershell
# python (all services)
D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q
# frontend
cd D:\AI_Hack\frontend; npm run build
# compose
cd D:\AI_Hack; docker compose config -q
# backend (read-only reference)
cd D:\AI_Hack\backend; .\mvnw.cmd -q test
```
Venv packages pre-installed: requests, httpx, beautifulsoup4, lxml, pymupdf, pillow, pytesseract,
fastapi, uvicorn, python-dotenv, pyyaml, openai, pytest (+chromadb if available — guard imports,
hash-embedding fallback required).
Tesseract binary is NOT installed → OCR must degrade gracefully (`ocr_used:false`, method noted).
Playwright NOT installed → guarded optional import.
