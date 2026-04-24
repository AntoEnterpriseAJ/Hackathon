"""
Inspect a PDF's text density to choose the extraction route:
  - "text_pdf"    → real PDF with extractable text (avg chars/page > threshold)
  - "scanned_pdf" → image-only pages, needs vision OCR (avg chars/page ≤ threshold)
"""
import pymupdf

_TEXT_CHAR_THRESHOLD = 100  # chars/page below this → treat as scanned


def detect_route(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = sum(len(page.get_text()) for page in doc)
    avg = total / max(doc.page_count, 1)
    doc.close()
    return "text_pdf" if avg > _TEXT_CHAR_THRESHOLD else "scanned_pdf"
