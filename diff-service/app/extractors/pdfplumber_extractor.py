"""PDF extractor using pdfplumber."""

from __future__ import annotations
from typing import BinaryIO, List
from io import BytesIO
import pdfplumber
import fitz
from ..core.extractor import PageText


class PdfPlumberExtractor:
    """Extracts text from PDFs using pdfplumber."""

    def _as_buffer(self, file_input: bytes | bytearray | memoryview | BinaryIO) -> BytesIO:
        """Normalize bytes or streams into a seekable in-memory buffer."""
        if isinstance(file_input, (bytes, bytearray, memoryview)):
            return BytesIO(bytes(file_input))

        if hasattr(file_input, "read"):
            try:
                if hasattr(file_input, "seek"):
                    file_input.seek(0)
            except Exception:
                # Some streams may not support seek; read from current position.
                pass

            raw = file_input.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="ignore")

            if not isinstance(raw, (bytes, bytearray, memoryview)):
                raise ValueError("Unsupported PDF stream payload")

            return BytesIO(bytes(raw))

        raise TypeError("Extractor expects bytes or a binary file-like object")
    
    def _extract_with_pdfplumber(self, file_bytes: bytes) -> List[PageText]:
        """Primary extractor: pdfplumber (good for structured text)."""
        pages: List[PageText] = []

        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                lines = [line for line in text.split("\n") if line.strip()]
                if lines:
                    pages.append(
                        PageText(
                            page_number=page_num,
                            lines=lines,
                            font_sizes=[]
                        )
                    )

        return pages

    def _extract_with_pymupdf(self, file_bytes: bytes) -> List[PageText]:
        """Fallback extractor: PyMuPDF (handles some PDFs pdfplumber can't)."""
        pages: List[PageText] = []
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                lines = [line for line in text.split("\n") if line.strip()]
                if lines:
                    pages.append(
                        PageText(
                            page_number=page_num,
                            lines=lines,
                            font_sizes=[]
                        )
                    )
        finally:
            doc.close()

        return pages

    def extract(self, file_input: bytes | bytearray | memoryview | BinaryIO) -> List[PageText]:
        """
        Extract pages from PDF bytes or a stream.
        
        Args:
            file_input: Raw PDF bytes or a file-like object
            
        Returns:
            List of PageText objects
        """
        pages: List[PageText] = []

        try:
            buffer = self._as_buffer(file_input)
            file_bytes = buffer.getvalue()

            # Try pdfplumber first.
            try:
                pages = self._extract_with_pdfplumber(file_bytes)
            except Exception:
                pages = []

            # Fallback for PDFs that pdfplumber cannot parse cleanly.
            if not pages:
                pages = self._extract_with_pymupdf(file_bytes)

            if not pages:
                raise ValueError(
                    "No extractable text found in PDF. "
                    "This file may be scanned/image-only and requires OCR."
                )
        except Exception as e:
            raise ValueError(f"Error extracting PDF: {e}")
        
        return pages
