# Website Monitoring (Phase 2)

The **monitor** service watches the seeded regulation sources, detects content
changes and pushes signed change events into the backend, which creates
regulations/versions and change events consumed downstream by **docproc**,
**ai** and the dashboard.

## 1. Architecture

```
sources.yaml (MCA / RBI / SEBI)
        │
        ▼
┌──────────────── monitor (services/monitor) ────────────────┐
│ retriever ──► snapshot store ──► change detection          │
│ (httpx+BS4,   storage/snapshots/  sha256 + difflib diff    │
│  optional      <CODE>/latest+history+diffs                 │
│  playwright/   notifier: ASCII-safe JSON + HMAC-SHA256      │
│  firecrawl)          │                                     │
└──────────────────────┼─────────────────────────────────────┘
                       ▼  POST {API_BASE}/api/webhooks/changedetection
        backend (8080) ── 202 {eventId, regulationId, newVersionId}
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
 storage/raw (docproc)        storage/processed → ai → alerts
```

Run modes:

| Mode | Command | Behaviour |
|---|---|---|
| One-shot | `python -m monitor.main --once` | single cycle, JSON summary on stdout |
| Polling | `python -m monitor.main --interval 3600` | cycle every N seconds |
| Dry run | add `--dry-run` | detect + print signed headers, **never** POST |
| Service | `uvicorn monitor.service:app --port 8101` | `POST /run`, `GET /health` |

Scheduler ownership: the CLI can poll itself (`--interval`), but the intended
production wiring is the compose service (ops) plus an n8n timer that calls
`POST http://monitor:8101/run` — both are equivalent, they share the same
snapshot state on disk.

## 2. Change detection

1. **Retrieve** the watch URL (`httpx` primary, `requests` fallback,
   BeautifulSoup + lxml for parsing). Optional engines:
   - `playwright` — guarded import; **not installed** in the shared venv,
     degrades to `http` with a warning.
   - `firecrawl` — requires `FIRECRAWL_API_KEY`; REST call via `httpx`
     (SDK used only if importable), degrades to `http` without a key.
2. **Normalise** — drop `script/style/noscript/svg`, collapse whitespace,
   remove blank lines → `latest.txt` becomes the canonical hash input.
3. **Compare** — `sha256(new_text)` vs `sha256(latest.txt)`.
   - no baseline yet → *initial snapshot* (notified when
     `MONITOR_NOTIFY_INITIAL=true`, the default).
   - equal → nothing is written (history only grows on real changes).
   - different → persist snapshot + `difflib.unified_diff`.
4. **Notify** the backend, then store the response (`202` ⇒ `notified`).

Snapshots live under `storage/snapshots/<CODE>/` (PLAN.md §2.3):

```
latest.txt | latest.html | latest.meta.json
history/<YYYYmmddTHHMMSSffffff>.{txt,html}
diffs/<YYYYmmddTHHMMSSffffff>.diff
```

`latest.meta.json` records `url, title, engine, status_code, fetched_at, sha256`
— the sha256 is the same value the backend stores as `contentHash`, so the two
layers stay comparable.

## 3. Webhook contract (PLAN.md §1.2)

```json
{"url":"https://www.rbi.org.in/...","title":"...",
 "source_code":"RBI","content":"<clean text or raw html>",
 "timestamp":"2026-10-03T12:00:00Z"}
```

* Serialised with `ensure_ascii=True`, compact separators → the raw body is
  guaranteed ASCII, so UTF-8/ISO-8859-1 decoding differences cannot break the
  signature.
* Header: `X-Webhook-Signature: sha256=<hex hmac-sha256(raw_body, WEBHOOK_SECRET)>`
  computed over the **exact bytes transmitted** (no re-serialisation on the
  wire). The backend accepts the token alternative `X-Webhook-Token` but the
  monitor always signs.
* `content` defaults to normalised text (`MONITOR_PAYLOAD_MODE=html` for raw).
  Identical content twice ⇒ backend keeps one version (dedupe by `contentHash`).
* Success = HTTP **202** with `{eventId,status,regulationId,newVersionId,receivedAt}`.

## 4. Configuration

See `services/monitor/README.md` for the full env-var table. Non-obvious ones:

* `MONITOR_NOTIFY_INITIAL=false` — treat the first fetch as a silent baseline
  (useful in CI so a fresh run does not create backend noise).
* `MONITOR_STORAGE_DIR` — snapshot root; in Docker it is `/data/snapshots`
  (mount a volume so docproc sees the same files).
* `MONITOR_SOURCES_FILE` — swap in another `sources.yaml` (e.g. fixtures with
  `file://` URLs for offline demos).

## 5. Failure modes & troubleshooting

| Symptom | Cause | Handling |
|---|---|---|
| summary `errors[]` with `fetch failed` | site down / blocked / TLS | logged, other sources still checked, cycle exits 0 |
| `playwright engine requested but not installed` | JS-heavy page configured with `engine: playwright` | warning, falls back to `http` |
| `FIRECRAWL_API_KEY unset` | firecrawl engine without key | warning, falls back to `http` |
| HTTP 401 from webhook | `WEBHOOK_SECRET` mismatch | signature recomputed per request — check env matches backend |
| HTTP 400/500 from webhook | payload rejected | response body logged (300 chars) |
| no `diffs/` entries | content genuinely unchanged | by design: history grows only on change |

Dry-run first when debugging signing:

```powershell
cd D:\AI_Hack\services\monitor
D:\AI_Hack\.venv\Scripts\python.exe -m monitor.main --once --dry-run --source RBI
```

prints the exact `X-Webhook-Signature` header that would be sent.

## 6. Verification

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services\monitor
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\monitor\tests -q
```

The suite proves: fixture v1 → baseline, v1 again → no event, fixture v2 →
change detected, unified diff persisted, payload matches the contract,
signature equals an independently computed HMAC. `test_live_backend.py` sends
one signed self-test event (URL `https://www.rbi.org.in/test-monitor-selftest.html`)
when the backend is reachable and expects `202`; it skips cleanly offline.
