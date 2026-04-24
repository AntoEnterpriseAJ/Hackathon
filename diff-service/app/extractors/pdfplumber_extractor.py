"""PDF extractor using pdfplumber."""

from __future__ import annotations
from typing import BinaryIO, List
from io import BytesIO
import pdfplumber
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
    
    def extract(self, file_input: bytes | bytearray | memoryview | BinaryIO) -> List[PageText]:
        """
        Extract pages from PDF bytes or a stream.
        
        Args:
            file_input: Raw PDF bytes or a file-like object
            
        Returns:
            List of PageText objects
        """
        pages = []
        
        try:
            with pdfplumber.open(self._as_buffer(file_input)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        lines = text.split('\n')
                        pages.append(
                            PageText(
                                page_number=page_num,
                                lines=lines,
                                font_sizes=[]
                            )
                        )

            if not pages:
                raise ValueError("No extractable text found in PDF (possibly scanned/image-only)")
        except Exception as e:
            raise ValueError(f"Error extracting PDF: {e}")
        
        return pages
