---
role: monitor
status: DONE
updated: 2026-10-03T08:22:00Z
---
## Artifacts
- D:\AI_Hack\services\monitor\monitor\__init__.py — package marker, version 1.0.0
- D:\AI_Hack\services\monitor\monitor\sources.yaml — watch list MCA/RBI/SEBI (URLs = seeded regulation_sources watchUrl/baseUrl)
- D:\AI_Hack\services\monitor\monitor\config.py — Settings/SourceConfig, env vars per PLAN.md §2.1 (API_BASE, WEBHOOK_SECRET, MONITOR_*), repo-root discovery
- D:\AI_Hack\services\monitor\monitor\retriever.py — httpx/requests + BeautifulSoup/lxml; guarded optional playwright/firecrawl (degrade to http with warning); file:// engine; 3-attempt retry on 429/5xx/network
- D:\AI_Hack\services\monitor\monitor\snapshots.py — storage/snapshots/<code>/{latest.txt,latest.html,latest.meta.json,history/,diffs/}; sha256 compare + difflib unified diff
- D:\AI_Hack\services\monitor\monitor\notifier.py — ASCII-safe JSON (ensure_ascii, compact) + X-Webhook-Signature: sha256=<hex hmac(raw_body, secret)> over exact transmitted bytes
- D:\AI_Hack\services\monitor\monitor\runner.py — MonitorRunner: fetch → detect → save+diff → notify; injectable fetcher/notifier/store for tests
- D:\AI_Hack\services\monitor\monitor\main.py — CLI: --once (default), --interval SECONDS, --dry-run (prints signed headers), --source CODE, --config PATH, --log-level
- D:\AI_Hack\services\monitor\monitor\service.py — FastAPI wrapper: POST /run → {"checked":n,"changed":[url...]}, GET /health (port 8101 per PLAN.md §2.5)
- D:\AI_Hack\services\monitor\tests\conftest.py — sys.path bootstrap for pytest
- D:\AI_Hack\services\monitor\tests\fixtures\page_v1.html — fixture baseline page
- D:\AI_Hack\services\monitor\tests\fixtures\page_v2.html — fixture changed page
- D:\AI_Hack\services\monitor\tests\test_change_detection.py — DoD self-test: v1 → baseline, v1 → no event, v2 → change + diff + contract payload + independently verified HMAC; dry-run, ascii-safety, notify_initial=false, file:// engine, snapshot roundtrip
- D:\AI_Hack\services\monitor\tests\test_config.py — sources.yaml contract (MCA/RBI/SEBI URLs) + settings defaults + empty-config rejection
- D:\AI_Hack\services\monitor\tests\test_live_backend.py — one real signed event to https://www.rbi.org.in/test-monitor-selftest.html, expects HTTP 202 (skips if backend down)
- D:\AI_Hack\services\monitor\requirements.txt — runtime deps (no playwright/firecrawl)
- D:\AI_Hack\services\monitor\Dockerfile — python:3.12-slim, uvicorn :8101, MONITOR_STORAGE_DIR=/data/snapshots, healthcheck
- D:\AI_Hack\services\monitor\README.md — usage, env table, CLI, HTTP API, contract, tests, docker
- D:\AI_Hack\docs\monitoring.md — architecture, detection algorithm, webhook signing, failure modes, troubleshooting
- D:\AI_Hack\storage\snapshots\{MCA,RBI,SEBI}\ — runtime baselines written during verification (latest/history/diffs/meta)
- D:\AI_Hack\.agents\status\monitor.md — this status file

## Verification
- `D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services\monitor` → PASS (clean, exit 0)
- `D:\AI_Hack\.venv\Scripts\python.exe -c "import monitor.config, ... , monitor.service"` → PASS (all modules import)
- `D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\monitor\tests -q` → **10 passed, 0 failed, 0 skipped** (includes live 202 test + DoD fixture self-test)
- CLI `python -m monitor.main --once --dry-run` (workdir services\monitor) → JSON `{"checked":3,"changed":[RBI url],"errors":[]}`, signed headers printed, nothing sent (httpx log: "would POST")
- CLI `python -m monitor.main --interval 4 --dry-run --source SEBI` →3 cycles in 11s, clean KeyboardInterrupt stop, no port leak
- FastAPI :8101 → `GET /health` = `{"status":"ok","service":"monitor","engines":{"http":true,"playwright":false,"firecrawl":false}}`; `POST /run {"dry_run":true,"sources":["SEBI"]}` = `{"checked":1,"changed":[]}`; `POST /run` with no body = `{"checked":3,"changed":[MCA watch_url]}` (body optional per contract)
- Backend acceptance (admin JWT, GET /api/events): event 84 = self-test URL → regulationId 28, `newVersionId: null` proves content-hash dedupe; event 85 = MCA watch URL initial → regulationId 55, newVersionId 73 (both delivered with 202)
- Snapshot layout on disk: `storage/snapshots/<code>/{latest.txt,latest.html,latest.meta.json,history/<ts>.{txt,html},diffs/<ts>.diff}` for all three codes
- No stray process on 8101 after verification

## Handoff notes
- **Webhook contract (PLAN.md §1.2) fully implemented**: body keys exactly `url,title,source_code,content,timestamp`, serialised `ensure_ascii=True` compact, header `X-Webhook-Signature: sha256=<hex hmac-sha256(raw_body, WEBHOOK_SECRET)>` over the exact bytes sent; expect 202 `{eventId,status,regulationId,newVersionId,receivedAt}`. Backend-verified live.
- **Env**: `API_BASE` (default http://localhost:8080), `WEBHOOK_SECRET` (default `dev-webhook-shared-secret-please-change`), `MONITOR_STORAGE_DIR` (default `<repo>/storage/snapshots`, Docker `/data/snapshots`), `MONITOR_SOURCES_FILE`, `MONITOR_NOTIFY_INITIAL` (default **true** → first fetch of a URL notifies and creates regulation v1), `MONITOR_PAYLOAD_MODE` (`text` default, `html` optional), `MONITOR_TIMEOUT`, `FIRECRAWL_API_KEY/_API_URL`.
- **docproc**: monitor does not write `storage/raw`; your raws come from your own downloads. `storage/snapshots/<code>/latest.meta.json` gives `{url,title,engine,status_code,fetched_at,sha256}` if you need the source URL/hash; `latest.txt` is clean extracted text; `diffs/*.diff` are old→new unified diffs. Webhook `content` (normalised text) is what the backend stores as version content.
- **ai**: change events originate here; identical content twice ⇒ backend dedupe (no new version). Diff history lives in `storage/snapshots/<code>/diffs/`; per PLAN.md §2.4 keep using `storage/processed/<regId>/v<n-1>.txt` as old text.
- **ops**: service entry is `uvicorn monitor.service:app --port 8101` (or `python -m monitor.main --interval N` for polling mode); Dockerfile owned by monitor at `services/monitor/Dockerfile` — wire it into docker-compose as service `monitor` with `API_BASE=http://backend:8080`, shared `WEBHOOK_SECRET`, volume `./storage/snapshots:/data/snapshots`, port `8101:8101`. n8n can simply POST `http://monitor:8101/run`.
- **qa**: monitor tests live at `services/monitor/tests/` (repo-root `tests/` is yours). `test_live_backend.py` sends one signed probe to `https://www.rbi.org.in/test-monitor-selftest.html` when :8080 is up (skips offline); regulations/events with that URL are intentional test data (regulationId 28). MCA watch-URL regulation = id 55.
- **sources.yaml must stay aligned with seeded regulation_sources** (MCA/RBI/SEBI codes + watch URLs); `tests/test_config.py` enforces it — update both together if seeds change.
- Engines: playwright/firecrawl are guarded and absent — page fetches use httpx; `engine: playwright` in YAML degrades to http with a warning until ops installs browsers.

## Extra deps / unresolved issues
- extra-deps: none (all packages pre-installed per PLAN.md §6)
- RBI WAF: server-side GETs of `BS_ViewMasNotifications.aspx` are redirected to `Error.aspx` from this host even with a browser UA → the baseline stored for RBI is the WAF page (stable, so no event spam). Real RBI content monitoring needs the `playwright` engine (guarded, not installed) or the changedetection.io container already in compose — ops decision.
- MCA WAF: intermittently 403s; plain `Mozilla/5.0` UA (default, full Chrome strings are rejected) + 3-attempt retry mitigates; per-source `user_agent` override available in sources.yaml.
- The self-test event was re-sent on each pytest iteration while developing (identical content ⇒ backend created one version, several ChangeEvent rows for the test URL). A non-dry real `--once` was NOT run to avoid further events; the send path is proven by events 84/85 above.
- No retention policy for history/diffs yet (they grow unbounded); add pruning if ops needs it.
