"""Protocol (interface) for PDF text extraction.

To add a new extractor (e.g. PyMuPDF):
1. Create a new file in app/extractors/
2. Implement this Protocol
3. Register it in config.EXTRACTOR_REGISTRY
"""

from __future__ import annotations
from typing import BinaryIO, Protocol, runtime_checkable
from dataclasses import dataclass, field


@dataclass
class PageText:
    """Extracted text from a single PDF page."""

    page_number: int
    lines: list[str]
    # Average font size per line — helps section parsers detect headings.
    # Empty list is fine if the extractor can't provide font info.
    font_sizes: list[float] = field(default_factory=list)


@runtime_checkable
class TextExtractor(Protocol):
    """Extracts raw text from a PDF file."""

    def extract(self, file_input: bytes | bytearray | memoryview | BinaryIO) -> list[PageText]:
        """Return ordered pages of text from a PDF.

        Args:
            file_input: PDF content as raw bytes or a binary file-like object.

        Returns:
            List of PageText, one per page, in page order.
        """
        ...
