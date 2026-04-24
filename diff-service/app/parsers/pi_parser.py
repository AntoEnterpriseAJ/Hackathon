"""Parser for "Planuri de Învățământ" (Teaching Plans)."""

from __future__ import annotations
from typing import List, Dict
import re
from ..core.extractor import PageText


class PISectionParser:
    """
    Parses Planuri de Învățământ (PI) documents.
    
    Typical sections:
    - General info
    - Learning Outcomes
    - Curriculum Structure
    - Assessment Strategy
    - Resources
    """
    
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
            
            # Simple heuristic: ALL CAPS lines are likely section headers
            if line.isupper() and len(line) > 5:
                if current_section and current_content:
                    sections[current_section] = current_content
                
                current_section = line.title()
                current_content = [line]
            else:
                current_content.append(line)
        
        # Save final section
        if current_section and current_content:
            sections[current_section] = current_content
        
        return sections
