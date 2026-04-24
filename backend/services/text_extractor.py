"""Extract plain text from a text-based PDF, capped at MAX_PAGES pages."""
import pymupdf

_MAX_PAGES = 20


def extract_text(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    parts: list[str] = []
    for i in range(min(doc.page_count, _MAX_PAGES)):
        parts.append(f"\n\n--- Page {i + 1} ---\n\n")
        parts.append(doc[i].get_text())
    doc.close()
    return "".join(parts).strip()
