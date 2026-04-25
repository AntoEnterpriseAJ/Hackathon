"""Pydantic models for the Template Shifter response report."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Confidence = Literal[
    "exact",
    "fuzzy",
    "llm-high",
    "llm-medium",
    "llm-low",
    "placeholder",
]


class SectionMatchReport(BaseModel):
    new_heading: str
    old_heading: str | None = None
    confidence: Confidence
    rationale: str | None = None


class AdminUpdateReport(BaseModel):
    field: str
    value: str


class ShiftReport(BaseModel):
    matches: list[SectionMatchReport] = []
    admin_updates: list[AdminUpdateReport] = []
    placeholders: list[str] = []
    llm_used: bool = False
