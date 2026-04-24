"""Protocol (interface) for text diffing."""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from ..models.response import SectionDiff


@runtime_checkable
class TextDiffer(Protocol):
    """Compares old and new document sections."""

    def diff(
        self,
        old_sections: dict[str, list[str]],
        new_sections: dict[str, list[str]],
    ) -> list[SectionDiff]:
        """Produce a diff for each section.

        Args:
            old_sections: Section name -> lines from version 1.
            new_sections: Section name -> lines from version 2.

        Returns:
            List of SectionDiff objects covering all sections.
        """
        ...
