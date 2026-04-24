"""PDF extractor using pdfplumber."""

from __future__ import annotations
from typing import List
import pdfplumber
from ..core.extractor import PageText


class PdfPlumberExtractor:
    """Extracts text from PDFs using pdfplumber."""
    
    def extract(self, file_bytes: bytes) -> List[PageText]:
        """
        Extract pages from PDF bytes.
        
        Args:
            file_bytes: Raw PDF file bytes
            
        Returns:
            List of PageText objects
        """
        pages = []
        
        try:
            with pdfplumber.open(file_bytes) as pdf:
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
        except Exception as e:
            raise ValueError(f"Error extracting PDF: {e}")
        
        return pages
