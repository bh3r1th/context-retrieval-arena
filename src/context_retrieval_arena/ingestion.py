"""Text extraction only: no OCR, layout inference, or silent page removal."""

import hashlib
from pathlib import Path
from time import perf_counter

import pypdf

from .models import Document, Page


def ingest_pdf(path: Path) -> Document:
    started = perf_counter()
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        source.seek(0)
        reader = pypdf.PdfReader(source)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported; provide a decrypted PDF")
        pages = [Page(i, page.extract_text() or "") for i, page in enumerate(reader.pages, 1)]
    if not pages:
        raise ValueError("PDF contains no pages")
    if not any(page.text.strip() for page in pages):
        raise ValueError("PDF has no extractable text; OCR is not implemented")
    return Document(1, path.name, digest, pypdf.__version__, perf_counter() - started, pages)
