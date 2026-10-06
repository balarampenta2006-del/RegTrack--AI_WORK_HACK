# AI Analysis & Relevance Detection (`services/ai`)

Phase 4 of the regulatory-update-tracking prototype. The service converts a
regulation version change into the §2.4 analysis contract, scores per-company
relevance, maintains a RAG vector index and emits alerts.

## 1. Pipeline

```
POST /analyze {regulation_id, version_no, event_id?}     (or python -m ai.main)
  │
  ├─ 1. meta       GET /api/regulations/{id}            → title, sourceCode
  ├─ 2. texts      storage/processed/<id>/v<n>.txt       (fallback: backend
  │                 + v<n-1>.txt                          version content, HTML-stripped)
  ├─ 3. diff       difflib.unified_diff                  → added/removed lines
  ├─ 4. extract    LLM (JSON mode) or StubLLM            → summary, key_changes,
  │                                                  affected_entities, effective_date,
  │                                                  required_actions, risk_level
  ├─ 5. relevance  GET /api/companies + /{id}/profile    → relevance[] per company
  ├─ 6. validate   every §2.4 key present, enums checked → storage/analysis/<id>/v<n>.json
  ├─ 7. index      chunk old/new → upsert                → storage/chroma (regulations)
  └─ 8. emit       POST /api/alerts for level != NONE    → emission report (stderr / log)
```

If the old version is absent, the new text is analyzed alone and the result
carries `"old_version_missing": true`.

## 2. LLM integration (`ai/llm.py`)

Provider selection order (PLAN §2.2):

1. `OPENAI_API_KEY` — official OpenAI endpoint (or `OPENAI_BASE_URL`)
2. `GEMINI_API_KEY` — Gemini OpenAI-compatible endpoint
   (`GEMINI_BASE_URL`, default `https://generativelanguage.googleapis.com/v1beta/openai/`)
3. `LLM_API_KEY` + optional `LLM_BASE_URL` — any OpenAI-compatible gateway
4. none of the above — **StubLLM immediately**

All real calls: `temperature=0`, `response_format={"type":"json_object"}`
(retried once without it for gateways that reject the parameter), client-level
timeout (`AI_TIMEOUT`, default 60 s) and retries (`AI_RETRIES`, default 2).

`ResilientLLM` wraps the provider and **never raises**: any exception (auth,
network, malformed JSON, missing package) is logged and the request is served by
`StubLLM` for the rest of the process. The resulting analysis is then marked
`analysis_mode:"stub"` / `model:"stub-rules"` so the frontend can badge it.

### StubLLM rules (deterministic, unit-tested)

| Field | Rule |
|---|---|
| `effective_date` | regexes for ISO (`2026-11-01`), `1 November 2026`, `November 1, 2026` **and** a context window (`effective`, `w.e.f.`, `with effect from`, `comes into force`, …) → normalized `YYYY-MM-DD` or `null` |
| `required_actions` | sentences containing `SHALL/MUST/should/is required to/may not` + compliance-by-date line when a date exists + reference-verification line |
| `key_changes` | unified-diff added lines; when no old version exists → numbered/ALL-CAPS section headings |
| `affected_entities` | dictionary of common regulated-entity terms (banks, NBFCs, listed entities, intermediaries, LSPs, …); falls back to `entities regulated by <SOURCE>` |
| reference numbers | `Notification No. …`, `F.No. …`, `G.S.R. …(E)`, `RBI/YYYY-YY/NNN`, `DOR.…` patterns |
| `risk_level` | `HIGH` ≥ 3 penalty words or `show cause`; `MEDIUM` if penalties/obligations exist; else `LOW` |

Every path is normalized through `normalize_analysis_fields()` so stub and LLM
output have identical types before validation.

## 3. RAG / vector store (`ai/embeddings.py`)

* **Chunking** — paragraph-aware, 1200 chars with 200-char overlap; ids
  `<regulation_id>:v<n>:old|new:<chunk_index>` (idempotent upserts).
* **Embeddings** — deterministic hashed bag-of-words (256-dim, L2-normalized,
  `sha1` token hashing with sign spreading). No network, identical on every run.
* **ChromaDB** (v1.5.9) — `PersistentClient` at `storage/chroma`, collection
  `regulations` created with `{"hnsw:space":"cosine"}`; explicit embeddings are
  passed to `upsert`/`query` so no embedding model download is required.
  Similarity is reported as `1 - cosine_distance`.
* **Fallback** — if `chromadb` import/open/query fails for any reason,
  `JsonlVectorStore` takes over: same interface (`upsert/query/count`),
  JSONL persistence (`storage/chroma/regulations.jsonl`) and cosine similarity
  over the same hash embeddings. `get_vector_store()` performs the switch and
  never raises; the chosen backend is reported in the indexing result
  (`{"ok":true,"backend":"chroma|jsonl","chunks":N}`).
* Indexing failures never fail an analysis — they are caught and reported.

## 4. Relevance scoring (`ai/relevance.py`)

Inputs: `GET /api/companies` + `GET /api/companies/{id}/profile`
(auth via `POST /api/auth/login` with `ADMIN_EMAIL`/`ADMIN_PASSWORD`).

Profile signals (snake_case contract names, camelCase aliases accepted):
`industry_sectors`, `regulatory_bodies`, `jurisdictions` — falling back to the
company's `industry` field; regulator bodies are **inferred from sectors**
(banking/NBFC/fintech → RBI, securities/listed → SEBI, company/corporate → MCA)
when the profile leaves them empty.

```
score = 0.35·body      (declared/inferred regulator vs regulation source)
      + 0.40·sector    (sector phrase vs regulation text / keywords / source hints)
      + 0.15·jurisdiction (neutral 0.5 when undeclared; ×0.6 score penalty when declared and mismatched)
      + 0.10·keyword   (token overlap of sectors+bodies with the regulation context)
```

Thresholds: `≥0.62 HIGH`, `≥0.38 MEDIUM`, `≥0.18 LOW`, else `NONE`.
`build_context()` derives the keyword set from the analysis
summary/key_changes/required_actions filtered to terms actually present in the
regulation text — so scoring is anchored in the document, not the model output
alone. Each entry carries a human-readable `rationale` with the evidence.

## 5. Alert emission (`ai/emit.py`)

For every `relevance[]` entry whose `level != NONE`:

1. Resolve `changeEventId`: CLI/API argument → otherwise newest
   `GET /api/events` entry whose `regulationId` matches.
2. `POST /api/alerts` (admin Bearer token) with the exact backend DTO:
   `{companyId, changeEventId, relevance, summary, affectedAreas, effectiveDate,
   requiredAction, emailRecipients}` — `emailRecipients` comes from the profile's
   `complianceContactEmail`.

Emission report states:

| status | meaning |
|---|---|
| `verified` | at least one alert row created (ids listed in `emitted[]`) |
| `deferred` | no matching change event, or the backend write failed — reasons in `deferred[]` |
| `skipped` | all entries are `NONE`, `--no-emit`, or offline mode |

The report is printed to **stderr** by the CLI (stdout stays pure analysis JSON)
and logged by the HTTP service.

## 6. HTTP surface (§2.5)

| Method | Path | Body / response |
|---|---|---|
| POST | `/analyze` | `{regulation_id, version_no, event_id?, emit?}` → §2.4 analysis JSON (422 = missing content, 502 = backend failure) |
| GET | `/health` | `{"status":"ok","service":"ai","version":"1.0.0"}` |

## 7. Frontend rendering guide

* Badge `analysis_mode` (`stub` = rules-derived, non-advisory) next to `model`.
* `risk_level` → severity colour; `relevance[].level` → per-company alert badge.
* `effective_date` is `YYYY-MM-DD` or `null` — render "not specified" for `null`.
* `key_changes`, `required_actions`, `affected_entities` are plain `string[]`
  (already truncated ≤400 chars) — safe for list/timeline rendering.
* `rationale` is a single sentence with the score and evidence — tooltip content.
* `old_version_missing: true` (present only when applicable) → show
  "compared against current version only" hint.

## 8. Known limitations

* `GET /api/events` returns only the **last 50** events and cannot filter by
  regulation — for older regulations event resolution returns `null` and
  emission is `deferred`. Callers (monitor/webhook/n8n) should always pass
  `event_id` (the webhook 202 response provides `eventId`).
* Profiles seeded without `industry_sectors` fall back to `company.industry`;
  scoring then relies on sector↔source inference and is inherently coarse.
* Hash embeddings are lexical — good enough for prototype RAG over short
  regulation texts; swap `embed_text()` for a real embedding model when one is
  available offline.
