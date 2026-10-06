# n8n — Regulatory Pipeline Automation

Phase 5 automation for the regulatory-update-tracking prototype. One scheduled workflow
drives the whole loop: monitor → backend events → docproc → ai → PENDING alerts →
Gmail → ack (SENT).

- Workflow file: [`workflows/regulatory-pipeline.json`](workflows/regulatory-pipeline.json)
- Port: **5678** (see PLAN.md §2.2)
- The workflow is imported **inactive** — you must activate it once (step 4 below).

## 1. Pipeline flow

```
Every 15 Minutes
  → Run Change Monitor        POST http://monitor:8101/run
  → Admin Login               POST http://backend:8080/api/auth/login   (ADMIN_EMAIL/ADMIN_PASSWORD)
  → Save Auth Token           (Code: carry {token} forward)
  → Fetch Events              GET  http://backend:8080/api/events        (Bearer)
  → Filter New Events         (Code: status == RECEIVED AND id > watermark, watermark = workflow staticData.lastEventId)
  → Has New Events?           (IF)
       ├─ true  → Process Document   POST http://docproc:8102/process   {input: payloadUrl, regulation_id, version_no: 1, source: sourceCode}
       │          → Analyze Regulation POST http://ai:8103/analyze      {regulation_id, version_no, event_id}
       │          → Reduce To One Item (Code)
       │          → Record Watermark  (Code: staticData.lastEventId = max(event id) — only after processing ran)
       └─ false → (skip straight to alerts)
  → Fetch Pending Alerts      GET  http://backend:8080/api/alerts?status=PENDING   (Bearer)
  → Normalize Alerts          (Code: array → one item per alert)
  → Has Recipients?           (IF, gates alerts with empty emailRecipients)
       ├─ true  → Send Alert Email   (Gmail node; subject = [source] title; body = AI summary, required action,
       │                              effective date, source link, affected areas, company, alert id)
       │          ├─ success → Mark Alert Sent   PATCH http://backend:8080/api/alerts/{id}/status  {status: "SENT"}
       │          └─ error   → Email Send Failed (Code: logs alert_id + reason; alert STAYS PENDING → retried next run)
       └─ false → (alert skipped, stays PENDING)
```

### Error handling (one failed step never kills the run)

- Every HTTP Request node and the Gmail node set `onError` (HTTP: `continueRegularOutput`,
  Gmail: `continueErrorOutput`) plus `retryOnFail` (2–3 tries, 3–5 s apart).
- Two **IF nodes** (`Has New Events?`, `Has Recipients?`) branch the flow logically; a run with
  zero new events or zero PENDING alerts finishes cleanly instead of failing.
- The Gmail node has a real **error branch** (`Send Alert Email` output 1 → `Email Send Failed`),
  so a failed send does **not** PATCH the alert to SENT — the alert is retried on a later run.
- Defensive Code nodes: if a backend response is an error body instead of an array, the
  filter/normalize nodes return empty/marker items and the run ends gracefully.

### Watermark (dedup across runs)

- Stored in n8n **workflow static data** (`$getWorkflowStaticData('global').lastEventId`),
  initial value `0`.
- `Filter New Events` only reads it; `Record Watermark` advances it **after** the
  docproc/ai branch has run. If the run dies mid-processing the watermark does not move
  and those events are retried next run (at-least-once).
- Static data persists reliably for **active (production) executions**. Manual executions
  from the editor also persist it, but treat production runs as the source of truth.
- First run therefore processes the whole RECEIVED backlog. To start from "now", open the
  workflow → execute once → set `lastEventId` in the workflow static data (or delete
  `staticData` in the exported JSON and re-import).

## 2. Import

### Option A — auto-import on first container start (default in docker-compose.yml)

The `n8n` service command imports the workflow **once** (guarded by a marker file in the
`n8n-data` volume), then starts n8n:

```yaml
command: ["/bin/sh", "-c", "if [ ! -f /home/node/.n8n/.workflow-imported ]; then n8n import:workflow --input=/workflows/regulatory-pipeline.json && touch /home/node/.n8n/.workflow-imported; fi; exec n8n start"]
```

`./n8n/workflows` is mounted read-only at `/workflows`. Re-runs of `docker compose up`
do not create duplicates (marker file lives in the persistent volume).

### Option B — CLI import (manual, anytime)

```powershell
docker compose cp n8n\workflows\regulatory-pipeline.json n8n:/tmp/regulatory-pipeline.json
docker compose exec n8n n8n import:workflow --input=/tmp/regulatory-pipeline.json
```

### Option C — UI import

1. Open http://localhost:5678 → create owner account on first visit.
2. **Workflows → Create → ⋯ (top right) → Import from File…**
3. Select `n8n/workflows/regulatory-pipeline.json`.

> `import:workflow` creates a **new** workflow each time it runs — do not import the same
> file twice unless you want duplicates (delete the old one first).

## 3. Environment variables

The `n8n` service passes these through (docker-compose.yml):

| Var | Default | Used by the workflow for |
|---|---|---|
| `ADMIN_EMAIL` | `admin@regtrack.local` | `Admin Login` body (`$env.ADMIN_EMAIL`) |
| `ADMIN_PASSWORD` | `Admin@12345` | `Admin Login` body (`$env.ADMIN_PASSWORD`) |
| `API_BASE` | `http://backend:8080` | informational; workflow URLs use docker-internal names |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` | **must stay `false`** — workflow reads `$env.ADMIN_*` |
| `N8N_ENCRYPTION_KEY` | `dev-only-n8n-encryption-key-change-me` | encrypts stored credentials — change for anything real |
| `N8N_SECURE_COOKIE` | `false` | allows plain-http access on http://localhost:5678 |
| `GENERIC_TIMEZONE` / `TZ` | `UTC` | schedule trigger timezone (set to your local TZ for sensible 15-min runs) |
| `N8N_DIAGNOSTICS_ENABLED` | `false` | no telemetry in the prototype |

Service URLs are hard-coded to docker-internal DNS (`http://monitor:8101`,
`http://docproc:8102`, `http://ai:8103`, `http://backend:8080`) per PLAN.md §2.5 — inside
the compose network these resolve; on the Windows dev-mode host, run n8n with the URLs
swapped to `localhost` or add extra hosts.

## 4. Gmail credential setup (one-time, manual)

The workflow ships with **placeholder credentials** on the `Send Alert Email` node:

```json
"credentials": { "gmailOAuth2": { "id": "{{GMAIL_OAUTH_CREDENTIAL_ID}}", "name": "{{GMAIL_OAUTH_CREDENTIAL_NAME}}" }
```

`{{GMAIL_OAUTH_CREDENTIAL_ID}}` / `{{GMAIL_OAUTH_CREDENTIAL_NAME}}` are literal placeholders —
n8n cannot resolve them, so the node shows "no credential" until you attach a real one:

1. Google Cloud Console → create/select a project → **APIs & Services → OAuth consent screen**
   (External + Test mode is fine) → add yourself as a test user.
2. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized redirect URI: `http://localhost:5678/rest/oauth2-credential/callback`
     (n8n UI → **Credentials → New → Gmail OAuth2 API** shows the exact URI it expects).
3. In n8n: create the **Gmail OAuth2 API** credential, paste Client ID + Secret, **Connect**,
   save. Copy the credential's **ID** (visible in the credential URL / `credentials` tab).
4. Open the imported workflow → `Send Alert Email` node → **Credential for Gmail OAuth2
   account** → select your credential → save. (Selecting it overwrites the `{{GMAIL_...}}`
   placeholder.)

Alternative: edit the JSON before import and replace the two `{{GMAIL_...}}` values with the
credential id/name you already have, e.g.
`docker compose exec n8n sh -c "sed -i 's/{{GMAIL_OAUTH_CREDENTIAL_ID}}/<id>/' /workflows/regulatory-pipeline.json"`.

Until a real credential is attached, sends fail into the `Email Send Failed` branch and
alerts remain PENDING (safe — nothing is lost, nothing is double-marked).

## 5. The ack loop (end-to-end)

1. **detect** — `monitor` checks sources every 15 min (also triggered by this workflow's
   `Run Change Monitor` node) and POSTs a signed payload to
   `POST /api/webhooks/changedetection` (`X-Webhook-Signature: sha256=<hmac>` or
   `X-Webhook-Token: <WEBHOOK_SECRET>`).
2. **ack at ingress** — backend returns `202 {eventId, status: RECEIVED, regulationId, newVersionId}`;
   duplicate content is deduped (no new event).
3. **process** — workflow picks up `RECEIVED` events newer than the watermark,
   runs `docproc /process` (writes `storage/processed/<regId>/v<n>.txt` + manifest)
   then `ai /analyze` (writes `storage/analysis/<regId>/v<n>.json`).
4. **alert** — ai (or the backend) creates alerts with `status: PENDING`;
   the workflow emails every `emailRecipients` on each PENDING alert.
5. **ack at egress** — `PATCH /api/alerts/{id}/status {"status": "SENT"}` closes the loop.
   A failed send leaves the alert PENDING so it is retried; the PATCH is the only thing that
   marks an alert done.

## 6. Smoke test

```powershell
docker compose ps                       # n8n healthy (healthcheck hits /healthz)
Invoke-RestMethod http://localhost:5678/healthz
# UI → open the workflow → "Execute workflow" once; then check Executions for the run
```

See `docs/operations.md` for the full bring-up order and curl/PowerShell smoke checks.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `$env.ADMIN_EMAIL` undefined | `N8N_BLOCK_ENV_ACCESS_IN_NODE` must be `false` (set in compose). |
| Gmail node "credential not found" | Attach a real credential (§4) — the `{{GMAIL_...}}` placeholder is intentional. |
| Duplicate workflows in the list | `import:workflow` was run twice — delete the extra, or wipe the `n8n-data` volume. |
| Events processed twice | Watermark only persists for active executions; activate the workflow and check `staticData.lastEventId`. |
| `monitor`/`docproc`/`ai` unreachable | Their services must be up and on the compose network (`docker compose up -d monitor docproc ai`); HTTP errors here are non-fatal by design (`onError: continueRegularOutput`). |
| Emails sent but alert still PENDING | `Mark Alert Sent` PATCH failed — check the execution and backend auth (token expired mid-run → re-run; login happens every execution). |
