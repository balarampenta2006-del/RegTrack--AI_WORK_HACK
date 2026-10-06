# Security Review — Regulatory Update Tracking (Phase 7)

| | |
|---|---|
| **Reviewer** | qa agent (security-auditor persona) |
| **Date** | 2026-10-03 |
| **Scope** | `backend/` Spring Boot service (config, security filters, controllers/services), `docker-compose.yml` env wiring, webhook ingress |
| **Method** | Static review of actual source with file:line evidence + live black-box probes against http://localhost:8080 (read-only) |
| **Out of scope** | Penetration testing of MySQL/OS, dependency CVE scanning (no scanner in pre-provisioned venv), `services/**` and `frontend/**` (separate roles) |

**Severity scale:** Critical (full compromise, fix immediately) · High (serious weakness, fix before any non-local deployment) · Medium (exploitable with constraints / defense-in-depth gap) · Low (hardening / hygiene).

---

## 1. Risk summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | — |
| High | 4 | SEC-01, SEC-02, SEC-03, SEC-04 |
| Medium | 7 | SEC-05 … SEC-11 |
| Low | 8 | SEC-12 … SEC-19 |
| Positive controls | 9 | POS-01 … POS-09 |

No Critical finding: nothing in the reviewed code yields unauthenticated remote code execution or unauthenticated data disclosure of other tenants. The two High findings that are *design* issues for a prototype (dev-default secrets, no TLS) become **Critical the moment this is deployed on a network without changing them**, which is why they are ranked High here and called out in §5.

---

## 2. Findings

### SEC-01 — HIGH — Dev-default JWT signing secret shipped as configuration default
`backend/src/main/resources/application.yml:46` and `docker-compose.yml:32`

```yaml
secret: ${JWT_SECRET:dev-only-change-me-0123456789-abcdefghijklmnopqrstuvwxyz-0123456789}
```

The HS256 signing key is a **publicly known literal**. Anyone who can reach the API can mint a valid token with `"role":"ADMIN"` and obtain full administrative access (audit log, company data, source/config writes). `JwtService` enforces a ≥32-byte secret (`JwtService.java:26-28` — good), but the default itself is 61 bytes of guessable text, so the guard passes.

- **Evidence:** a forged token cannot be distinguished server-side from a real one; `JwtAuthenticationFilter.java:36-45` trusts claims without server-side lookup.
- **Impact:** total authorization bypass (ADMIN) for any attacker with network access.
- **Remediation:** fail startup when `JWT_SECRET` is unset **outside** the `dev` profile (e.g. `@Value` + `ApplicationRunner` guard, or Spring profile-conditional default); document a `openssl rand -base64 48` generation step; rotate on every environment build.

### SEC-02 — HIGH — Seeded admin account with well-known credentials
`application.yml:53-54`, `SeedBootstrap.java:36-58`

`admin@regtrack.local / Admin@12345` is created automatically at first boot and remains valid forever (no forced rotation, no lockout). Combined with SEC-01 this is redundant but independent: the password alone grants ADMIN over plain HTTP.

- **Remediation:** require `ADMIN_PASSWORD` to be provided by the environment (no default in non-dev profiles), force password change on first login, or issue a one-time random password printed to the boot log.

### SEC-03 — HIGH — No HTTPS/TLS anywhere in the transport path
No `server.ssl.*` in `application.yml`; `docker-compose.yml:46` publishes `8080:8080` plaintext; JDBC URL uses `useSSL=false` (`application.yml:5`).

Bearer tokens, webhook HMACs and all regulatory/company data traverse the network unencrypted. On any shared network this enables token theft (→ SEC-01/SEC-02) and tampering with webhook content that drives the analysis pipeline.

- **Remediation:** terminate TLS at a reverse proxy (nginx/Traefik) or enable `server.ssl` with keystore from env; enable MySQL `sslMode=REQUIRED`; add HSTS at the proxy. This satisfies the problem-statement requirement *"HTTPS termination"*.

### SEC-04 — HIGH — SSRF: authenticated users can fetch arbitrary URLs server-side
`ExtractionController.java:24-43`, `ExtractionDtos.java:9-15`, `ExtractionService.java:60-79,191-193`

`POST /api/v1/extractions/extract` and `/trigger` accept `{url, strategy}` from **any authenticated user** (route falls under `anyRequest().authenticated()`, `SecurityConfig.java:49`). `ExtractRequest.url` carries **no validation annotations at all** (no `@URL`, no scheme/host constraint), and the backend forwards it to the extraction worker, which performs the server-side request (`ExtractionService.java:40,60-79`).

- **Impact:** SSRF into internal networks — `http://127.0.0.1:3307`, `http://backend:8080/actuator/*`, cloud metadata `169.254.169.254`, plus response content returned to the caller (`ExtractResponse.markdown`).
- **Evidence (static):** `ExtractionService.java:193` even prefixes `https://` only when a scheme is absent — `http://` and other schemes pass straight through; no IP/host allow-list exists.
- **Remediation:** validate `@URL` + scheme ∈ {https}; resolve and block private/loopback/link-local ranges; allow-list regulatory domains (`.gov.in`, `rbi.org.in`, `sebi.gov.in`, `mca.gov.in`); restrict `/trigger` to ADMIN; consider egress proxy.

### SEC-05 — MEDIUM — Webhook HMAC has no replay window
`WebhookHmacFilter.java:71-89`, `WebhookService.java:55-131`

The signature covers the raw body (good) but the body's `timestamp` field (PLAN §1.2) is **never validated** and there is no nonce store. A signed request captured once (e.g. from a misconfigured log or proxy) can be replayed indefinitely, producing spurious change events/alerts.

- **Remediation:** reject deliveries whose `timestamp` is outside ±300 s of server time; add an idempotency key (signature hash) with a short TTL cache.

### SEC-06 — MEDIUM — Static `X-Webhook-Token` fallback removes payload integrity
`WebhookHmacFilter.java:72-75`

`X-Webhook-Token: <secret>` authenticates *any* body with a single static value: no integrity, no freshness, and the secret must be stored verbatim wherever n8n/ChangeDetection keeps it. Comparison is constant-time (POS-03), but the design is weaker than signature-over-body.

- **Remediation:** keep HMAC signature as the only mode in production; gate the token fallback behind a `regtrack.security.webhook.allow-token` flag defaulting to false.

### SEC-07 — MEDIUM — No brute-force protection on authentication
`AuthController.java:24-35`, `AuthService.java:77-97`

`/api/auth/register` and `/api/auth/login` are `permitAll` (`SecurityConfig.java:40`) with no rate limiting, CAPTCHA, exponential backoff or account lockout. Failed attempts are audited (`AuthService.java:83`, verified live: `GET /api/audit?action=LOGIN_FAILED` returns rows) but nothing throttles them.

- **Remediation:** bucket5/Resilience4j rate limit per IP+email (e.g. 5/min), lock after N failures, plus WAF-level rate limiting at the edge (problem-statement requirement).

### SEC-08 — MEDIUM — CORS configuration is not actually wired to its environment variable
`AppConfig.java:18-39` vs `docker-compose.yml:36`

`@Value("${regtrack.cors.allowed-origins:...}")` does **not** read `CORS_ALLOWED_ORIGINS` (`@Value` performs no relaxed binding), and `application.yml` defines no `regtrack.cors.allowed-origins` key with `${CORS_ALLOWED_ORIGINS:...}`. Operators changing the compose variable get silent no-op. Live probe:

- preflight `Origin: https://evil.example` → **403, no ACAO header** (good),
- preflight `Origin: http://localhost:5173` → **200, `access-control-allow-origin: http://localhost:5173`** (correct).

Current behaviour is safe, but the control is unmanageable. Also `setAllowedHeaders(["*"])` (`AppConfig.java:32`) is permissive and `setExposedHeaders(["X-Webhook-Signature"])` (`AppConfig.java:33`) exposes a response header nothing uses.

- **Remediation:** add `regtrack.cors.allowed-origins: ${CORS_ALLOWED_ORIGINS:http://localhost:5173,http://localhost:3000}` to `application.yml`; enumerate needed headers; forbid `*` as an origin pattern in review.

### SEC-09 — MEDIUM — Unbounded request body buffering on the webhook path
`WebhookHmacFilter.java:49` (`request.getInputStream().readAllBytes()`), no `server.tomcat.max-http-form-post-size`/size-limit config anywhere.

The whole body is buffered **before** any size check, on a `permitAll` endpoint. A single large POST can drive heap pressure; there is no Content-Length pre-check.

- **Remediation:** enforce a max body size (Tomcat `maxSwallowSize`/`maxPostSize`, or Spring `ServerHttp` limit at the proxy), reject `Content-Length > 1 MB` before reading.

### SEC-10 — MEDIUM — `server.error.include-message: always`
`application.yml:29-30`

Exception messages are included in default error payloads. `GlobalExceptionHandler` returns a generic `"Internal server error"` for unhandled exceptions (`GlobalExceptionHandler.java:65-69` — good), but framework-level errors routed through the `/error` endpoint (e.g. unexposed actuator endpoints, see SEC-16) can surface message text.

- **Remediation:** `include-message: never` outside dev; rely on the `@RestControllerAdvice` payload (which already implements the PLAN §1.1 shape).

### SEC-11 — MEDIUM — 401/403 emitted by the security chain violate the documented error contract
`SecurityConfig.java:58-84`

`writeUnauthorized`/`writeForbidden` serialize `{error, message}` only — **no `timestamp`, no `status`** — while PLAN §1.1 and every `@RestControllerAdvice` response use `{timestamp,status,error,message[,fields]}`. Verified live:

- `GET /api/me` (no token) → `{"message":"Missing or invalid authentication token","error":"unauthorized"}`
- officer `POST /api/sources` → `{"message":"...","error":"forbidden"}`
- `POST /api/auth/login` (bad creds) → full 4-key shape.

Consumers that always read `status` break on auth errors. (Tracked as known-issue #1; tests `test_error_shape_security_chain_401/403` are `xfail`.)

- **Remediation:** emit the same 4-key map from both handlers (also add `timestamp`).

### SEC-12 — LOW — Client IP in audit trail taken from spoofable `X-Forwarded-For`
`AuthController.java:37-40`, `AlertController.java:64-70`, `CompanyController.java:78-84`

First `X-Forwarded-For` hop is trusted unconditionally. Any caller can forge the recorded source IP of LOGIN/REGISTER/WEBHOOK/ALERT audit rows — weakens the audit trail's evidentiary value (SOC 2 / ISO 27001 logging control).

- **Remediation:** parse XFF only when the request comes from a trusted proxy hop; otherwise use `remoteAddr`.

### SEC-13 — LOW — 24-hour JWT lifetime with no revocation
`application.yml:47` (86400 s), `JwtAuthenticationFilter.java:28-45`

No refresh tokens, no deny-list, no logout endpoint: a stolen token works up to 24 h; disabling a user only takes effect after re-login AND token expiry (`AuthService.java:87-89` blocks login but existing tokens still parse).

- **Remediation:** shorten TTL (15–60 min) + refresh rotation, or add a revocation list checked in the filter.

### SEC-14 — LOW — Database credentials have insecure defaults and TLS disabled
`application.yml:5-7` (`useSSL=false&allowPublicKeyRetrieval=true`, password `regtrack`), `docker-compose.yml:20-24` (root password `root`).

Fine on a dev laptop; unacceptable if 3307 stays published in any shared environment.

- **Remediation:** `sslMode=REQUIRED`, move credentials to an `.env` outside VCS, do not publish 3307 outside dev.

### SEC-15 — LOW — Secret rotation requires process restart; no key IDs
`JwtService.java:22-32`, `WebhookHmacFilter.java:37-38`

Secrets are injected once at startup; tokens carry no `kid`, so rotating `JWT_SECRET` invalidates every session at once, and there is no dual-key overlap window. Same for `WEBHOOK_SECRET` (all four pipeline agents must be re-deployed simultaneously).

- **Remediation:** support primary+secondary secrets (verify against both during rotation), add `kid` to JWT header, document rotation runbook.

### SEC-16 — LOW — Unexposed actuator endpoints return HTTP 500
Live probe: `GET /actuator/env` → unauth **401**; with ADMIN token → **500** (`{"message":"Internal server error"}`), same for `/actuator/beans`.

Authorization works (`SecurityConfig.java:43`), exposure is correctly limited to `health,info` (`application.yml:33-37`), but a missing endpoint should be 404 rather than 500 — the generic 500 masks routing misconfiguration and adds noise to monitoring.

- **Remediation:** 404 for unmatched actuator paths (`management.endpoints.web.exposure` + `NoResourceFoundException` handler).

### SEC-17 — LOW — CSRF disabled
`SecurityConfig.java:35`

Acceptable **only because** the API is stateless bearer-token (no cookies) — sessions are `STATELESS` (`SecurityConfig.java:37`) and the token travels in `Authorization`. Documented so nobody adds cookie-based auth later without re-enabling CSRF.

### SEC-18 — LOW — CORS origin patterns configurable to `*` with permissive defaults risk
`AppConfig.java:18-30`

`setAllowedOriginPatterns` accepts whatever the property contains — a future `*` would reflect arbitrary origins (harmless today only because auth is header-based, not cookie-based). Default list (`localhost:5173,localhost:3000`) is appropriately narrow.

- **Remediation:** validate/forbid `*` at startup; keep the explicit list.

### SEC-19 — LOW — Password policy is length-only
`AuthDtos.java:14` (`@Size(min = 8, max = 100)`), `AppConfig.java:22-24` (BCrypt)

No complexity/breach checks (`Admin@12345` satisfies the rule). BCrypt cost is the default 10 — acceptable.

- **Remediation:** add complexity or check against common-password lists; consider `DelegatingPasswordEncoder` for future algorithm agility.

---

## 3. Positive controls verified (with evidence)

| ID | Control | Evidence |
|---|---|---|
| POS-01 | BCrypt password hashing, matches on login | `AppConfig.java:22-24`, `AuthService.java:63,82` |
| POS-02 | JWT secret length enforced (≥32 bytes) at startup | `JwtService.java:26-28` |
| POS-03 | HMAC comparison is constant-time (`MessageDigest.isEqual`), both signature and token paths | `WebhookHmacFilter.java:74-75,87-88,110-112` |
| POS-04 | Signature computed over the **raw** body (cached-body replay to the chain), case-normalised hex | `WebhookHmacFilter.java:49,65,86-88`; live test: valid HMAC → 202, tampered → 401 |
| POS-05 | RBAC enforced at route level **and** method level (`@EnableMethodSecurity`) | `SecurityConfig.java:24,38-49`; live: officer `POST /api/sources` → 403, `GET /api/audit` → 403, admin → 200 |
| POS-06 | Tenant scoping implemented in services, not just UI | `AlertService.java:43-54,61-66,94-95`; `CompanyService.java:49-52,113-114`; live test: officer B cannot see officer A's alerts |
| POS-07 | SQL-injection posture: JPA repositories, parameterised JPQL only, **zero** native queries | `RegulationVersionRepository.java:23` (named params); live probe `?action=' OR '1'='1` → 200 with empty list (in-memory filter, no error) |
| POS-08 | Actuator locked down: exposure = `health,info`, everything else ADMIN, health public | `application.yml:33-41`, `SecurityConfig.java:42-43`; live: `/actuator/env` unauth → 401 |
| POS-09 | Stateless sessions, generic 500 without stack traces, failed-login auditing | `SecurityConfig.java:37`, `GlobalExceptionHandler.java:65-69`, `AuthService.java:83`; live: 500 body = `{"message":"Internal server error"}` |

---

## 4. Compliance mapping (light)

| Framework | Control objective | Status |
|---|---|---|
| ISO 27001 A.9 access control | Role-based access, least privilege, tenant isolation | **Met** (POS-05/06) with SEC-13 caveat |
| ISO 27001 A.14 system acquisition | Secure transmission | **Not met** — SEC-03 (no TLS) |
| SOC 2 CC6.1 logical access | AuthN/AuthZ, brute-force protection | **Partially met** — SEC-07 gap |
| SOC 2 CC7.2 monitoring | Audit trail integrity | **Partially met** — SEC-12 (spoofable IP) |
| NIST SSF PR.DS data in transit | Encryption in transit | **Not met** — SEC-03 |
| OWASP API Security Top 10 | API1 broken auth, API4 unrestricted resource consumption, API7 SSRF | Gaps: SEC-01/02/07 (API1), SEC-09 (API4), SEC-04 (API7) |

---

## 5. Recommendations (prioritised)

1. **Before any non-local deployment:** remove dev defaults for `JWT_SECRET`, `WEBHOOK_SECRET`, `ADMIN_PASSWORD` (fail-fast when unset) — SEC-01/02; terminate TLS + HSTS at a reverse proxy — SEC-03.
2. **Short term:** SSRF guard on `/api/v1/extractions/**` (scheme + host allow-list, private-IP block, `/trigger` → ADMIN) — SEC-04; webhook replay window (±5 min timestamp) and disable token fallback — SEC-05/06; login rate limiting + edge WAF/rate rules — SEC-07.
3. **Config hygiene:** wire `regtrack.cors.allowed-origins` to `CORS_ALLOWED_ORIGINS` in `application.yml` — SEC-08; `include-message: never` outside dev — SEC-10; align 401/403 body with PLAN §1.1 — SEC-11.
4. **Hardening backlog:** request size caps (SEC-09), trusted-proxy XFF (SEC-12), short-lived tokens + revocation (SEC-13), DB TLS/credentials (SEC-14), rotation runbook with dual secrets (SEC-15), 404 for missing actuator endpoints (SEC-16), password policy (SEC-19).
5. **Secret rotation (problem-statement requirement):** runbook = set new secret as secondary → rolling restart (dual-verify) → promote → drop old; requires SEC-15 dual-key support first.

*All probes in this report were read-only; no backend/container was restarted or reconfigured during the audit.*
