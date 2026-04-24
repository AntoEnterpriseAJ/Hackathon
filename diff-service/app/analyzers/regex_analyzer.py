"""Regex-based logic analyzer for detecting semantic changes."""

from __future__ import annotations
from typing import List, Dict
import re
from ..models.response import SectionDiff, LogicChange


class RegexAnalyzer:
    """
    Detects logical/semantic changes using regex patterns.
    
    Detects:
    - Hours changed (ore, hours)
    - ECTS credits changed
    - Evaluation methods changed
    - Bibliography changes
    """
    
    def analyze(
        self,
        old_sections: Dict[str, List[str]],
        new_sections: Dict[str, List[str]],
        section_diffs: List[SectionDiff]
    ) -> List[LogicChange]:
        """
        Analyze diffs for logical changes.
        
        Args:
            old_sections: Original sections
            new_sections: New sections
            section_diffs: Computed diffs
            
        Returns:
            List of LogicChange objects
        """
        logic_changes = []
        
        for section_diff in section_diffs:
            if section_diff.status in ["equal", "removed"]:
                continue
            
            old_text = " ".join(old_sections.get(section_diff.name, []))
            new_text = " ".join(new_sections.get(section_diff.name, []))
            
            # Detect hours changes
            hours_changes = self._detect_hours_changes(old_text, new_text, section_diff.name)
            logic_changes.extend(hours_changes)
            
            # Detect ECTS changes
            ects_changes = self._detect_ects_changes(old_text, new_text, section_diff.name)
            logic_changes.extend(ects_changes)
            
            # Detect evaluation changes
            eval_changes = self._detect_evaluation_changes(old_text, new_text, section_diff.name)
            logic_changes.extend(eval_changes)
        
        return logic_changes
    
    def _detect_hours_changes(self, old_text: str, new_text: str, section: str) -> List[LogicChange]:
        """Detect changes in lecture/lab hours."""
        changes = []
        
        # Regex patterns for hours
        patterns = [
            (r'(\d+)\s*ore\s+curs', 'Lecture hours'),
            (r'(\d+)\s*ore\s+laborat', 'Lab hours'),
            (r'(\d+)\s*ore\s+seminar', 'Seminar hours'),
            (r'(\d+)\s*ore\s+proiect', 'Project hours'),
            (r'(\d+)\s*h?\s+curs', 'Lecture hours (h)'),
            (r'(\d+)\s*h?\s+laborat', 'Lab hours (h)'),
        ]
        
        for pattern, label in patterns:
            old_match = re.search(pattern, old_text, re.IGNORECASE)
            new_match = re.search(pattern, new_text, re.IGNORECASE)
            
            if old_match and new_match:
                old_val = old_match.group(1)
                new_val = new_match.group(1)
                
                if old_val != new_val:
                    changes.append(LogicChange(
                        type="HOURS_CHANGED",
                        section=section,
                        description=f"{label} changed from {old_val} to {new_val}",
                        severity="HIGH",
                        old_value=old_val,
                        new_value=new_val
                    ))
        
        return changes
    
    def _detect_ects_changes(self, old_text: str, new_text: str, section: str) -> List[LogicChange]:
        """Detect changes in ECTS credits."""
        changes = []
        
        pattern = r'(\d+(?:[.,]\d+)?)\s*(?:ECTS|credite)'
        
        old_match = re.search(pattern, old_text, re.IGNORECASE)
        new_match = re.search(pattern, new_text, re.IGNORECASE)
        
        if old_match and new_match:
            old_val = old_match.group(1)
            new_val = new_match.group(1)
            
            if old_val != new_val:
                changes.append(LogicChange(
                    type="ECTS_CHANGED",
                    section=section,
                    description=f"ECTS credits changed from {old_val} to {new_val}",
                    severity="HIGH",
                    old_value=old_val,
                    new_value=new_val
                ))
        
        return changes
    
    def _detect_evaluation_changes(self, old_text: str, new_text: str, section: str) -> List[LogicChange]:
        """Detect changes in evaluation methods."""
        changes = []
        
        # Extract evaluation percentages if they exist
        eval_patterns = [
            (r'(?:examen|exam).*?(\d+)\s*%', 'Exam'),
            (r'(?:curs|lecture).*?(\d+)\s*%', 'Lecture'),
            (r'(?:laborat|lab).*?(\d+)\s*%', 'Lab'),
            (r'(?:proiect|project).*?(\d+)\s*%', 'Project'),
        ]
        
        for pattern, label in eval_patterns:
            old_match = re.search(pattern, old_text, re.IGNORECASE)
            new_match = re.search(pattern, new_text, re.IGNORECASE)
            
            if old_match and new_match:
                old_val = old_match.group(1)
                new_val = new_match.group(1)
                
                if old_val != new_val:
                    changes.append(LogicChange(
                        type="EVALUATION_CHANGED",
                        section=section,
                        description=f"{label} evaluation changed from {old_val}% to {new_val}%",
                        severity="MEDIUM",
                        old_value=f"{old_val}%",
                        new_value=f"{new_val}%"
                    ))
        
        return changes
