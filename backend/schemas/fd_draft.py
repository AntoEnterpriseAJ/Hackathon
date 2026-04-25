"""Schemas for UC 3.4 FD Drafter (generates a draft Fișa Disciplinei from a Plan entry)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanCourseSummary(BaseModel):
    """Lightweight view of one course row in the Plan, used to populate the picker."""
    course_name: str
    course_code: str | None = None
    year: int | None = None
    semester: int | None = None
    credits: float | None = None
    evaluation_form: str | None = None
    categoria_formativa: str | None = None
    total_hours: float | None = None
    weekly_hours: str | None = None


class PlanCourseListResponse(BaseModel):
    program: str | None = None
    courses: list[PlanCourseSummary] = Field(default_factory=list)


class FdDraftRequest(BaseModel):
    plan: dict
    course_name: str
    course_code: str | None = None
    use_claude: bool | None = None


class FdDraftSection(BaseModel):
    title: str
    body: str


class SelectedCompetency(BaseModel):
    code: str
    title: str
    ri_bullets: list[str] = Field(default_factory=list)
    rationale: str | None = None


class FdDraft(BaseModel):
    course_name: str
    course_code: str | None = None
    year: int | None = None
    semester: int | None = None
    credits: float | None = None
    evaluation_form: str | None = None
    categoria_formativa: str | None = None
    total_hours: float | None = None
    weekly_hours: str | None = None
    competencies: list[str] = Field(default_factory=list)
    selected_cp: list[SelectedCompetency] = Field(default_factory=list)
    selected_ct: list[SelectedCompetency] = Field(default_factory=list)
    picker_fallback_reason: str | None = None
    sections: list[FdDraftSection] = Field(default_factory=list)
    markdown: str
    ai_generated: bool = False
    summary: str
