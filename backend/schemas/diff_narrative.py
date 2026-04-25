"""Response model for the diff narrative explainer."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DiffNarrative(BaseModel):
    narrative: str
    key_changes: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
