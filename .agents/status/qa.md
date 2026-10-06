---
role: qa
status: DONE
updated: 2026-10-03T08:21:40Z
---
## Artifacts
- tests/conftest.py — shared fixtures: live-API helpers, uuid random-data factories, HMAC signer (hmac stdlib, WEBHOOK_SECRET default from PLAN §2.1), officer/change-event factories
- tests/pipeline_support.py — service import/discovery helpers (handles package, sub-package and namespace layouts under services/; skips with explicit reason when a contract entry point is missing)
- tests/test_backend_contract.py — 23 live API contract tests (PLAN §1.1): auth round-trip, RBAC matrix, error-shape validation, alert/company scoping
- tests/test_webhook_security.py — 12 live webhook tests (PLAN §1.2): missing/wrong/tampered/garbage signatures → 401, valid HMAC over raw body → 202 + ack shape, static token, content dedupe (no 2nd version), changed content → v2
- tests/test_storage_contracts.py — 11 pure validators: full required-key/type/enum checks for manifest.json (§2.3) and analysis JSON (§2.4), 10 self-tests + live scan of real storage artifacts (auto-enables)
- tests/test_pipeline_docproc.py — 11 accuracy fixtures over real services/docproc (gazette HTML → extract → clean determinism, unicode/page/hyphenation rules, full process() manifest per §2.3, isolated STORAGE_ROOT)
- tests/test_pipeline_ai.py — 8 accuracy fixtures over real services/ai (stub mode forced, scripted fake backend client, isolated STORAGE_ROOT): §2.4 schema validity, non-empty summary, effective_date null-or-ISO, relevance enums, clause detection, determinism, persisted analysis file
- docs/security-review.md — 19 findings (4 High / 7 Medium / 8 Low) + 9 positive controls, file:line evidence, live probes, compliance mapping, prioritised remediation
- docs/known-issues.md — 8 entries: error-shape gap, ACK null-key omission, e2e fix record, compose env binding gap, undocumented routes, deferred items
- docs/test-report.md — every command with pass/fail/skip/xfail counts, skip inventory, security probe evidence, re-run instructions
- scripts/e2e-phase1.ps1 (edit) — source code now derives from $runId (was 4-char guid); company/email/URL were already $runId-random on receipt; comment added
## Verification
- `.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q` → **62 passed, 1 skipped, 2 xfailed, 0 failed** (65 collected) — stable across 3 consecutive final runs (61/2/2 → 62/1/2 → 62/1/2 as storage/analysis artifact landed)
- `.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests -q -rs` → skip reason: no storage/processed/**/manifest.json yet (auto-enables); xfail reasons: SecurityConfig 401/403 body lacks timestamp/status (known-issue #1)
- `.venv\Scripts\python.exe -m pytest D:\AI_Hack\tests --collect-only -q` → 65 tests (backend 23 / webhook 12 / storage 11 / docproc 11 / ai 8)
- `.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\tests` → OK
- `scripts\e2e-phase1.ps1` → 4 × **33 passed, 0 failed** (2 baseline pre-edit, 2 after edit) — non-idempotency closed
- PowerShell `[Parser]::ParseFile("...\e2e-phase1.ps1")` → SYNTAX OK (0 errors)
- Security probes (read-only): evil-origin CORS preflight 403/no-ACAO; `/actuator/env` anon 401; SQLi probes neutral; admin actuator-non-exposed → generic 500 (SEC-16)
- No pip installs; no backend/docker restarts
## Handoff notes
- DoD met: zero unexpected failures (1 skip + 2 xfail all recorded with reasons), 3 docs exist, e2e fix applied and syntax-valid
- Orchestrator: known-issue #1 (401/403 error shape) needs a backend fix — flip the two xfail tests to normal once done; known-issue #2 (ACK drops newVersionId on dedupe) is a PLAN-vs-behaviour doc decision
- ops/backend: docker-compose `CORS_ALLOWED_ORIGINS`/`EXTRACTION_WORKER_URL` are NOT bound to `@Value` properties — currently silent no-ops (known-issue #4)
- security: 4 High findings before any non-local deployment — dev-default JWT secret, default admin password, no TLS, SSRF on /api/v1/extractions (see docs/security-review.md §5)
- re-run pytest after docproc processes a real regulation: the last skip (real manifest scan) then enables with no code change
- assumptions recorded: backend contract taken from PLAN §1.1/§1.2 + live probing (backend read-only); pipeline tests bind to actual services/docproc and services/ai entry points as of 13:39 local — if those signatures change, tests/pipeline_support discovery skips with a reason rather than failing
## Extra deps / unresolved issues
- extra-deps: none (suite uses only pre-provisioned requests/pytest/hmac/stdlib)
- optional (not raised, would need pip): pip-audit/OWASP-dep-check for CVE scanning, locust for load tests, playwright for UI E2E — all deferred in docs/known-issues.md #7
- unresolved: 1 storage-artifact skip (awaiting first real manifest); 2 documented xfails awaiting backend error-shape fix
