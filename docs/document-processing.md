# Document Processing (docproc)

Phase 3 of the regulatory-update-tracking prototype. The service turns a
gazette/document source (URL or local file) into the normalised text +
manifest that the **ai** role analyses. Contracts come from
`.agents/PLAN.md` §2.3 (storage/manifest) and §2.5 (HTTP surface).

Source: `services/docproc/` · Port **8102** · CLI `python -m docproc.main`

## 1. Pipeline

```
input (URL / path)
   │  fetch.py  — httpx stream (30 s timeout, 50 MB cap) or local copy
   ▼
storage/raw/<nameHint>_<sha256[:8]>_<basename>
   │  extract.py — magic-byte + content-type dispatch
   ▼
raw text (PDF pages separated by form-feed \f)      method: pdf | html | ocr
   │  clean.py  — normalisation (see §3)
   ▼
storage/processed/<regulationId>/v<n>.txt           content_sha256 = SHA-256(utf-8)
storage/processed/<regulationId>/manifest.json      + version-pinned v<n>.manifest.json
```

Raw filenames are deterministic per `(name hint, input spec)`, so re-running
the same input overwrites the same raw file (idempotent).

## 2. Format detection and extraction

Detection order in `extract.py`: magic bytes → served/detected content type →
file suffix → UTF-8/HTML sniff. Mislabelled servers (PDF served as
`text/plain`) are therefore still handled.

| Kind | Method | Path |
|---|---|---|
| PDF with text layer (≥ 50 chars/page) | `pdf` | PyMuPDF `page.get_text("text")` per page |
| PDF without text layer (scanned) | `ocr` | OCR path, see §4 |
| HTML/XHTML | `html` | BeautifulSoup (`lxml`, fallback `html.parser`): drops `script/style/noscript/template/svg/iframe`, `<br>` → newline, block tags → paragraph boundaries |
| PNG/JPEG/TIFF/GIF/BMP/WebP | `ocr` | OCR path, see §4 |
| Plain text (`.txt`/`.md`/decodable bytes) | `html` | decoded as-is (markup/text pipeline) |

`ocr_used` is `true` only when OCR actually produced text.

## 3. Cleaning rules (`clean.py`, in order)

1. `\r\n` / `\r` → `\n`
2. **Unicode NFKC** — ligatures (`ﬁ`→`fi`), full-width forms, circled digits
   (`①`→`1`), non-breaking space → space
3. Smart characters unified — curly single/double quotes → `'`/`"`, en/em dash
   and minus → `-`, ellipsis → `...`, soft hyphen removed, bullet → `-`
4. **Page furniture stripped** (only when the text carries page separators):
   - first/last non-empty line of a page matching a page-number pattern
     (`42`, `Page 3`, `Page 3 of 12`, `- 4 -`) on multi-page documents
   - lines repeated as first or last line of ≥ 30 % of pages (min 2 pages)
     on ≥ 3-page documents → running headers/footers
5. **De-hyphenation** — `letter-` at end of line followed by a lowercase
   letter on the next line is re-joined (`inter-\nnational` → `international`);
   runs across page boundaries as well
6. Whitespace collapsed — space/tab runs → single space, line-edge spaces
   trimmed, ≥ 3 newlines → blank line

Paragraph structure is preserved: paragraph breaks survive as `\n\n`, line
breaks inside paragraphs survive as single `\n`.

## 4. OCR behaviour (guarded degradation)

Tesseract is **not installed on the dev host** (PLAN.md §6). Everything is
behind `ocr_available()` → `shutil.which("tesseract")` + import check:

| Situation | Result |
|---|---|
| Tesseract present, PDF scanned | 200 dpi page renders → pytesseract (30 s/page timeout) → `method:"ocr"`, `ocr_used:true` |
| Tesseract present, per-page failure/timeouts | successful pages kept; failures listed in `note`; `ocr_used` reflects whether any text came back |
| Tesseract **absent** | no subprocess launched (cannot hang) → `method:"ocr"`, `ocr_used:false`, `note:"OCR skipped: tesseract binary not found on PATH ..."` |
| OCR path selected but zero text overall | `EmptyContentError` → CLI exit 1 / HTTP 422; **no** empty `v<n>.txt` or manifest is written |

The situation is always recorded (`ocr_used` + `note` in the manifest, or the
error message when nothing was extractable); the pipeline never crashes on a
missing binary.

## 5. Manifest contract (docproc → ai)

Written to `storage/processed/<regulationId>/manifest.json` (canonical) and
`storage/processed/<regulationId>/v<n>.manifest.json` (version-pinned copy, so
analysing an older version after a newer one still finds matching metadata).

| Field | Type | Notes |
|---|---|---|
| `regulation_id` | int | echo of request |
| `version_no` | int | echo of request |
| `source` | string | e.g. `RBI`, `MCA`, `SEBI` |
| `source_url` | string | URL input → the URL; local path → `""` |
| `method` | `html` \| `pdf` \| `ocr` | pipeline used |
| `content_path` | string | posix path relative to storage parent — `storage/processed/<id>/v<n>.txt` in the default layout |
| `content_sha256` | string | SHA-256 of the cleaned UTF-8 text bytes |
| `char_count` | int | `len(cleaned_text)` |
| `ocr_used` | bool | true only if OCR produced text |
| `extracted_at` | string | UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `pipeline_version` | string | `"1.0"` |
| `note` | string \| null | **additive** — OCR/degradation situation, else `null` |

Downstream diffing: previous text is at
`storage/processed/<regulationId>/v<(n-1)>.txt` (PLAN.md §2.4).

## 6. Interfaces

### CLI

```powershell
cd D:\AI_Hack\services\docproc
D:\AI_Hack\.venv\Scripts\python.exe -m docproc.main `
  --input <url|path> --regulation-id 1 --version 2 [--source RBI] [--storage-root <dir>]
```

stdout = manifest JSON; handled errors → stderr, exit code 1.

### HTTP (§2.5)

- `POST /process` `{input, regulation_id, version_no, source}` → manifest JSON
- `GET /health` → `{"status":"ok","service":"docproc","ocr_available":bool}`
- handled pipeline errors → `422 {"error":"<ExceptionName>","detail":"..."}`;
  validation errors → FastAPI `422`

### Environment

| Var | Default | Purpose |
|---|---|---|
| `STORAGE_ROOT` | auto-detect `<project>/storage` | storage root override |
| `DOCPROC_PORT` | `8102` | port for `python -m docproc.api` |

## 7. Verification

```powershell
D:\AI_Hack\.venv\Scripts\python.exe -m compileall -q D:\AI_Hack\services\docproc
D:\AI_Hack\.venv\Scripts\python.exe -m pytest D:\AI_Hack\services\docproc\tests -q
```

Tests build multi-page PDFs with PyMuPDF in temp dirs and cover: extraction,
cleaning rules, manifest schema/sha, CLI, HTTP wrapper, and the tesseract-absent
OCR fallback (fast, non-crashing, `ocr_used:false`).

## 8. Known limitations

- Header/footer stripping is heuristic (page-separator based); single-page
  inputs keep their lone page-number line.
- Scanned PDFs cannot produce text on the dev host until tesseract is
  installed (`extra-deps` recorded in `.agents/status/docproc.md`); Docker
  image ships with it.
- `content_path` assumes the storage root sits directly under the project root
  (true in both dev and the Docker `STORAGE_ROOT=/data/storage` layout).
