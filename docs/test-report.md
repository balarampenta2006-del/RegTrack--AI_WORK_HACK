# Test Report — Phase 7 (QA)

| | |
|---|---|
| **Date** | 2026-10-03 |
| **Suite** | `D:\AI_Hack\tests` (pytest 9.1.1, venv `D:\AI_Hack\.venv`) |
| **SUT** | Spring Boot backend @ http://localhost:8080 (live), MySQL @ 3307, `services/docproc`, `services/ai` (import-level) |
| **Isolation** | every test generates uuid-based data (random email/company/source-code/webhook URL); pipeline tests run against a throwaway `STORAGE_ROOT` under `pytest tmp_path` — the suite is fully re-runnable |

---

## 1. Commands executed (chronological)

| # | Command | Result |
|---|---|---|
| 1 | `& D:\AI_Hack\scripts\e2e-phase1.ps1` (baseline, before QA edit) | **33 passed, 0 failed** |
| 2 | `& D:\AI_Hack\scripts\e2e-phase1.ps1` (baseline, 2nd consecutive run) | **33 passed, 0 failed** |
| 3 | `.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q` (1st draft) | 4 failed, 41 passed, 5 skipped, 2 xfailed — *all 4 failures were QA test-authoring bugs (backend upper-cases source codes; `sha256=` prefix is case-sensitive; dedupe ACK omits null keys; docproc `clean_text` correctly expects extracted text, not raw HTML) — fixed in test code* |
| 4 | `... pytest D:\AI_Hack\tests -q` (after contract fixes + docproc rewrite) | 1 failed, 50 passed, 5 skipped, 2 xfailed — *test expected page-number stripping without form-feed pages; test corrected to the documented contract* |
| 5 | `... pytest D:\AI_Hack\tests -q` | **53 passed, 5 skipped, 2 xfailed** |
| 6 | `... pytest D:\AI_Hack\tests -q -rs` (after ai-service tests added) | 1 failed, 60 passed, 2 skipped, 2 xfailed — *fake backend client lacked `get_versions`; fixed in test code* |
| 7 | `... pytest D:\AI_Hack\tests -q -rs` | **61 passed, 2 skipped, 2 xfailed** |
| 8 | `... pytest D:\AI_Hack\tests -q -rs` (storage artifacts landed) | **62 passed, 1 skipped, 2 xfailed** |
| 9 | `... pytest D:\AI_Hack\tests -q -rs` (confirm re-runnability) | **62 passed, 1 skipped, 2 xfailed** — identical to #8 |
| 10 | `... pytest D:\AI_Hack\tests --collect-only -q` | 65 tests collected |
| 11 | `.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\tests` | OK (no syntax errors) |
| 12 | PowerShell `[Parser]::ParseFile("D:\AI_Hack\scripts\e2e-phase1.ps1")` | **SYNTAX OK** (1789 tokens, 0 errors) |
| 13 | `& D:\AI_Hack\scripts\e2e-phase1.ps1` (after idempotency fix) | **33 passed, 0 failed** |
| 14 | `& D:\AI_Hack\scripts\e2e-phase1.ps1` (2nd consecutive run after fix) | **33 passed, 0 failed** |
| 15 | Security probes (ad-hoc `httpx` script, read-only) — see §4 | as tabulated in §4 |

*No pip installs were performed. No backend/container was stopped or restarted.*

---

## 2. Final suite result

```
.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q
→ 62 passed, 1 skipped, 2 xfailed        (65 collected, 0 failures)
```

| File | Tests | Layer | Result |
|---|---|---|---|
| `tests/test_backend_contract.py` | 23 | Live API contract (PLAN §1.1) | 21 pass + 2 xfail (known gaps, §3) |
| `tests/test_webhook_security.py` | 12 | Live webhook security & versioning (PLAN §1.2) | 12 pass |
| `tests/test_storage_contracts.py` | 11 | Pure storage validators (PLAN §2.3/§2.4) | 10 pass + 1 skip (§3) |
| `tests/test_pipeline_docproc.py` | 11 | Docproc accuracy fixtures (isolated storage root) | 11 pass |
| `tests/test_pipeline_ai.py` | 8 | AI stub-mode accuracy fixtures (isolated storage root) | 8 pass |
| **Total** | **65** | | **62 pass, 1 skip, 2 xfail, 0 fail** |

Supporting files: `tests/conftest.py` (fixtures, HMAC helper, random-data factories), `tests/pipeline_support.py` (service import/discovery helpers with skip-on-missing contracts).

### What the live layer proved (PLAN §1.1/§1.2)

- random registration (201) → login (200) → `/api/me` round-trip; duplicate email 409; bad password 401; no/garbage token 401.
- **RBAC matrix:** officer `POST /api/sources` → 403, officer `GET /api/audit` → 403, admin → 200 for both, admin creates source 201 (code normalised to upper-case), anonymous write → 401.
- **Webhook security:** missing signature → 401 · wrong HMAC → 401 · signature over a *different* body → 401 · garbage signature → 401 · empty/wrong token → 401 · **valid HMAC over the raw body (hmac stdlib, secret = `WEBHOOK_SECRET` default `dev-webhook-shared-secret-please-change`) → 202 with `{eventId,status,regulationId,newVersionId,receivedAt}`** · uppercase hex in `sha256=` → 202 · static token → 202.
- **Version dedupe:** identical content posted twice → second ACK has no `newVersionId` and `/versions` stays at 1 entry; changed content → v2 created, content retrievable and different.
- **Alert scoping:** officer A's alert invisible to officer B (id *and* companyId checks), visible to A and ADMIN; cross-company alert creation → 403; company list scoped to own company; foreign company → 403.
- **Error shape:** `{timestamp,status,error,message}` verified for 400 (with `fields`), 401 (auth handler), 404, 409 — the two security-chain cases are tracked as xfail (§3).

### What the pure/pipeline layer proved

- **Storage validators:** full required-key sets for `manifest.json` (§2.3: 11 keys, method enum, sha256 format, ISO timestamps) and analysis JSON (§2.4: 13 keys, `risk_level`/`relevance.level` enums, `effective_date` null-or-`YYYY-MM-DD`, relevance entry shape) — 10 self-tests cover accept/reject paths; **one real artifact** (`storage/analysis/1/v6.json`, written by the ai service) passes the §2.4 validator live.
- **Docproc accuracy:** HTML gazette snippet → extract (markup/scripts stripped, `method=html`, `ocr_used=false`) → `clean_text` deterministic, key phrase preserved, unicode normalisation (ligature/smart-quote/NBSP), page furniture stripped, EOL hyphenation rejoined; full `process()` pipeline emits a §2.3-valid manifest + `v1/v2` texts in an isolated storage root, byte-identical across runs, `char_count`/`content_sha256` self-consistent.
- **AI accuracy (stub mode, no key):** `run_analysis` with `AI_FORCE_STUB=1` returns schema-valid §2.4 — non-empty summary, `effective_date` null-or-ISO, `risk_level`/relevance levels inside enums, relevance scored `HIGH` for an RBI-regulated NBFC profile; detects the new "public register" clause in `key_changes`; **deterministic across runs** (all stable fields byte-equal); `old_version_missing:true` when v1 absent; result persisted to `storage/analysis/<id>/v2.json` satisfying the §2.4 validator.

---

## 3. Skips & xfails (all with recorded reasons)

| Test | Kind | Reason | Auto-enables when |
|---|---|---|---|
| `test_storage_contracts.py::test_real_manifests_satisfy_contract` | skip | `no storage/processed/**/manifest.json yet (docproc agent pending)` — docproc service is DONE but has not yet processed a real regulation into `storage/processed/` | a manifest lands on disk (test needs no edit) |
| `test_backend_contract.py::test_error_shape_security_chain_401` | xfail (strict=False) | KNOWN GAP #1: `SecurityConfig` 401/403 handlers emit `{error,message}` only | backend fix → reports XPASS |
| `test_backend_contract.py::test_error_shape_security_chain_403` | xfail (strict=False) | same | same |

`-rs` run confirms these are the **only** skip/xfail reasons; there are no environment-conditional skips left for missing `services/*` folders (docproc + ai landed and their tests run).

---

## 4. Security probe evidence (read-only, live)

| Probe | Result |
|---|---|
| `GET /actuator/health` (anon) | 200 `{"status":"UP"}` |
| `GET /actuator/env` (anon) | 401 |
| `GET /actuator/env`, `/actuator/beans` (ADMIN) | 500, generic body (SEC-16) |
| CORS preflight `Origin: https://evil.example` | 403, no ACAO header |
| CORS preflight `Origin: http://localhost:5173` | 200, `ACAO: http://localhost:5173` |
| `GET /api/audit?action=' OR '1'='1` (ADMIN) | 200, empty list — no SQL error/injection (JPQL/in-memory filter) |
| `GET /api/sources?source=' OR 1=1--` (ADMIN) | 200 |
| 401 body (no token) vs 401 body (bad login) | inconsistent shapes → known-issue #1 |
| officer alert cross-company create | 403 with full 4-key error shape |

Full findings with file:line references: **`docs/security-review.md`** (19 findings: 4 High, 7 Medium, 8 Low + 9 positive controls).

---

## 5. Deferred / not covered

| Item | Why | Where tracked |
|---|---|---|
| Real-manifest file scan | no `storage/processed/**/manifest.json` exists yet (runtime artifact, not code) | known-issues #6; test auto-enables |
| UI/browser E2E, visual, cross-browser | Playwright not installed (PLAN §6); frontend owned by another role | known-issues #7 |
| Load/performance tests | no load tool in pre-provisioned venv; no `extra-deps:` raised | known-issues #7 |
| `mvnw test` (backend unit tests) | `backend/**` read-only for QA; Phase 1 surefire reports already present under `backend/target/surefire-reports` | known-issues #7 |
| Docker-compose integration & container-level tests | owned by ops role | known-issues #7 |
| Dependency CVE scanning | scanner not in venv, `pip install` forbidden | status file `extra-deps:` |

---

## 6. Re-run instructions

```powershell
# full suite (must end "zero unexpected failures")
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q

# with skip/xfail reasons
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q -rs

# phase-1 E2E (idempotent; safe to run repeatedly)
D:\AI_Hack\scripts\e2e-phase1.ps1
```

Environment knobs read by the suite: `API_BASE` (default `http://localhost:8080`), `WEBHOOK_SECRET` (default from PLAN §2.1), `ADMIN_EMAIL`/`ADMIN_PASSWORD` (defaults from PLAN §2.1).
