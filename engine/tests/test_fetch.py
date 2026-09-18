"""Tests for `worker/fetch.py`'s PDF text-extraction path — PDFs used to be
rejected before `fetch()` ever saw them (`search_stage._is_pdf_url`); now
`fetch()` detects a PDF response, extracts its text with `pypdf`, and routes
it through `pagestate.assess()` like any other fetched document. Same
fixture/monkeypatch style as `test_worker.py`'s "fetch.py" section (`conn`
fixture over `embed.index.connect`, `requests` swapped for a fake object with
a `get` staticmethod).
"""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

vec = pytest.importorskip("sqlite_vec")

from embed import index
from worker import fetch as fetchmod


@pytest.fixture
def conn(tmp_path):
    c = index.connect(tmp_path / "g.db")
    yield c
    c.close()


def _make_pdf(text: str) -> bytes:
    """A minimal, hand-built single-page PDF with one text-showing content
    stream — no reportlab in the environment, and a `PdfWriter`-only blank
    page has no extractable text at all, so this hand-assembles the objects
    (catalog, pages, page, font, content stream) plus a valid xref/trailer.
    Verified against `pypdf.PdfReader` to round-trip the exact string."""
    content = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_offset = out.tell()
    n = len(objects) + 1
    out.write(f"xref\n0 {n}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n")
    out.write(f"<< /Size {n} /Root 1 0 R >>\n".encode())
    out.write(b"startxref\n")
    out.write(f"{xref_offset}\n".encode())
    out.write(b"%%EOF")
    return out.getvalue()


def _make_multipage_pdf(page_texts: list[str]) -> bytes:
    """Same hand-assembly as `_make_pdf`, generalised to N pages — one
    content stream per page, each showing its own text, so a cap test can
    tell whether extraction ran past the boundary rather than just checking
    a page count. Page objects are objects 3..(2+N); the shared font is
    object (3+N); content streams are objects (4+N)..(3+2N)."""
    n = len(page_texts)
    font_obj = 3 + n
    content_objs = list(range(4 + n, 4 + 2 * n))
    contents = [f"BT /F1 12 Tf 72 700 Td ({t}) Tj ET".encode("latin-1")
                for t in page_texts]

    objects = []
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objects.append(f"<< /Type /Catalog /Pages 2 0 R >>".encode())
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i in range(n):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << "
            f"/F1 {font_obj} 0 R >> >> /MediaBox [0 0 612 792] "
            f"/Contents {content_objs[i]} 0 R >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for c in contents:
        objects.append(b"<< /Length %d >>\nstream\n" % len(c) + c + b"\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_offset = out.tell()
    total = len(objects) + 1
    out.write(f"xref\n0 {total}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n")
    out.write(f"<< /Size {total} /Root 1 0 R >>\n".encode())
    out.write(b"startxref\n")
    out.write(f"{xref_offset}\n".encode())
    out.write(b"%%EOF")
    return out.getvalue()


# Long enough to clear pagestate.MIN_DOCUMENT_WORDS (120) so the result comes
# back "ok", not "thin" — same rationale as test_search_stage.py's _PAGE_BODY.
_PDF_BODY = ("extracted pdf content word " * 20).strip()


class _FakeResp:
    def __init__(self, content: bytes, *, content_type: str = "application/pdf",
                status_code: int = 200):
        self.content = content
        self.headers = {"Content-Type": content_type} if content_type else {}
        self.status_code = status_code

    @property
    def text(self):  # pragma: no cover - guards against the mangling bug
        raise AssertionError(
            "fetch() must read PDF bytes via .content, not decode via .text")


def _fake_requests(resp):
    class FakeRequests:
        RequestException = Exception
        @staticmethod
        def get(*a, **kw):
            return resp
    return FakeRequests


def test_pdf_response_is_extracted_and_usable(conn, monkeypatch, tmp_path):
    pdf_bytes = _make_pdf(_PDF_BODY)
    monkeypatch.setattr(fetchmod, "requests",
                        _fake_requests(_FakeResp(pdf_bytes)))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/report.pdf")
    assert result.text and "extracted pdf content" in result.text
    assert result.state.usable is True
    assert result.cache_hit is False


def test_pdf_url_suffix_is_detected_without_a_content_type_header(
        conn, monkeypatch, tmp_path):
    """A server that mislabels or omits Content-Type is still recognised as
    a PDF via the `.pdf` url suffix fallback."""
    pdf_bytes = _make_pdf(_PDF_BODY)
    monkeypatch.setattr(
        fetchmod, "requests",
        _fake_requests(_FakeResp(pdf_bytes, content_type="")))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/mislabeled.pdf")
    assert result.text and "extracted pdf content" in result.text
    assert result.state.usable is True


def test_malformed_pdf_does_not_crash_fetch(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(
        fetchmod, "requests",
        _fake_requests(_FakeResp(b"not actually a pdf, just garbage bytes")))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/broken.pdf")
    assert result.text is None
    assert result.state.usable is False
    assert result.error


def test_extracted_pdf_text_is_cached(conn, monkeypatch, tmp_path):
    pdf_bytes = _make_pdf(_PDF_BODY)
    calls = []

    class FakeRequests:
        RequestException = Exception
        @staticmethod
        def get(*a, **kw):
            calls.append(1)
            return _FakeResp(pdf_bytes)
    monkeypatch.setattr(fetchmod, "requests", FakeRequests)

    first = fetchmod.fetch(conn, tmp_path, "https://x.test/cached.pdf")
    assert first.cache_hit is False
    assert len(calls) == 1

    second = fetchmod.fetch(conn, tmp_path, "https://x.test/cached.pdf")
    assert second.cache_hit is True
    assert len(calls) == 1, "a cached pdf fetch must not call requests.get again"
    assert second.text and "extracted pdf content" in second.text


# --------------------------------------------------------- size/page cap --

def test_pdf_over_the_page_cap_is_rejected_without_extracting(
        conn, monkeypatch, tmp_path):
    """A PDF whose page count exceeds `PDF_MAX_PAGES` must be rejected by
    the cheap page-count gate — `_extract_pdf_text` (the expensive full
    extraction) must never run at all."""
    monkeypatch.setattr(fetchmod, "PDF_MAX_PAGES", 3)
    pdf_bytes = _make_multipage_pdf([f"page {i} text content" for i in range(5)])

    def boom(*a, **kw):
        raise AssertionError("full pdf extraction must not run past the page cap")
    monkeypatch.setattr(fetchmod, "_extract_pdf_text", boom)
    monkeypatch.setattr(fetchmod, "requests",
                        _fake_requests(_FakeResp(pdf_bytes)))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/book.pdf")
    assert result.text is None
    assert result.state.usable is False
    assert "pages" in result.error and "5" in result.error


def test_pdf_over_the_byte_cap_is_rejected_without_opening_the_reader(
        conn, monkeypatch, tmp_path):
    """The byte-size gate runs before `PdfReader` even opens the buffer —
    the cheapest possible check, ahead of any pypdf call at all."""
    monkeypatch.setattr(fetchmod, "PDF_MAX_BYTES", 50)
    pdf_bytes = _make_pdf(_PDF_BODY)
    assert len(pdf_bytes) > 50, "fixture must actually exceed the lowered cap"

    def boom(*a, **kw):
        raise AssertionError("PdfReader must not open a pdf over the byte cap")
    monkeypatch.setattr(fetchmod, "PdfReader", boom)
    monkeypatch.setattr(fetchmod, "requests",
                        _fake_requests(_FakeResp(pdf_bytes)))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/huge.pdf")
    assert result.text is None
    assert result.state.usable is False
    assert "bytes" in result.error


def test_pdf_just_under_the_page_cap_extracts_fully_and_normally(
        conn, monkeypatch, tmp_path):
    monkeypatch.setattr(fetchmod, "PDF_MAX_PAGES", 3)
    pdf_bytes = _make_multipage_pdf([
        ("page " + str(i) + " " + ("filler word " * 30)) for i in range(3)
    ])
    monkeypatch.setattr(fetchmod, "requests",
                        _fake_requests(_FakeResp(pdf_bytes)))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/report3.pdf")
    assert result.state.usable is True
    assert result.text
    for i in range(3):
        assert f"page {i}" in result.text
