"""Protocol (interface) for document section parsing."""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from .extractor import PageText


@runtime_checkable
class SectionParser(Protocol):
    """Parses extracted pages into named sections."""

    def parse(self, pages: list[PageText]) -> dict[str, list[str]]:
        """Parse pages into a dict of section_name -> list of lines.

        Args:
            pages: Ordered list of PageText from an extractor.

        Returns:
            Dict mapping section names to their content lines.
            Section names should be normalized (stripped, title-cased).
        """
        ...
