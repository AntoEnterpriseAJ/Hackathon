"""Response models — JSON-serializable dataclasses for API responses."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json


@dataclass
class InlineDiff:
    """Word-level diff within a line."""
    text: str
    type: str  # "equal" | "remove" | "add"


@dataclass
class LineDiff:
    """Single line in a diff."""
    type: str  # "equal" | "remove" | "add" | "replace"
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    old_line_no: Optional[int] = None
    new_line_no: Optional[int] = None
    inline_diff: List[InlineDiff] = field(default_factory=list)


@dataclass
class SectionDiff:
    """Diff for a single section."""
    name: str
    status: str  # "equal" | "modified" | "added" | "removed"
    lines: List[LineDiff] = field(default_factory=list)


@dataclass
class LogicChange:
    """Represents a semantic change detected in the diff."""
    type: str  # e.g., "HOURS_CHANGED", "ECTS_CHANGED"
    section: str
    description: str
    severity: str  # "LOW" | "MEDIUM" | "HIGH"
    old_value: Optional[str] = None
    new_value: Optional[str] = None


@dataclass
class DiffSummary:
    """Statistics about the diff."""
    total_sections: int
    modified: int
    added: int
    removed: int
    unchanged: int
    logic_changes_count: int


@dataclass
class DiffResponse:
    """Complete API response for a diff operation."""
    sections: List[SectionDiff] = field(default_factory=list)
    logic_changes: List[LogicChange] = field(default_factory=list)
    summary: Optional[DiffSummary] = None
    
    def to_dict(self):
        """Convert to dict for JSON serialization."""
        return asdict(self)
    
    def to_json(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
