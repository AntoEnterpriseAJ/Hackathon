"""Parser for "Fișe de Disciplină" (Course Description Sheets)."""

from __future__ import annotations
from typing import List, Dict
import re
from ..core.extractor import PageText


class FDSectionParser:
    """
    Parses Fișe de Disciplină (FD) documents.
    
    Typical sections:
    - Identificare
    - Obiective
    - Competențe specifice
    - Conținuturi
    - Structura disciplinei
    - Evaluare
    - Bibliografie
    """
    
    # Regex patterns for common FD section headers
    SECTION_PATTERNS = [
        r"^(?:1\.|I\.|Identificare|Cod disciplin)",
        r"^(?:2\.|II\.|Obiective)",
        r"^(?:3\.|III\.|Competențe|Competente)",
        r"^(?:4\.|IV\.|Conținuturi|Continut)",
        r"^(?:5\.|V\.|Structura disciplinei|Ore)",
        r"^(?:6\.|VI\.|Evaluare)",
        r"^(?:7\.|VII\.|Bibliografie|Referințe)",
    ]
    
    def parse(self, pages: List[PageText]) -> Dict[str, List[str]]:
        """
        Parse pages into sections.
        
        Args:
            pages: List of PageText objects
            
        Returns:
            Dict mapping section names to lines
        """
        # Flatten all lines
        all_lines = []
        for page in pages:
            all_lines.extend(page.lines)
        
        sections = {}
        current_section = "Header"
        current_content = []
        
        for line in all_lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts a new section
            is_new_section = False
            for pattern in self.SECTION_PATTERNS:
                if re.match(pattern, line, re.IGNORECASE):
                    # Save previous section
                    if current_section and current_content:
                        sections[current_section] = current_content
                    
                    # Start new section
                    current_section = self._extract_section_name(line)
                    current_content = [line]
                    is_new_section = True
                    break
            
            if not is_new_section:
                current_content.append(line)
        
        # Save final section
        if current_section and current_content:
            sections[current_section] = current_content
        
        return sections
    
    def _extract_section_name(self, header_line: str) -> str:
        """Extract clean section name from header line."""
        # Remove numbering
        cleaned = re.sub(r"^(?:\d+\.|[IVX]+\.|[-\.])\s*", "", header_line.strip())
        return cleaned or "Unknown"
