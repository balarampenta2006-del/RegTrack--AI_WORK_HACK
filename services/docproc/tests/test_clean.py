"""Unit tests for docproc.clean."""

from __future__ import annotations

from docproc.clean import clean_text


def test_nfkc_and_smart_character_unification() -> None:
    raw = "The \ufb01le \u2460 shows \u201cquotes\u201d and \u2018marks\u2019 \u2014 dash\u2026 end"
    cleaned = clean_text(raw)
    assert cleaned == 'The file 1 shows "quotes" and \'marks\' - dash... end'


def test_dehyphenates_line_breaks() -> None:
    assert clean_text("inter-\nnational rules") == "international rules"
    assert clean_text("state-\nwise\npolicy") == "statewise\npolicy"


def test_strips_page_numbers_and_repeated_headers() -> None:
    pages = [
        "RBI HEADER\nBody text one.\nPage 1 of 3",
        "RBI HEADER\nBody text two.\nPage 2 of 3",
        "RBI HEADER\nBody text three.\nPage 3 of 3",
    ]
    cleaned = clean_text("\f".join(pages))
    assert "RBI HEADER" not in cleaned
    assert "Page" not in cleaned
    assert "Body text one." in cleaned
    assert "Body text two." in cleaned
    assert "Body text three." in cleaned


def test_single_page_keeps_content() -> None:
    cleaned = clean_text("Only one page of content.")
    assert cleaned == "Only one page of content."


def test_collapses_whitespace_and_preserves_paragraphs() -> None:
    raw = "Para one.   with   spaces\n\n\n\nPara two.\n\n"
    assert clean_text(raw) == "Para one. with spaces\n\nPara two."


def test_normalises_carriage_returns() -> None:
    assert clean_text("line one\r\nline two\rline three") == "line one\nline two\nline three"


def test_empty_input() -> None:
    assert clean_text("") == ""
