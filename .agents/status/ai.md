---
role: ai
status: DONE
updated: 2026-10-03T08:30:00Z
---
## Artifacts
- services/ai/ai/llm.py — OpenAI-compatible client (OPENAI_API_KEY / GEMINI_API_KEY+GEMINI_BASE_URL / LLM_API_KEY, LLM_MODEL, timeout+retries, JSON mode) + deterministic StubLLM (regex effective dates, SHALL/MUST obligations, numbered headings, gazette/notification numbers, penalty-based risk) + ResilientLLM total-fallback wrapper
- services/ai/ai/embeddings.py — paragraph chunking (1200/200), hashed 256-dim embeddings, ChromaDB store (`storage/chroma`, collection `regulations`, cosine, guarded import) + JSONL cosine fallback store, `get_vector_store()` factory that never raises
- services/ai/ai/relevance.py — live profile fetch (login → /api/companies → /{id}/profile) + pure scoring fn: 0.35 regulator-body + 0.40 sector + 0.15 jurisdiction + 0.10 keyword overlap → HIGH/MEDIUM/LOW/NONE with rationale; bodies inferred from sectors when profile empty
- services/ai/ai/analyze.py — text loading (storage/processed → backend content fallback), difflib diff, prompt build, §2.4 assembly+validation, persistence to `storage/analysis/<id>/v<n>.json`, vector indexing
- services/ai/ai/emit.py — event resolution (arg → newest GET /api/alerts match) + POST /api/alerts per non-NONE entry, report {verified|deferred|skipped}
- services/ai/ai/client.py, config.py — shared backend HTTP client (admin bearer, one re-login retry, HTML strip) and lazy env config
- services/ai/ai/main.py — CLI `python -m ai.main --regulation-id N --version N [--event-id E] [--no-emit] [--offline] [--quiet]`
- services/ai/ai/server.py — FastAPI §2.5 wrapper: `POST /analyze`, `GET /health`, port 8103
- services/ai/tests/{conftest,sample_data,test_analysis_contract,test_llm_stub,test_relevance,test_vector_store,test_emit}.py — 42 offline tests
- services/ai/{Dockerfile,requirements.txt,README.md,conftest.py} — owned packaging
- docs/ai-analysis.md — architecture, scoring model, frontend rendering guide, limitations
- storage/analysis/1/v6.json, storage/chroma/** — live run output (ai-owned subfolders per §2.3)

## Verification
- `D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services` → COMPILEALL OK (exit 0)
- `D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\ai -q` → **42 passed in 1.36s** (also verified via `pytest D:\AI_Hack\services\ai\tests -q`). Covers: every §2.4 key present in StubLLM JSON (round-trips through json.dumps/loads), old_version_missing flag, relevance unit tests with fake profiles (HIGH/NONE/jurisdiction-mismatch/industry fallback), chroma AND jsonl round-trip (embed → query → found) + forced-chroma-failure fallback, stub rules (date/obligation/heading/reference/risk), provider selection for all 3 key env vars, emit payload shape + deferred/skipped paths. Tests are fully offline (API_BASE pointed at closed port, AI_FORCE_STUB=1, per-test tmp storage).
- Live smoke: `POST http://localhost:8080/api/auth/login` `{admin@regtrack.local, Admin@12345}` → **200, token, role ADMIN**
- Live smoke: `python -m ai.main --regulation-id 1 --version 6` (workdir services/ai) → exit 0, analysis JSON on stdout (analysis_mode=stub, model=stub-rules, event_id resolved, relevance[] for 89 live companies, chroma backend, 2 chunks indexed); storage/analysis/1/v6.json written
- Live smoke (alert emission VERIFIED): script called `emit_alerts(..., event_id=66)` against localhost:8080 → `{"status":"verified","emitted":[13],"reason":"1 alert(s) created for event 66"}` — POST /api/alerts accepted the exact DTO
- Live smoke (HTTP): uvicorn ai.server:app on 8103 → `GET /health` 200 `{"status":"ok",...}`; `POST /analyze {"regulation_id":1,"version_no":6,"emit":false}` → **200** with all 13 §2.4 keys
- No pip installs run; no files touched outside services/ai/**, docs/ai-analysis.md, .agents/status/ai.md, storage/{analysis,chroma}

## Handoff notes
- **Exact analysis JSON (§2.4)** written to `storage/analysis/<regulationId>/v<n>.json` and returned by `POST /analyze`:
  `regulation_id, version_no, event_id, analysis_mode("llm"|"stub"), model, summary, key_changes[], affected_entities[], effective_date("YYYY-MM-DD"|null), required_actions[], risk_level("HIGH"|"MEDIUM"|"LOW"), relevance[{company_id, company_name, level("HIGH"|"MEDIUM"|"LOW"|"NONE"), rationale}], generated_at(ISO8601 Z)`
  plus `old_version_missing: true` **only when** `v<n-1>` is absent (frontend: show "compared against current version only").
- **Frontend rendering**: badge `analysis_mode` (stub = rules-derived, non-advisory) beside `model`; colour by `risk_level`; per-company chips from `relevance[].level`; `effective_date` null → "not specified"; `key_changes`/`required_actions`/`affected_entities` are clean `string[]` (≤400 chars each) → lists/timelines; `rationale` (one sentence incl. score+evidence) → tooltip. Nothing outside these keys is emitted (no extras except the sanctioned `old_version_missing`).
- **Alert emission state: LIVE VERIFIED.** For every `relevance.level != NONE` → `POST /api/alerts` as admin with DTO `{companyId, changeEventId, relevance, summary, affectedAreas, effectiveDate, requiredAction, emailRecipients}` (email from profile.complianceContactEmail). Report: `verified` (alert ids), `deferred` (no matching event / backend write failed / reasons), `skipped` (all NONE or --no-emit). CLI prints report to **stderr** (stdout = pure JSON).
- **For monitor/n8n/ops**: ALWAYS pass `event_id` to `/analyze` (webhook 202 returns `eventId`). `GET /api/events` only returns the last 50 events and cannot filter by regulation → older regulations resolve `event_id=null` and emission is `deferred` (observed live on regulation 1 after 66 events piled up).
- **Assumptions recorded** (per ACK §0.5): backend contract held as specified; profile fields `industry_sectors/regulatory_bodies/jurisdictions` are currently null on seeded companies → scoring falls back to `company.industry` + sector↔source inference (works, see live run rationales). ChromaDB 1.5.9 API used: `get_or_create_collection(..., metadata={"hnsw:space":"cosine"})` + `query(query_embeddings=...)` with explicit hash embeddings (no ONNX model download, fully offline).
- Backend alert row created during smoke: **alert id 13** (event 66, company 1, HIGH) — intentional test data, harmless to other roles.

## Extra deps / unresolved issues
- extra-deps: none (all packages pre-installed: chromadb 1.5.9, openai 3.24.0, fastapi, uvicorn, requests, python-dotenv, pytest).
- unresolved: (1) `/api/events` last-50 limitation above — needs a backend filter (`?regulationId=`) for reliable auto-resolution of old events; (2) all live companies currently score HIGH against RBI circulars because their industry is "Banking & NBFC" — thresholds are tunable in `ai/relevance.py` (HIGH≥0.62) if QA/frontend prefer fewer HIGH badges; (3) hash embeddings are lexical — swap `embed_text()` when an offline semantic model is provisioned.
