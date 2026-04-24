"""Differ using difflib for line and word-level diffs."""

from __future__ import annotations
from typing import List, Dict
from difflib import SequenceMatcher
from ..models.response import SectionDiff, LineDiff, InlineDiff


class DifflibDiffer:
    """
    Computes diffs using difflib with line-level and word-level precision.
    """
    
    def diff(
        self,
        old_sections: Dict[str, List[str]],
        new_sections: Dict[str, List[str]]
    ) -> List[SectionDiff]:
        """
        Compute diffs for all sections.
        
        Args:
            old_sections: Dict of section_name -> list of lines
            new_sections: Dict of section_name -> list of lines
            
        Returns:
            List of SectionDiff objects
        """
        all_sections = set(old_sections.keys()) | set(new_sections.keys())
        diffs = []
        
        for section_name in sorted(all_sections):
            old_lines = old_sections.get(section_name, [])
            new_lines = new_sections.get(section_name, [])
            
            section_diff = self._diff_section(section_name, old_lines, new_lines)
            diffs.append(section_diff)
        
        return diffs
    
    def _diff_section(
        self,
        section_name: str,
        old_lines: List[str],
        new_lines: List[str]
    ) -> SectionDiff:
        """Compute diff for a single section."""
        
        # Determine status
        if not old_lines and not new_lines:
            status = "equal"
        elif not old_lines:
            status = "added"
        elif not new_lines:
            status = "removed"
        else:
            # Use SequenceMatcher to detect if section changed
            matcher = SequenceMatcher(None, old_lines, new_lines)
            ratio = matcher.ratio()
            status = "equal" if ratio > 0.95 else "modified"
        
        # Compute line diffs
        line_diffs = self._diff_lines(old_lines, new_lines)
        
        return SectionDiff(
            name=section_name,
            status=status,
            lines=line_diffs
        )
    
    def _diff_lines(self, old_lines: List[str], new_lines: List[str]) -> List[LineDiff]:
        """Compute line-level diffs with word-level inline diffs."""
        line_diffs = []
        
        matcher = SequenceMatcher(None, old_lines, new_lines)
        old_idx = 0
        new_idx = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Lines are identical
                for i in range(i2 - i1):
                    line_diffs.append(LineDiff(
                        type="equal",
                        old_text=old_lines[i1 + i],
                        new_text=old_lines[i1 + i],
                        old_line_no=i1 + i + 1,
                        new_line_no=j1 + i + 1
                    ))
                old_idx = i2
                new_idx = j2
            
            elif tag == 'replace':
                # Lines changed
                # Try to match old and new lines 1-to-1
                old_chunk = old_lines[i1:i2]
                new_chunk = new_lines[j1:j2]
                
                # For each pair, create a replace diff with inline diffs
                max_len = max(len(old_chunk), len(new_chunk))
                for k in range(max_len):
                    old_line = old_chunk[k] if k < len(old_chunk) else ""
                    new_line = new_chunk[k] if k < len(new_chunk) else ""
                    
                    inline_diffs = self._diff_words(old_line, new_line) if old_line and new_line else []
                    
                    line_diffs.append(LineDiff(
                        type="replace",
                        old_text=old_line,
                        new_text=new_line,
                        old_line_no=(i1 + k + 1) if k < len(old_chunk) else None,
                        new_line_no=(j1 + k + 1) if k < len(new_chunk) else None,
                        inline_diff=inline_diffs
                    ))
                
                old_idx = i2
                new_idx = j2
            
            elif tag == 'insert':
                # New lines added
                for j in range(j1, j2):
                    line_diffs.append(LineDiff(
                        type="add",
                        old_text=None,
                        new_text=new_lines[j],
                        old_line_no=None,
                        new_line_no=j + 1
                    ))
                new_idx = j2
            
            elif tag == 'delete':
                # Lines removed
                for i in range(i1, i2):
                    line_diffs.append(LineDiff(
                        type="remove",
                        old_text=old_lines[i],
                        new_text=None,
                        old_line_no=i + 1,
                        new_line_no=None
                    ))
                old_idx = i2
        
        return line_diffs
    
    def _diff_words(self, old_text: str, new_text: str) -> List[InlineDiff]:
        """Compute word-level inline diffs."""
        if not old_text and not new_text:
            return []
        
        if not old_text or not new_text:
            # One is empty
            text = old_text or new_text
            return [InlineDiff(text=text, type="remove" if old_text else "add")]
        
        # Split into words (keeping spaces)
        import re
        old_words = re.findall(r'\S+|\s+', old_text)
        new_words = re.findall(r'\S+|\s+', new_text)
        
        inline_diffs = []
        matcher = SequenceMatcher(None, old_words, new_words)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for i in range(i2 - i1):
                    inline_diffs.append(InlineDiff(
                        text=old_words[i1 + i],
                        type="equal"
                    ))
            elif tag == 'replace':
                # Mark old words as remove, new as add
                for i in range(i1, i2):
                    inline_diffs.append(InlineDiff(
                        text=old_words[i],
                        type="remove"
                    ))
                for j in range(j1, j2):
                    inline_diffs.append(InlineDiff(
                        text=new_words[j],
                        type="add"
                    ))
            elif tag == 'insert':
                for j in range(j1, j2):
                    inline_diffs.append(InlineDiff(
                        text=new_words[j],
                        type="add"
                    ))
            elif tag == 'delete':
                for i in range(i1, i2):
                    inline_diffs.append(InlineDiff(
                        text=old_words[i],
                        type="remove"
                    ))
        
        return inline_diffs
