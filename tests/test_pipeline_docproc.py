"""Pipeline accuracy fixtures for document processing (PLAN §3, docproc).

Author-level accuracy tests over the real services/docproc package:
a sample old/new gazette snippet must be fetched, extracted, cleaned into
stable markup-free text and manifested per PLAN §2.3.

All pipeline runs use an isolated temporary storage root so nothing in
D:\\AI_Hack\\storage is touched.
"""

import uuid

import pytest

from pipeline_support import (find_callable, import_service_modules,
                              service_available)
from test_storage_contracts import validate_manifest

pytestmark = pytest.mark.skipif(
    not service_available("docproc"),
    reason="services/docproc not present yet (docproc agent pending - will enable on re-run)")

SAMPLE_OLD_GAZETTE = """
<html><head><title>RBI/2026-27/15</title>
<script>var x = 'tracking';</script>
<style>.hdr{color:red}</style></head>
<body>
<div class="header">RESERVE BANK OF INDIA</div>
<h1>Notification on Digital Lending Platforms</h1>
<p>  The Reserve Bank of India, in exercise of the powers conferred by Section
  45L of the RBI Act, 1934, hereby prescribes the following guidelines   </p>
<p>1. All Regulated Entities shall ensure that the Loan Service Providers
   follow fair practices Code.</p>
<p>Issue: August 15, 2026</p>
</body></html>
"""

SAMPLE_NEW_GAZETTE = """
<html><head><title>RBI/2026-27/42</title>
<script>var x = 'tracking';</script></head>
<body>
<div class="header">RESERVE BANK OF INDIA</div>
<h1>Notification on Digital Lending Platforms (Amended)</h1>
<p>  The Reserve Bank of India, in exercise of the powers conferred by Section
  45L of the RBI Act, 1934, hereby prescribes the following guidelines   </p>
<p>1. All Regulated Entities shall ensure that the Loan Service Providers
   follow fair practices Code.</p>
<p>2. NEW: Regulated Entities shall maintain a public register of all
   loan service providers within 30 days.</p>
<p>Issue: October 01, 2026</p>
</body></html>
"""

KEY_PHRASE = "Reserve Bank of India"


@pytest.fixture(scope="module")
def docproc():
    """Resolve the real docproc entry points (extract / clean_text / process)."""
    modules, errors = import_service_modules("docproc")
    if not modules:
        pytest.skip(f"services/docproc: no modules importable ({errors[:3]})")
    return {
        "extract": find_callable(modules, ("extract",), "docproc"),
        "clean_text": find_callable(modules, ("clean_text",), "docproc"),
        "process": find_callable(modules, ("process",), "docproc"),
    }


def _reg_id() -> int:
    # High random id so tests never collide with real regulation ids.
    return 900_000 + uuid.uuid4().int % 90_000


# --------------------------------------------------------------------------
# Accuracy: extract + clean over a gazette snippet
# --------------------------------------------------------------------------

def test_extract_strips_markup_and_scripts(docproc, tmp_path):
    html_file = tmp_path / "gazette.html"
    html_file.write_text(SAMPLE_OLD_GAZETTE, encoding="utf-8")

    result = docproc["extract"](html_file)
    assert result.method == "html"
    assert result.ocr_used is False
    text = result.text
    assert KEY_PHRASE.lower() in text.lower()
    assert "<script" not in text.lower()
    assert "<html" not in text.lower()


def test_cleaning_produces_stable_markup_free_text(docproc, tmp_path):
    html_file = tmp_path / "gazette.html"
    html_file.write_text(SAMPLE_OLD_GAZETTE, encoding="utf-8")

    extracted = docproc["extract"](html_file).text
    cleaned_1 = docproc["clean_text"](extracted)
    cleaned_2 = docproc["clean_text"](extracted)

    assert isinstance(cleaned_1, str)
    assert cleaned_1.strip(), "cleaning produced empty text"
    assert KEY_PHRASE.lower() in cleaned_1.lower(), (
        f"key gazette phrase lost during cleaning: {cleaned_1[:300]!r}")
    assert "<script" not in cleaned_1.lower()
    assert "<html" not in cleaned_1.lower()
    assert cleaned_1 == cleaned_2, "cleaning is not deterministic"


def test_cleaning_keeps_new_clause_and_differs_from_old(docproc, tmp_path):
    old_file = tmp_path / "old.html"
    new_file = tmp_path / "new.html"
    old_file.write_text(SAMPLE_OLD_GAZETTE, encoding="utf-8")
    new_file.write_text(SAMPLE_NEW_GAZETTE, encoding="utf-8")

    cleaned_old = docproc["clean_text"](docproc["extract"](old_file).text)
    cleaned_new = docproc["clean_text"](docproc["extract"](new_file).text)

    assert "public register" in cleaned_new.lower(), (
        "new regulatory clause lost by the pipeline")
    assert cleaned_new != cleaned_old, "old vs new must differ for diffing"
    assert KEY_PHRASE.lower() in cleaned_old.lower()


# --------------------------------------------------------------------------
# clean_text unit accuracy (normalisation rules)
# --------------------------------------------------------------------------

def test_clean_text_normalises_unicode(docproc):
    raw = "Caf\u00e9 \ufb01le \u2014 \u201cquoted\u201d\u00a0text\u00ad."
    out = docproc["clean_text"](raw)
    assert "\ufb01" not in out and "fi" in out, "ligature not expanded"
    assert "\u2014" not in out and "-" in out, "em dash not unified"
    assert "\u201c" not in out and '"' in out, "smart quotes not unified"
    assert "\u00a0" not in out, "NBSP not normalised"


def test_clean_text_collapses_whitespace(docproc):
    raw = "Line   one\t\ttwo\n\n\n\nThree"
    out = docproc["clean_text"](raw)
    assert "   " not in out, "runs of spaces not collapsed"
    assert "\t" not in out, "tabs not collapsed"
    assert "\n\n\n" not in out, "blank-line runs not collapsed"
    assert "Line one two" in out


def test_clean_text_strips_page_numbers(docproc):
    raw = "page 12\nBody A\fpage 12\nBody B\fpage 12\nBody C"
    out = docproc["clean_text"](raw)
    assert "page 12" not in out.lower(), "page-number furniture not stripped"
    for body in ("Body A", "Body B", "Body C"):
        assert body in out, f"{body} lost while stripping page furniture"


def test_clean_text_rejoins_line_end_hyphenation(docproc):
    raw = "The Regulated Enti-\nty shall comply."
    out = docproc["clean_text"](raw)
    assert "Enti- \nty" not in out and "Entity" in out


def test_clean_text_is_deterministic_for_plain_text(docproc):
    raw = "RBI circular 2026-27: the caption    text remains intact.\nSecond line."
    assert docproc["clean_text"](raw) == docproc["clean_text"](raw)


# --------------------------------------------------------------------------
# Full pipeline: manifest per PLAN §2.3 in an isolated storage root
# --------------------------------------------------------------------------

def test_process_pipeline_emits_valid_manifest(docproc, tmp_path):
    html_file = tmp_path / "circular.html"
    html_file.write_text(SAMPLE_NEW_GAZETTE, encoding="utf-8")
    storage = tmp_path / "storage"
    reg_id = _reg_id()

    manifest = docproc["process"](str(html_file), reg_id, 1, "RBI",
                                  storage_root=storage)

    errors = validate_manifest(manifest)
    assert not errors, f"manifest violates PLAN §2.3: {errors}"
    assert manifest["regulation_id"] == reg_id
    assert manifest["version_no"] == 1
    assert manifest["method"] in {"html", "pdf", "ocr"}
    assert manifest["ocr_used"] is False

    content_file = storage / "processed" / str(reg_id) / "v1.txt"
    assert content_file.is_file(), f"processed content missing: {content_file}"
    text = content_file.read_text(encoding="utf-8")
    assert "public register" in text.lower()
    assert "<script" not in text.lower()
    assert len(text) == manifest["char_count"]


def test_process_pipeline_is_deterministic(docproc, tmp_path):
    html_file = tmp_path / "circular.html"
    html_file.write_text(SAMPLE_OLD_GAZETTE, encoding="utf-8")

    texts = []
    for run in range(2):
        storage = tmp_path / f"storage{run}"
        reg_id = _reg_id()
        manifest = docproc["process"](str(html_file), reg_id, 1, "RBI",
                                      storage_root=storage)
        content_file = storage / "processed" / str(reg_id) / "v1.txt"
        texts.append(content_file.read_text(encoding="utf-8"))
        assert validate_manifest(manifest) == []

    assert texts[0] == texts[1], "pipeline output not deterministic for same input"


def test_process_pipeline_version_two_differs(docproc, tmp_path):
    old_file = tmp_path / "old.html"
    new_file = tmp_path / "new.html"
    old_file.write_text(SAMPLE_OLD_GAZETTE, encoding="utf-8")
    new_file.write_text(SAMPLE_NEW_GAZETTE, encoding="utf-8")
    storage = tmp_path / "storage"
    reg_id = _reg_id()

    docproc["process"](str(old_file), reg_id, 1, "RBI", storage_root=storage)
    manifest_v2 = docproc["process"](str(new_file), reg_id, 2, "RBI",
                                     storage_root=storage)

    assert validate_manifest(manifest_v2) == []
    assert manifest_v2["version_no"] == 2
    v1 = (storage / "processed" / str(reg_id) / "v1.txt").read_text(encoding="utf-8")
    v2 = (storage / "processed" / str(reg_id) / "v2.txt").read_text(encoding="utf-8")
    assert v1 != v2
    import hashlib
    assert manifest_v2["content_sha256"] == hashlib.sha256(v2.encode()).hexdigest()
