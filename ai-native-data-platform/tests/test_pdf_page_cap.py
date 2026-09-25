"""Regression test: PDF ingestion must reject an oversized page count
before doing any rasterization work.

app.ingestion.multimodal.pdf_to_images previously had no page limit at
all: a small PDF file declaring an enormous page count ("page bomb") would
be rasterized page-by-page with no ceiling, turning one upload into
unbounded CPU work plus, downstream, one vision-API call and one pgvector
row per page. This mocks pdf2image (poppler is a system dependency this
mocked unit suite deliberately doesn't require) to check the app-level
cap-enforcement logic in isolation.
"""
from __future__ import annotations

import pytest

import app.ingestion.multimodal as multimodal


def test_pdf_over_the_page_cap_is_rejected_before_rasterizing(monkeypatch):
    monkeypatch.setattr(multimodal.settings, "max_pdf_pages", 5)

    def fake_pdfinfo_from_bytes(pdf_bytes):
        return {"Pages": 20}

    def fake_convert_from_bytes(*args, **kwargs):
        raise AssertionError("convert_from_bytes must not run once the page cap check fails")

    import pdf2image

    monkeypatch.setattr(pdf2image, "pdfinfo_from_bytes", fake_pdfinfo_from_bytes)
    monkeypatch.setattr(pdf2image, "convert_from_bytes", fake_convert_from_bytes)

    with pytest.raises(multimodal.PdfTooManyPagesError) as exc_info:
        multimodal.pdf_to_images(b"fake-pdf-bytes")

    assert exc_info.value.page_count == 20
    assert exc_info.value.limit == 5


def test_pdf_within_the_page_cap_is_converted_normally(monkeypatch):
    monkeypatch.setattr(multimodal.settings, "max_pdf_pages", 5)

    def fake_pdfinfo_from_bytes(pdf_bytes):
        return {"Pages": 3}

    calls = []

    class _FakePage:
        def save(self, buf, format):
            buf.write(b"fake-png-bytes")

    def fake_convert_from_bytes(pdf_bytes, dpi, fmt, last_page):
        calls.append({"last_page": last_page})
        return [_FakePage(), _FakePage(), _FakePage()]

    import pdf2image

    monkeypatch.setattr(pdf2image, "pdfinfo_from_bytes", fake_pdfinfo_from_bytes)
    monkeypatch.setattr(pdf2image, "convert_from_bytes", fake_convert_from_bytes)

    result = multimodal.pdf_to_images(b"fake-pdf-bytes")

    assert len(result) == 3
    assert all(mime == "image/png" for _, mime in result)
    # The cap is also passed to convert_from_bytes itself (defense in depth
    # if pdfinfo and the real conversion ever disagree on page count).
    assert calls == [{"last_page": 5}]
