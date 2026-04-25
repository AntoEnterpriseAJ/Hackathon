"""
Cross-document validation results for FD (Fișa Disciplinei) ↔ Plan de Învățământ.

A FD must align with the Plan on three axes:
  - course identity (denumirea disciplinei matches a course in the plan)
  - administrative fields (credits, evaluation form must match what the plan declares)
  - competency references (every CP/CT code in the FD must exist in the plan)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.template_validation import GuardViolation


CrossValidationStatus = Literal["valid", "invalid", "no_match"]


class PlanCourseMatch(BaseModel):
    """The row in the plan that we matched the FD course to."""
    course_name: str
    course_code: str | None = None
    year: int | None = None
    semester: int | None = None
    credits: float | None = None
    evaluation_form: str | None = None  # "E" (examen) | "C" (colocviu) | None
    categoria_formativa: str | None = None  # DF/DD/DS/DC
    total_hours: int | None = None  # semestral instructional hours (ai+at+tc+aa) when present
    weekly_hours: int | None = None  # per-week instructional hours (C+S+L+P+Pr) when present
    match_confidence: Literal["exact", "fuzzy", "none"] = "exact"


class FdCoverageEntry(BaseModel):
    """Result of validating one FD against a shared Plan (batch mode)."""
    fd_course_name: str | None = None
    result: "CrossValidationResult"


class CoverageReport(BaseModel):
    """Plan-wide coverage: every plan row → status of its FD (if any)."""
    total_plan_courses: int
    fds_uploaded: int
    aligned: int
    inconsistent: int
    unmatched_fds: int  # FDs we couldn't tie to any plan row
    missing_fds: list[str]  # plan course names with no FD uploaded
    entries: list[FdCoverageEntry]


class CrossValidationResult(BaseModel):
    status: CrossValidationStatus
    fd_course_name: str | None = None
    plan_match: PlanCourseMatch | None = None
    field_violations: list[GuardViolation] = Field(default_factory=list)
    competency_violations: list[GuardViolation] = Field(default_factory=list)
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


# Resolve forward reference for FdCoverageEntry
FdCoverageEntry.model_rebuild()
