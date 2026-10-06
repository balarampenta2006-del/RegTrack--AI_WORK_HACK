# regtrack-ai — AI Analysis & Relevance Detection (Phase 4)

Python service that turns a raw regulation version diff into the machine-readable
analysis contract of `PLAN.md §2.4`, scores company relevance, indexes texts into
a vector store and emits alerts to the backend.

```
storage/processed/<id>/v<n>.txt ─┐
                                 ├─> diff ─> LLM (or StubLLM) ──┐
backend GET /api/regulations/... ─┘                             ├─> §2.4 JSON ─> storage/analysis/<id>/v<n>.json
                                                                 ├─> relevance[] (profiles vs keywords) 
storage/chroma (regulations)  <── chunk + upsert (RAG index) ────┤
                                                                 └─> POST /api/alerts (level != NONE)
```

## Layout

| File | Responsibility |
|---|---|
| `ai/llm.py` | OpenAI-compatible client (OPENAI/GEMINI/LLM key), JSON mode, timeout+retries, deterministic `StubLLM` fallback |
| `ai/embeddings.py` | chunking, hashed embeddings, ChromaDB store (`storage/chroma`, collection `regulations`) + JSONL cosine fallback |
| `ai/relevance.py` | company profiles from the live backend → `HIGH\|MEDIUM\|LOW\|NONE` + rationale |
| `ai/analyze.py` | text loading (storage → backend fallback), diff, prompt, validation, persistence |
| `ai/emit.py` | event resolution + `POST /api/alerts` per non-NONE entry |
| `ai/main.py` | CLI `python -m ai.main` |
| `ai/server.py` | FastAPI wrapper, port **8103** (`POST /analyze`, `GET /health`) |
| `ai/client.py` | thin authenticated HTTP client for the Spring Boot backend |

## Usage

```powershell
# CLI (from services/ai)
D:\AI_Hack\.venv\Scripts\python.exe -m ai.main --regulation-id 1 --version 6 [--event-id 7] [--no-emit] [--offline] [--quiet]

# HTTP service
D:\AI_Hack\.venv\Scripts\python.exe -m uvicorn ai.server:app --port 8103
curl -X POST http://localhost:8103/analyze -H "Content-Type: application/json" `
     -d '{"regulation_id":1,"version_no":6,"event_id":7}'

# tests (offline, no network, no API key needed)
D:\AI_Hack\.venv\Scripts\python.exe -m pytest tests -q
```

## Environment (PLAN.md §2.2)

| Var | Default | Notes |
|---|---|---|
| `API_BASE` | `http://localhost:8080` | docker: `http://backend:8080` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@regtrack.local` / `Admin@12345` | alert emission + profile reads |
| `OPENAI_API_KEY` | unset | provider 1 (OpenAI) |
| `GEMINI_API_KEY` | unset | provider 2, uses `GEMINI_BASE_URL` |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Gemini OpenAI-compat endpoint |
| `LLM_API_KEY` / `LLM_BASE_URL` | unset | generic OpenAI-compatible provider |
| `LLM_MODEL` | `gpt-4o-mini` | model for any provider |
| `AI_TIMEOUT` / `AI_RETRIES` | `60` / `2` | client timeout + retries |
| `AI_FORCE_STUB` | unset | force deterministic stub mode |
| `STORAGE_ROOT` / `CHROMA_DIR` | `<repo>/storage` / `<repo>/storage/chroma` | data locations |

**No key / provider failure ⇒ automatic `StubLLM` fallback** (`analysis_mode:"stub"`,
`model:"stub-rules"`). The pipeline never crashes because of LLM credentials.

## Output contract (PLAN.md §2.4)

Written to `storage/analysis/<regulationId>/v<version>.json` and returned by
`POST /analyze`:

```json
{"regulation_id":1,"version_no":2,"event_id":7,"analysis_mode":"llm|stub",
 "model":"gpt-4o-mini|stub-rules","summary":"...",
 "key_changes":["..."],"affected_entities":["..."],
 "effective_date":"YYYY-MM-DD|null","required_actions":["..."],
 "risk_level":"HIGH|MEDIUM|LOW",
 "relevance":[{"company_id":1,"company_name":"...","level":"HIGH|MEDIUM|LOW|NONE","rationale":"..."}],
 "generated_at":"2026-10-03T12:00:00Z"}
```

`old_version_missing: true` is added when `v<n-1>` does not exist (analysis then
uses `v<n>` alone).

## Docker

```bash
docker build -t regtrack-ai services/ai
docker run -p 8103:8103 -e API_BASE=http://backend:8080 -v <storage>:/storage regtrack-ai
```
