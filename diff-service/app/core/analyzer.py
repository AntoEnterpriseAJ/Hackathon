"""Protocol (interface) for logic / semantic analysis."""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from ..models.response import SectionDiff, LogicChange


@runtime_checkable
class LogicAnalyzer(Protocol):
    """Detects logical / semantic changes from diff results."""

    def analyze(
        self,
        old_sections: dict[str, list[str]],
        new_sections: dict[str, list[str]],
        section_diffs: list[SectionDiff],
    ) -> list[LogicChange]:
        """Analyze diffs for logical significance.

        Args:
            old_sections: Original document sections.
            new_sections: New document sections.
            section_diffs: The computed diffs between versions.

        Returns:
            List of LogicChange with type, description, severity.
        """
        ...
