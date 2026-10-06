# regtrack-monitor

Government website change detection (Phase 2). Watches the seeded regulation
sources **MCA**, **RBI**, **SEBI**, stores snapshots under
`storage/snapshots/<code>/`, detects changes (sha256 + unified diff) and posts
an HMAC-signed event to the backend webhook.

## Layout

```
monitor/
  sources.yaml    watch list (codes/URLs match seeded regulation_sources)
  config.py       env-var settings (API_BASE, WEBHOOK_SECRET, ...)
  retriever.py    httpx/requests + BeautifulSoup; optional playwright/firecrawl
  snapshots.py    storage/snapshots/<code>/{latest,history,diffs}
  notifier.py     ASCII-safe JSON payload + sha256= HMAC header
  runner.py       one full check cycle (fetch → detect → notify)
  main.py         CLI entry point
  service.py      FastAPI wrapper (port 8101)
tests/            pytest self-tests + HTML fixtures
```

## Configuration (PLAN.md §2.1)

| Env var | Default | Purpose |
|---|---|---|
| `API_BASE` | `http://localhost:8080` | backend base URL |
| `WEBHOOK_SECRET` | `dev-webhook-shared-secret-please-change` | HMAC secret |
| `MONITOR_STORAGE_DIR` | `<repo>/storage/snapshots` | snapshot root |
| `MONITOR_SOURCES_FILE` | `monitor/sources.yaml` | watch list override |
| `MONITOR_NOTIFY_INITIAL` | `true` | notify on the first-ever snapshot |
| `MONITOR_PAYLOAD_MODE` | `text` | `text` or `html` for `content` |
| `MONITOR_TIMEOUT` | `30` | fetch timeout (seconds) |
| `FIRECRAWL_API_KEY` | unset | enables the optional `firecrawl` engine |

## CLI

```powershell
cd D:\AI_Hack\services\monitor
D:\AI_Hack\.venv\Scripts\python.exe -m monitor.main --once
D:\AI_Hack\.venv\Scripts\python.exe -m monitor.main --once --dry-run        # print signed headers, send nothing
D:\AI_Hack\.venv\Scripts\python.exe -m monitor.main --interval 3600 --source RBI
D:\AI_Hack\.venv\Scripts\python.exe -m monitor.main --once --config path\to\sources.yaml
```

Exit codes: `0` success, `2` configuration error, `1` interrupted polling.
Per-source fetch errors are reported in the JSON summary (`errors[]`), not fatal.

## HTTP service (port 8101, PLAN.md §2.5)

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m uvicorn monitor.service:app --port 8101
```

- `GET /health` → `{"status":"ok","service":"monitor",...}`
- `POST /run` → `{"checked":3,"changed":["https://..."]}`
  optional body: `{"dry_run": true, "sources": ["RBI"]}`

## Webhook contract (PLAN.md §1.2)

```json
{"url":"...","title":"...","source_code":"RBI","content":"...","timestamp":"2026-10-03T12:00:00Z"}
```

Body is serialised with `ensure_ascii=True`; header
`X-Webhook-Signature: sha256=<hex hmac-sha256(raw_body, WEBHOOK_SECRET)>`
is computed over the exact transmitted bytes. Backend answers `202` with
`{"eventId","status","regulationId","newVersionId","receivedAt"}`.

## Tests

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\monitor\tests -q
```

The live test (`test_live_backend.py`) sends **one** signed self-test event to
`https://www.rbi.org.in/test-monitor-selftest.html` when the backend is up on
localhost:8080 and skips otherwise.

## Docker

```bash
docker build -t regtrack-monitor ./services/monitor
docker run -p 8101:8101 -e API_BASE=http://backend:8080 regtrack-monitor
```

Snapshots persist in the `/data/snapshots` volume (mount it to share with
docproc). The compose wiring lives in `docker-compose.yml` (ops owns it).
