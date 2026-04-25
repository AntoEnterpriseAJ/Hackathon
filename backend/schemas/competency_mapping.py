"""Schemas for the competency mapping use case (UC 2.2 — The Competency
Mapper).

Given a Fișa Disciplinei and the Plan de Învățământ for the same program,
we produce a side-by-side view of the competence catalogue (CP/CT codes):

* which codes are *declared* in the FD (and what they mean in the plan);
* which codes are *unknown* (referenced in the FD but missing from the
  plan's catalogue — likely a typo or stale reference);
* which codes the plan defines but the FD does not reference;
* optional AI recommendations: codes from the catalogue that match the
  course topic and could be added to the FD.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CompetencyEntry(BaseModel):
    """One competence code with its plan-side description."""

    code: str
    title: str | None = None


class RecommendedCompetency(BaseModel):
    """An AI-suggested competence the FD could include."""

    code: str
    title: str | None = None
    rationale: str
    confidence: Literal["high", "medium", "low"] = "medium"


class CompetencyMapping(BaseModel):
    fd_course_name: str | None = None
    plan_program: str | None = None

    # All CP/CT codes the plan defines (the "official catalogue").
    catalog: list[CompetencyEntry] = Field(default_factory=list)

    # FD codes that exist in the plan catalogue.
    declared: list[CompetencyEntry] = Field(default_factory=list)
    # FD codes that do NOT exist in the plan catalogue.
    unknown: list[CompetencyEntry] = Field(default_factory=list)
    # Plan codes the FD does not reference.
    plan_only: list[CompetencyEntry] = Field(default_factory=list)
    # AI suggestions (optional; empty if Claude is unavailable / disabled).
    recommended: list[RecommendedCompetency] = Field(default_factory=list)

    summary: str = ""
