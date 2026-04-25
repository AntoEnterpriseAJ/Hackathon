"""UC 3.4 — FD Drafter.

Generates a draft Fișa Disciplinei (FD) skeleton from a parsed Plan.

Two paths:
  * Deterministic — always runs. Pulls course metadata + competency catalog
    from the Plan and assembles a skeleton with empty narrative sections.
  * Optional Claude — fills in objectives, content outline, bibliography
    suggestions when ANTHROPIC_API_KEY is set.

The drafter is intentionally additive: it never modifies the Plan and it
never invents administrative numbers — those come straight from the Plan
row. AI is used only for the narrative sections.
"""
from __future__ import annotations

import os

from schemas.extraction import ExtractedDocument
from schemas.fd_draft import FdDraft, FdDraftSection, PlanCourseSummary, SelectedCompetency
from services import claude_service
from services.competency_picker import (
    parse_plan_competencies,
    pick_for_course,
)
from services.cross_doc_validator import (
    _extract_admin_fields,
    _extract_categoria,
    _normalize,
    _plan_course_tables,
    _row_to_dict,
    _extract_year_from_table_name,
)


_DRAFT_TOOL = {
    "name": "submit_fd_draft",
    "description": "Returnează secțiunile narative pentru o draft Fișă a Disciplinei.",
    "input_schema": {
        "type": "object",
        "properties": {
            "obiective_generale": {"type": "string"},
            "obiective_specifice": {"type": "string"},
            "continut_curs": {"type": "string"},
            "continut_aplicatii": {"type": "string"},
            "bibliografie": {"type": "string"},
            "metode_evaluare": {"type": "string"},
        },
        "required": [
            "obiective_generale",
            "obiective_specifice",
            "continut_curs",
            "continut_aplicatii",
            "bibliografie",
            "metode_evaluare",
        ],
    },
}


def list_plan_courses(plan: ExtractedDocument) -> list[PlanCourseSummary]:
    """Flatten all courses from the Plan tables for the picker UI."""
    courses: list[PlanCourseSummary] = []
    for table in _plan_course_tables(plan):
        year = _extract_year_from_table_name(table.name)
        for row in table.rows:
            row_dict = _row_to_dict(table.headers, row)
            disc_name = row_dict.get("disciplina") or row_dict.get("denumirea_disciplinei")
            if not disc_name:
                continue
            credits, eval_form, semester, total_hours, weekly_hours = _extract_admin_fields(row_dict)
            courses.append(
                PlanCourseSummary(
                    course_name=disc_name,
                    course_code=row_dict.get("codul_disciplinei") or None,
                    year=year,
                    semester=semester,
                    credits=credits,
                    evaluation_form=eval_form,
                    categoria_formativa=_extract_categoria(row_dict),
                    total_hours=total_hours,
                    weekly_hours=str(weekly_hours) if weekly_hours is not None else None,
                )
            )
    return courses


def draft_fd_from_plan(
    *,
    plan: ExtractedDocument,
    course_name: str,
    course_code: str | None = None,
    use_claude: bool | None = None,
) -> FdDraft:
    """Build an FD skeleton for the named course from the Plan."""
    target = _normalize(course_name)
    matched: PlanCourseSummary | None = None

    for c in list_plan_courses(plan):
        if course_code and c.course_code and c.course_code.strip() == course_code.strip():
            matched = c
            break
        if _normalize(c.course_name) == target:
            matched = c
            break

    if matched is None:
        # Fallback: substring match
        for c in list_plan_courses(plan):
            if target and target in _normalize(c.course_name):
                matched = c
                break

    if matched is None:
        # Last resort skeleton with just the requested name.
        matched = PlanCourseSummary(course_name=course_name, course_code=course_code)

    competencies = _competency_catalog(plan)

    if use_claude is None:
        use_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))

    # UC 1.4 — pick relevant CP/CT for THIS course (closed-set Claude guard).
    plan_comps = parse_plan_competencies(plan)
    pick = pick_for_course(
        course_name=matched.course_name,
        course_meta={
            "year": matched.year,
            "semester": matched.semester,
            "credits": matched.credits,
            "evaluation_form": matched.evaluation_form,
            "categoria_formativa": matched.categoria_formativa,
            "weekly_hours": matched.weekly_hours,
        },
        plan_competencies=plan_comps,
        use_claude=use_claude,
    )
    selected_cp = [
        SelectedCompetency(
            code=e.code, title=e.title, ri_bullets=e.ri_bullets,
            rationale=pick.rationale.get(e.code),
        )
        for e in pick.cp
    ]
    selected_ct = [
        SelectedCompetency(
            code=e.code, title=e.title, ri_bullets=e.ri_bullets,
            rationale=pick.rationale.get(e.code),
        )
        for e in pick.ct
    ]

    sections = _baseline_sections(matched, competencies)
    ai_used = pick.ai_used
    if use_claude:
        try:
            ai_sections = _generate_narrative_with_claude(matched, competencies)
            if ai_sections:
                sections = ai_sections
                ai_used = True
        except Exception:  # noqa: BLE001 — AI is optional, never fails the draft
            pass

    md = _render_markdown(matched, competencies, sections, selected_cp, selected_ct)
    summary_parts = [
        f"Draft FD pentru '{matched.course_name}' generat din Plan."
    ]
    if selected_cp or selected_ct:
        summary_parts.append(
            f"Competențe selectate: {len(selected_cp)} CP + {len(selected_ct)} CT."
        )
    if pick.fallback_reason:
        summary_parts.append(pick.fallback_reason)
    if ai_used:
        summary_parts.append("Sugestii narative AI incluse.")

    return FdDraft(
        course_name=matched.course_name,
        course_code=matched.course_code,
        year=matched.year,
        semester=matched.semester,
        credits=matched.credits,
        evaluation_form=matched.evaluation_form,
        categoria_formativa=matched.categoria_formativa,
        total_hours=matched.total_hours,
        weekly_hours=matched.weekly_hours,
        competencies=competencies,
        selected_cp=selected_cp,
        selected_ct=selected_ct,
        picker_fallback_reason=pick.fallback_reason,
        sections=sections,
        markdown=md,
        ai_generated=ai_used,
        summary=" ".join(summary_parts),
    )


# ---------- helpers ----------

def _competency_catalog(plan: ExtractedDocument) -> list[str]:
    for f in plan.fields:
        if f.key == "competente_catalog" and isinstance(f.value, list):
            return [str(v) for v in f.value]
    return []


def _baseline_sections(
    course: PlanCourseSummary, competencies: list[str]
) -> list[FdDraftSection]:
    return [
        FdDraftSection(
            title="Obiective generale",
            body="(De completat) Obiectivul general al disciplinei.",
        ),
        FdDraftSection(
            title="Obiective specifice",
            body="(De completat) Obiective specifice formulate pe competențele țintă.",
        ),
        FdDraftSection(
            title="Conținut curs",
            body="(De completat) Lista capitolelor de curs.",
        ),
        FdDraftSection(
            title="Conținut aplicații",
            body="(De completat) Lista temelor de seminar/laborator/proiect.",
        ),
        FdDraftSection(
            title="Bibliografie",
            body="(De completat) Surse bibliografice obligatorii și suplimentare.",
        ),
        FdDraftSection(
            title="Metode de evaluare",
            body=(
                f"Forma de evaluare conform Planului: {course.evaluation_form or '(neprecizată)'}."
                "\n(De completat) Ponderi pentru activități, examen, proiect."
            ),
        ),
    ]


def _generate_narrative_with_claude(
    course: PlanCourseSummary, competencies: list[str]
) -> list[FdDraftSection] | None:
    competencies_block = "\n".join(f"- {c}" for c in competencies) or "(catalog gol)"
    user_prompt = (
        "Generează secțiunile narative pentru o draft Fișă a Disciplinei (FD) "
        "în limba română, conform standardului ARACIS/RNCIS.\n\n"
        f"Disciplină: {course.course_name}\n"
        f"Cod: {course.course_code or '-'}\n"
        f"An / Sem: {course.year or '?'} / {course.semester or '?'}\n"
        f"Credite: {course.credits or '?'}\n"
        f"Evaluare: {course.evaluation_form or '-'}\n"
        f"Categorie formativă: {course.categoria_formativa or '-'}\n\n"
        f"Catalog competențe disponibile în Plan:\n{competencies_block}\n\n"
        "Reguli stricte:\n"
        "- Nu inventa numere de credite, ore sau ponderi nestabilite.\n"
        "- Folosește limbaj formal academic românesc.\n"
        "- Conținutul cursului trebuie să aibă 6-10 capitole numerotate.\n"
        "- Conținutul aplicațiilor trebuie să aibă 6-10 teme numerotate.\n"
        "- Bibliografia: 4-8 referințe în stil clasic (autor, titlu, editură, an).\n"
        "- Obiectivele specifice trebuie corelate cu competențele din catalog."
    )
    raw = claude_service._call_claude_tool(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=(
            "Ești un expert în proiectarea fișelor de disciplină pentru "
            "învățământul superior românesc tehnic."
        ),
        tool=_DRAFT_TOOL,
        tool_name="submit_fd_draft",
    )

    def _s(key: str) -> str:
        return str(raw.get(key, "")).strip() or "(nu s-a generat)"

    return [
        FdDraftSection(title="Obiective generale", body=_s("obiective_generale")),
        FdDraftSection(title="Obiective specifice", body=_s("obiective_specifice")),
        FdDraftSection(title="Conținut curs", body=_s("continut_curs")),
        FdDraftSection(title="Conținut aplicații", body=_s("continut_aplicatii")),
        FdDraftSection(title="Bibliografie", body=_s("bibliografie")),
        FdDraftSection(title="Metode de evaluare", body=_s("metode_evaluare")),
    ]


def _render_markdown(
    course: PlanCourseSummary,
    competencies: list[str],
    sections: list[FdDraftSection],
    selected_cp: list[SelectedCompetency] | None = None,
    selected_ct: list[SelectedCompetency] | None = None,
) -> str:
    selected_cp = selected_cp or []
    selected_ct = selected_ct or []
    lines: list[str] = []
    lines.append(f"# Fișa Disciplinei — {course.course_name}")
    lines.append("")
    lines.append("## Date administrative (preluate din Plan)")
    lines.append("")
    lines.append(f"- **Denumire disciplină:** {course.course_name}")
    if course.course_code:
        lines.append(f"- **Cod disciplină:** {course.course_code}")
    if course.year:
        lines.append(f"- **An de studiu:** {course.year}")
    if course.semester:
        lines.append(f"- **Semestru:** {course.semester}")
    if course.credits is not None:
        lines.append(f"- **Credite:** {course.credits}")
    if course.evaluation_form:
        lines.append(f"- **Formă de evaluare:** {course.evaluation_form}")
    if course.categoria_formativa:
        lines.append(f"- **Categorie formativă:** {course.categoria_formativa}")
    if course.total_hours is not None:
        lines.append(f"- **Ore totale (semestriale):** {course.total_hours}")
    if course.weekly_hours:
        lines.append(f"- **Ore săptămânale (C/S/L/P):** {course.weekly_hours}")

    if selected_cp or selected_ct:
        lines.append("")
        lines.append("## Competențe specifice (selectate pentru această disciplină)")
        for entry in selected_cp:
            lines.append("")
            lines.append(f"### {entry.code} — {entry.title}")
            if entry.rationale:
                lines.append(f"_Motivație AI: {entry.rationale}_")
            for ri in entry.ri_bullets:
                lines.append(f"- {ri}")
        for entry in selected_ct:
            lines.append("")
            lines.append(f"### {entry.code} — {entry.title}")
            if entry.rationale:
                lines.append(f"_Motivație AI: {entry.rationale}_")
            for ri in entry.ri_bullets:
                lines.append(f"- {ri}")
    elif competencies:
        lines.append("")
        lines.append("## Catalog competențe disponibile în Plan")
        lines.append("")
        for c in competencies:
            lines.append(f"- {c}")

    for section in sections:
        lines.append("")
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.body)

    lines.append("")
    return "\n".join(lines)
