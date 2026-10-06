# Known Issues — QA (Phase 7)

Owner: qa agent · Updated: 2026-10-03 · Severity: **[contract]** = violates PLAN §2 contract · **[env]** = environment limitation · **[deferred]** = intentionally out of scope for Phase 7.

---

## 1. [contract] Security-chain 401/403 responses miss `timestamp` and `status`

- **Where:** `backend/src/main/java/com/regtrack/backend/config/SecurityConfig.java:58-84`
- **Detail:** `writeUnauthorized` / `writeForbidden` serialize `{"error": ..., "message": ...}` only. Every other error path (the `@RestControllerAdvice` at `GlobalExceptionHandler.java:75-82`) emits the PLAN §1.1 shape `{timestamp,status,error,message[,fields]}`.
- **Live evidence:**
  - `GET /api/me` (no token) → `401 {"message":"Missing or invalid authentication token","error":"unauthorized"}`
  - officer `POST /api/sources` → `403 {"message":"...","error":"forbidden"}`
  - `POST /api/auth/login` (bad password) → `401 {"timestamp":...,"status":401,...}`
- **Affected tests:** `tests/test_backend_contract.py::test_error_shape_security_chain_401` and `..._403` are marked `xfail (strict=False)` so the suite stays green while documenting the gap. They will report `XPASS` once fixed — flip them to normal tests then.
- **Suggested fix (backend role):** emit `Map.of("timestamp", Instant.now(), "status", 401, "error", ..., "message", ...)` in both handlers.

## 2. [contract] Webhook ACK omits `newVersionId` on content dedupe

- **Where:** `application.yml:24-25` (`default-property-inclusion: non_null`) + `WebhookService.java:129-130`
- **Detail:** PLAN §1.2 documents the ACK as `{"eventId","status","regulationId","newVersionId","receivedAt"}`. When an identical content hash arrives, `newVersionId` stays `null` and the key is **dropped entirely** by Jackson (`non_null`), not sent as `null`. Consumers using `ack["newVersionId"]` get `KeyError`; `ack.get("newVersionId")` works.
- **Evidence:** pytest `test_same_content_twice_creates_no_second_version` asserts the key is absent; e2e uses `[bool]` checks so it never noticed.
- **Suggested fix:** either document "key present only when a new version is created" in PLAN §1.2, or serialise `newVersionId` as explicit `null` for this endpoint.

## 3. [fixed] `scripts/e2e-phase1.ps1` non-idempotent test data

- **Reported collision:** company name `"Acme Fintech Ltd"` and source code `"EDCI"` on re-run (PLAN §1 note: "31/33 known non-idempotent bug — QA owns the fix").
- **State on receipt:** company name (`line 67`), officer email (`line 66`) and webhook URL (`line 123`) were **already** randomised with `$runId`; the source code used `[guid]::NewGuid()...Substring(0,4)` (`line 114`) — only 4 hex chars ≈ 1/65k collision chance per run against `uk_sources_code`.
- **Fix applied (QA):** source code now derives from the run's own `$runId` (`"ED" + $runId.Substring(0,8).ToUpper()`, 10 chars) plus an explanatory comment — collision now requires a duplicate run-id.
- **Verification:** PowerShell parser → `SYNTAX OK`; **4 consecutive runs → 33/33 passed, 0 failed** (runs 1–2 before the edit, runs 3–4 after).

## 4. [contract] Compose env vars not bound to backend `@Value` properties

- **Where:** `docker-compose.yml:36` (`CORS_ALLOWED_ORIGINS`) vs `AppConfig.java:18` (`regtrack.cors.allowed-origins`); `docker-compose.yml:37` (`EXTRACTION_WORKER_URL`) vs `ExtractionService.java:40` (`app.extraction-worker.url`).
- **Detail:** Spring `@Value` does **not** do relaxed binding from those env names, so editing them in `.env` silently does nothing (CORS keeps `localhost:5173,3000`; extraction worker keeps the default `http://extraction-worker:8000`, which happens to match compose).
- **Suggested fix (ops + backend):** add `regtrack.cors.allowed-origins: ${CORS_ALLOWED_ORIGINS:...}` and `app.extraction-worker.url: ${EXTRACTION_WORKER_URL:...}` to `application.yml`.
- Tracked as **SEC-08** in `docs/security-review.md`.

## 5. [contract] Undocumented API surface vs PLAN §1.1

Routes that exist and are reachable but are absent from the PLAN API table (frontend/monitor may not know about them):

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/regulations/{id}/versions`, `/versions/{vid}`, `/diff`, `/diff/patch` | `DiffController.java:16-56` |
| POST | `/api/v1/extractions/extract`, `/trigger` | `ExtractionController.java:15-43` — **SSRF risk, see SEC-04** |
| POST | `/api/alerts` (request shape) | `{companyId, changeEventId}` are `@NotNull` (`AlertDtos.java:14-15`) — PLAN omits the body schema |
| PUT | `/api/companies/{id}/profile` | body schema not in PLAN |

## 6. [contract] Storage-contract tests skip until real artifacts exist

- `tests/test_storage_contracts.py::test_real_manifests_satisfy_contract` and `..._test_real_analyses_satisfy_contract` skip when `storage/processed/**/manifest.json` / `storage/analysis/**/*.json` do not exist.
- As of the final QA run **no artifacts had been written to `D:\AI_Hack\storage\`** (docproc/ai services write them only when the pipeline runs). The validators themselves are fully exercised by 10 self-test cases against the PLAN §2.3/§2.4 examples; the file-scanning tests auto-enable the moment storage output lands.
- Minor note: docproc writes `source_url: ""` when processing a **local file** input (`fetch.py:197`); the §2.3 example shows a URL. Validators accept both — flagging so ai/frontend don't assume a parseable URL.

## 7. [deferred] Items intentionally not covered

| Item | Reason |
|---|---|
| Frontend/UI E2E, browser tests | Playwright not installed (PLAN §6); frontend owned by another role |
| Load/performance testing | No load tool in pre-provisioned venv; no `extra-deps:` raised |
| `docker compose config` / compose integration | ops role owns `docker-compose.yml` (PLAN §4) |
| Backend `mvnw test` | backend/ is read-only for QA; Phase 1 surefire reports exist under `backend/target/surefire-reports` |
| Dependency CVE scan (OWASP dep-check, pip-audit) | No scanner in venv, `pip install` forbidden — see `extra-deps:` in status file if wanted |
| DB-level row tests (MySQL) | Live contract tests cover behaviour through the API; direct DB access would mutate shared state |

## 8. [accepted] Observations recorded, no action for the prototype

- **Open registration** (`POST /api/auth/register` → always `COMPLIANCE_OFFICER`, `AuthService.java:65`) is by design (PLAN §1.1); combined with no rate limit it is SEC-07.
- **Audit list filters in memory** (`AuditService.java:34-37` loads all rows then filters `action`) — correct but O(n); will need a DB-side predicate for large deployments.
- **Login audit of failed attempts works** but relies on `X-Forwarded-For` for IP (SEC-12).
- **Seeded sources** `MCA/RBI/SEBI` and admin account are recreated only when absent (`SeedBootstrap.java:53`) — safe for re-runs.
