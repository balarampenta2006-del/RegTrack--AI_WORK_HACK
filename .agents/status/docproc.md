---
role: docproc
status: DONE
updated: 2026-10-03T08:11:27Z
---
## Artifacts
- `services/docproc/docproc/__init__.py` — package root, `__version__ = "1.0"`, re-exports `process`
- `services/docproc/docproc/fetch.py` — httpx streaming download (30 s timeout, 50 MB cap) + local-path/`file://` copy into `storage/raw/`, magic-byte content-type detection, deterministic raw names `<hint>_<sha256(spec)[:8]>_<basename>`
- `services/docproc/docproc/extract.py` — PyMuPDF text extraction, BeautifulSoup (`lxml`) HTML, guarded OCR (`shutil.which("tesseract")` + import check, 200 dpi / 30 s per page), image/text inputs
- `services/docproc/docproc/clean.py` — NFKC, smart-quote/dash unification, page-number + repeated header/footer stripping, EOL de-hyphenation, whitespace collapse, paragraph preservation
- `services/docproc/docproc/process.py` — orchestrator; writes `storage/processed/<regId>/v<n>.txt`, `manifest.json`, version-pinned `v<n>.manifest.json`
- `services/docproc/docproc/main.py` — CLI `python -m docproc.main --input <url|path> --regulation-id N --version N [--source RBI] [--storage-root D]`
- `services/docproc/docproc/api.py` — FastAPI wrapper, port 8102 (`POST /process`, `GET /health`)
- `services/docproc/docproc/paths.py`, `exceptions.py` — storage-root resolution (`STORAGE_ROOT` env → project-root detection), `DocprocError` hierarchy
- `services/docproc/tests/` — 29 pytest self-tests (conftest + clean/extract/process/api/main)
- `services/docproc/Dockerfile` — python:3.12-slim, installs `tesseract-ocr`, uvicorn on 8102, `STORAGE_ROOT=/data/storage`
- `services/docproc/requirements.txt`, `services/docproc/README.md`
- `docs/document-processing.md` — full pipeline/contract documentation
- `storage/raw/`, `storage/processed/` — created (my §2.3 subfolders)

## Verification
- `D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services\docproc` → OK (exit 0)
- `D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\docproc\tests -q` → **29 passed** (PDF generation with PyMuPDF, extraction, cleaning rules, manifest schema + sha256, OCR-absent fallback, CLI, FastAPI TestClient)
- Live API smoke: `python -m docproc.api` → `GET http://localhost:8102/health` → `{"status":"ok","service":"docproc","ocr_available":false}`; `POST /process` with a generated PDF → 200, manifest with `method:"pdf"`, `ocr_used:false`, `content_path:"storage/processed/42/v1.txt"` (server stopped after test)
- CLI smoke: `python -m docproc.main --input ... --regulation-id 42 --version 1` → exit 0, manifest on stdout, de-hyphenation visible in `v1.txt` ("hyphen- / ated" → "hyphenated"); smoke artifacts cleaned afterwards
- `shutil.which("tesseract")` → `None` (host) — degraded OCR path exercised by tests (no crash, no hang, <10 s)

## Handoff notes
- **ai role — manifest fields (PLAN §2.3, all guaranteed):** `regulation_id` int, `version_no` int, `source` str, `source_url` str (`""` for local-path input), `method` `"html"|"pdf"|"ocr"`, `content_path` str (`storage/processed/<id>/v<n>.txt` in the default layout; resolve against the storage root's **parent**), `content_sha256` str (SHA-256 of cleaned UTF-8 text bytes — equals sha256 of `v<n>.txt` on disk), `char_count` int (`len(cleaned text)`), `ocr_used` bool (true only if OCR produced text), `extracted_at` str (UTC `YYYY-MM-DDTHH:MM:SSZ`), `pipeline_version` `"1.0"`.
- **One additive field:** `note` (str|null) — records OCR/degradation situations, `null` otherwise; ignore if not needed. All §2.3 fields are present with exactly the specified names/types.
- Manifest locations: canonical `storage/processed/<id>/manifest.json` (overwritten by later versions) **plus** version-pinned `storage/processed/<id>/v<n>.manifest.json` — ai should prefer the version-pinned copy when analysing `v<n>`.
- Old text for diff per §2.4: `storage/processed/<regId>/v<n-1>.txt`.
- If `process` cannot extract text (e.g. scanned PDF on a host without tesseract) it raises `EmptyContentError` → CLI exit 1 / HTTP 422 `{"error":"EmptyContentError","detail":...}`; **no** empty `v<n>.txt` or manifest is written.
- **Assumptions:** contracts in PLAN.md §2 hold (upstream roles not yet DONE); storage root auto-detects `D:\AI_Hack\storage` via `.agents/`, overridable with `STORAGE_ROOT`; plain-text inputs report `method:"html"` (markup/text pipeline) since §2.3 allows only three method values; content capped at 50 MB, HTTP timeout 30 s (never hangs).
- Tests: run with `D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\docproc\tests -q` from any cwd (tests bootstrap `sys.path`); roles importing `docproc` directly need `PYTHONPATH=D:\AI_Hack\services\docproc` or cwd=`services/docproc`.
- Dockerfile installs `tesseract-ocr`, so the containerised service performs real OCR (`ocr_used:true`); ops must mount/set `STORAGE_ROOT=/data/storage` for shared storage (compose is ops-owned).

## Extra deps / unresolved issues
- extra-deps: none (tesseract binary intentionally NOT installed on host; guarded fallback covers it — real OCR only inside the Docker image)
- unresolved: Docker image not built/smoke-tested here (ops owns compose); `docs/document-processing.md` §8 lists heuristic limitations (single-page inputs keep a lone page-number line)
