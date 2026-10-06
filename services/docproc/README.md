# docproc — Document Processing Service (Phase 3)

Retrieves gazette/document sources, extracts text (PDF / HTML / OCR), normalises
it, and writes the processed version plus the manifest consumed by the **ai**
role. Part of the regulatory-update-tracking prototype (see
`D:\AI_Hack\.agents\PLAN.md`).

## Layout

```
services/docproc/
  docproc/
    fetch.py       download URL (httpx) or copy local path into storage/raw/
    extract.py     PyMuPDF text, BeautifulSoup HTML, guarded pytesseract OCR
    clean.py       NFKC, de-hyphenation, header/footer/page-number stripping
    process.py     orchestrator: writes v<n>.txt + manifest.json
    main.py        CLI: python -m docproc.main
    api.py         FastAPI wrapper, port 8102 (POST /process, GET /health)
    paths.py       storage-root resolution (STORAGE_ROOT env / project root)
    exceptions.py  DocprocError hierarchy
  tests/           pytest self-tests (no network, no tesseract needed)
  Dockerfile       python:3.12-slim + tesseract-ocr
  requirements.txt
```

Storage follows PLAN.md §2.3 (override root with `STORAGE_ROOT`):

```
storage/raw/                      downloaded originals (deterministic names)
storage/processed/<regId>/v<n>.txt
storage/processed/<regId>/manifest.json
storage/processed/<regId>/v<n>.manifest.json   (version-pinned copy)
```

## CLI

Run from `services/docproc` (so `docproc` is importable):

```powershell
cd D:\AI_Hack\services\docproc
D:\AI_Hack\.venv\Scripts\python.exe -m docproc.main `
  --input https://www.rbi.org.in/Notification.pdf `
  --regulation-id 1 --version 2 --source RBI
```

`--input` accepts an http(s) URL, `file://` URL, or a local path.
Prints the manifest JSON to stdout; exit code `1` + stderr message on failure.

## HTTP API (port 8102)

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m docproc.api     # or: uvicorn docproc.api:app --port 8102
```

| Method | Path | Body | Result |
|---|---|---|---|
| POST | /process | `{"input","regulation_id","version_no","source"}` | manifest JSON (200) |
| GET | /health | – | `{"status","service","ocr_available"}` |

Handled pipeline errors return `422` with `{"error": "<ExceptionName>", "detail": "..."}`.

## Manifest (docproc → ai, PLAN.md §2.3)

```json
{"regulation_id":1,"version_no":2,"source":"RBI","source_url":"https://...",
 "method":"html|pdf|ocr","content_path":"storage/processed/1/v2.txt",
 "content_sha256":"...","char_count":1234,"ocr_used":false,
 "extracted_at":"2026-10-03T12:00:00Z","pipeline_version":"1.0","note":null}
```

`note` is additive: it records OCR/degradation situations and is `null`
otherwise. `content_sha256` is SHA-256 of the cleaned UTF-8 text.
`source_url` is `""` for local-path inputs.

## OCR behaviour

The tesseract **binary is not installed** on the dev host. The OCR path is
behind `shutil.which("tesseract")`:

- text-layer PDF → `method:"pdf"`, `ocr_used:false`
- image-only/scanned PDF or image file, tesseract present → `method:"ocr"`,
  `ocr_used:true` (page renders at 200 dpi, 30 s per-page timeout)
- tesseract absent → never crashes/hangs: `method:"ocr"`, `ocr_used:false`,
  `note:"OCR skipped: tesseract binary not found on PATH ..."`; if no fallback
  text exists either, `EmptyContentError` is raised (422 over HTTP).

The Docker image installs `tesseract-ocr`, so containers run real OCR.

## Tests

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services\docproc
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\docproc\tests -q
```

Tests generate their own PDFs/HTML in temp dirs; no network access, no
tesseract required.
