import re
import traceback
import unicodedata
import base64
import io
import json
import os
from urllib.parse import quote
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic import ValidationError

from schemas.cross_validation import CoverageReport, CrossValidationResult
from schemas.diff_narrative import DiffNarrative
from schemas.extraction import ExtractedDocument
from schemas.template_validation import SemanticSuggestionResult, ValidationResult
from schemas.competency_mapping import CompetencyMapping
from schemas.fd_draft import FdDraft, PlanCourseListResponse
from services import claude_service, pdf_router, scan_extractor, text_extractor
from services.competency_mapper import map_competencies
from services.fd_docx_renderer import render_fd_docx
from services.fd_drafter import draft_fd_from_plan, list_plan_courses
from services.cross_doc_validator import cross_validate, cross_validate_batch
from services.diff_explainer import explain_diff
from services.document_classifier import classify as classify_document
from services.fd_bundle_splitter import split_fd_bundle
from services.fd_fast_parser import parse_fd as fast_parse_fd
from services.bibliography_checker import (
    BibliographyReport,
    check_bibliography,
    check_fd_bibliography,
)
from services.numeric_consistency import (
    NumericConsistencyReport,
    check_fd_numeric_consistency,
)
from services.parse_cache import parse_cache
from services.pi_fast_parser import parse_pi as fast_parse_pi
from services.template_suggester import suggest_template_fixes
from services.template_validator import validate_template
from services.docx_section_extractor import extract_sections as extract_docx_sections
from services.template_filler import fill_template
from services.template_section_mapper import map_sections
from schemas.template_shift import (
    AdminUpdateReport,
    SectionMatchReport,
    ShiftReport,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    documents: list[dict] = []


class ChatResponse(BaseModel):
    reply: str


class ValidateTemplateRequest(BaseModel):
    template: dict[str, Any]
    template_schema: dict[str, Any] = Field(alias="schema")
    guards: list[dict[str, Any]] = []


class SuggestTemplateRequest(BaseModel):
    user_message: str
    template: dict[str, Any]
    template_schema: dict[str, Any] = Field(alias="schema")
    guards: list[dict[str, Any]] = []


class CrossValidateRequest(BaseModel):
    fd: dict[str, Any]
    plan: dict[str, Any]


class MapCompetenciesRequest(BaseModel):
    fd: dict[str, Any]
    plan: dict[str, Any]
    use_claude: bool | None = None


class ListPlanCoursesRequest(BaseModel):
    plan: dict[str, Any]


class DraftFdRequest(BaseModel):
    plan: dict[str, Any]
    course_name: str
    course_code: str | None = None
    use_claude: bool | None = None


class CrossValidateBatchRequest(BaseModel):
    plan: dict[str, Any]
    fds: list[dict[str, Any]]


class ExplainDiffRequest(BaseModel):
    diff: dict[str, Any]


class CheckNumericConsistencyRequest(BaseModel):
    fd: dict[str, Any]


class CheckBibliographyRequest(BaseModel):
    text: str
    max_age_years: int = 5
    check_urls: bool = False
    current_year: int | None = None


class CheckFdBibliographyRequest(BaseModel):
    fd: dict[str, Any]
    max_age_years: int = 5
    check_urls: bool = False
    current_year: int | None = None


class FdSliceResponse(BaseModel):
    index: int
    course_name_hint: str | None
    page_start: int
    page_end: int
    pdf_base64: str


class SplitFdBundleResponse(BaseModel):
    total_pages: int
    fd_count: int
    slices: list[FdSliceResponse]

_PDF_MIMES = {"application/pdf"}
_IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/tiff",
    "image/bmp",
}
_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|webp|tiff?|bmp)$", re.IGNORECASE)
_PDF_EXT = re.compile(r"\.pdf$", re.IGNORECASE)


def _normalize_extracted_payload(raw: dict | None) -> dict:
    payload = dict(raw or {})

    if not payload.get("document_type"):
        payload["document_type"] = "form"

    if payload.get("summary") is None:
        payload["summary"] = ""

    fields = payload.get("fields")
    if fields is None or not isinstance(fields, list):
        payload["fields"] = []

    tables = payload.get("tables")
    if tables is None or not isinstance(tables, list):
        payload["tables"] = []

    return payload


@router.post("/parse", response_model=ExtractedDocument)
async def parse_document(
    file: UploadFile = File(...),
) -> ExtractedDocument:
    """
    Accept a PDF or image file and return structured extracted data.

    Routing logic:
      1. Image file (.png/.jpg/etc.)  → scan_extractor → Claude Vision
      2. Text-based PDF               → text_extractor → Claude text prompt
      3. Scanned PDF (image-only)     → scan_extractor → Claude Vision
    """
    content_type = (file.content_type or "").split(";")[0].strip()
    filename = file.filename or ""
    file_bytes = await file.read()

    is_image = content_type in _IMAGE_MIMES or bool(_IMAGE_EXT.search(filename))
    is_pdf = content_type in _PDF_MIMES or bool(_PDF_EXT.search(filename))

    if not is_image and not is_pdf:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Accepted: PDF or image files.",
        )

    cache_key = parse_cache.hash_bytes(file_bytes)
    cached = parse_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        if is_image:
            source_route = "image"
            page_images = scan_extractor.extract_page_images(
                file_bytes, filename, is_pdf=False
            )
            raw = claude_service.extract_from_images(page_images)

        else:  # PDF
            # Try the deterministic fast path first for known FD/PI documents.
            kind = classify_document(file_bytes)
            if kind == "fd":
                fast = fast_parse_fd(file_bytes)
                if fast is not None:
                    parse_cache.put(cache_key, fast)
                    return fast
            elif kind == "pi":
                fast = fast_parse_pi(file_bytes)
                if fast is not None:
                    parse_cache.put(cache_key, fast)
                    return fast

            route = pdf_router.detect_route(file_bytes)
            source_route = route

            if route == "text_pdf":
                text = text_extractor.extract_text(file_bytes)
                raw = claude_service.extract_from_text(text)
            else:  # scanned_pdf
                num_pages = scan_extractor.count_pdf_pages(file_bytes)
                if num_pages > scan_extractor._PAGE_BATCH_THRESHOLD:
                    raw = claude_service.extract_from_images_paged(file_bytes)
                else:
                    page_images = scan_extractor.extract_page_images(
                        file_bytes, filename, is_pdf=True
                    )
                    raw = claude_service.extract_from_images(page_images)

        raw = _normalize_extracted_payload(raw)
        extracted = ExtractedDocument(**raw, source_route=source_route)
        parse_cache.put(cache_key, extracted)
        return extracted

    except RuntimeError as exc:
        # e.g. missing API key
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValidationError as exc:
        traceback.print_exc()
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=500,
            detail=f"Parsed document validation failed: {error_messages}",
        ) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer a teacher's question, optionally grounded in extracted document data."""
    try:
        reply = claude_service.chat(req.message, req.documents)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
    return ChatResponse(reply=reply)


@router.post("/validate", response_model=ValidationResult)
async def validate(req: ValidateTemplateRequest) -> ValidationResult:
    """Validate a generic template against a provided schema and guard set."""
    return validate_template(
        template=req.template,
        schema=req.template_schema,
        guards=req.guards,
    )


@router.post("/suggest", response_model=SemanticSuggestionResult)
async def suggest(req: SuggestTemplateRequest) -> SemanticSuggestionResult:
    """Generate semantic fix suggestions, then keep only revalidated patches."""
    return suggest_template_fixes(
        user_message=req.user_message,
        template=req.template,
        schema=req.template_schema,
        guards=req.guards,
    )


@router.post("/cross-validate", response_model=CrossValidationResult)
async def cross_validate_endpoint(req: CrossValidateRequest) -> CrossValidationResult:
    """Validate a Fișa Disciplinei against a Plan de Învățământ (the source of truth)."""
    try:
        fd_doc = ExtractedDocument(**{**req.fd, "source_route": req.fd.get("source_route", "text_pdf")})
        plan_doc = ExtractedDocument(**{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")})
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    return cross_validate(fd=fd_doc, plan=plan_doc)


@router.post("/check-numeric-consistency", response_model=NumericConsistencyReport)
async def check_numeric_consistency_endpoint(
    req: CheckNumericConsistencyRequest,
) -> NumericConsistencyReport:
    """UC 1.2 — Verify internal numeric consistency of a parsed FD."""
    try:
        fd_doc = ExtractedDocument(
            **{**req.fd, "source_route": req.fd.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    return check_fd_numeric_consistency(fd_doc)


@router.post("/check-bibliography", response_model=BibliographyReport)
async def check_bibliography_endpoint(
    req: CheckBibliographyRequest,
) -> BibliographyReport:
    """UC 3.1 — Check bibliography freshness and (optionally) URL liveness."""
    return check_bibliography(
        req.text,
        current_year=req.current_year,
        max_age_years=req.max_age_years,
        check_urls=req.check_urls,
    )


@router.post("/check-fd-bibliography", response_model=BibliographyReport)
async def check_fd_bibliography_endpoint(
    req: CheckFdBibliographyRequest,
) -> BibliographyReport:
    """UC 3.1 — Bibliography check from a parsed FD (uses fields/tables)."""
    try:
        fd_doc = ExtractedDocument(
            **{**req.fd, "source_route": req.fd.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc
    return check_fd_bibliography(
        fd_doc,
        current_year=req.current_year,
        max_age_years=req.max_age_years,
        check_urls=req.check_urls,
    )


@router.post("/map-competencies", response_model=CompetencyMapping)
async def map_competencies_endpoint(req: MapCompetenciesRequest) -> CompetencyMapping:
    """Map FD competence references against the Plan's official catalogue (UC 2.2)."""
    try:
        fd_doc = ExtractedDocument(
            **{**req.fd, "source_route": req.fd.get("source_route", "text_pdf")}
        )
        plan_doc = ExtractedDocument(
            **{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    return map_competencies(fd=fd_doc, plan=plan_doc, use_claude=req.use_claude)


@router.post("/list-plan-courses", response_model=PlanCourseListResponse)
async def list_plan_courses_endpoint(req: ListPlanCoursesRequest) -> PlanCourseListResponse:
    """List all courses found in a parsed Plan (used by the FD Drafter picker)."""
    try:
        plan_doc = ExtractedDocument(
            **{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    program = None
    for f in plan_doc.fields:
        if f.key in ("program_studii", "denumire_program", "specializare") and isinstance(f.value, str):
            program = f.value
            break
    return PlanCourseListResponse(program=program, courses=list_plan_courses(plan_doc))


@router.post("/draft-fd", response_model=FdDraft)
async def draft_fd_endpoint(req: DraftFdRequest) -> FdDraft:
    """UC 3.4 — generate a draft Fișa Disciplinei from a Plan course entry."""
    try:
        plan_doc = ExtractedDocument(
            **{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    return draft_fd_from_plan(
        plan=plan_doc,
        course_name=req.course_name,
        course_code=req.course_code,
        use_claude=req.use_claude,
    )


@router.post("/draft-fd-docx")
async def draft_fd_docx_endpoint(req: DraftFdRequest) -> StreamingResponse:
    """UC 1.4 — generate the FD as a real .docx using the UTCN template."""
    try:
        plan_doc = ExtractedDocument(
            **{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")}
        )
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    draft = draft_fd_from_plan(
        plan=plan_doc,
        course_name=req.course_name,
        course_code=req.course_code,
        use_claude=req.use_claude,
    )

    plan_meta = {f.key: f.value for f in plan_doc.fields if isinstance(f.value, (str, int, float))}

    try:
        docx_bytes = render_fd_docx(draft=draft, plan_meta=plan_meta)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    pretty = f"FD_{draft.course_name}.docx"
    # ASCII fallback for legacy clients (strip diacritics, then strip non-word chars).
    ascii_stem = unicodedata.normalize("NFKD", draft.course_name).encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_stem).strip("_") or "fisa"
    ascii_filename = f"FD_{ascii_stem}.docx"
    # RFC 5987 — pretty UTF-8 filename for modern browsers.
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_filename}"; '
                f"filename*=UTF-8''{quote(pretty, safe='')}"
            ),
        },
    )


@router.post("/cross-validate-batch", response_model=CoverageReport)
async def cross_validate_batch_endpoint(req: CrossValidateBatchRequest) -> CoverageReport:
    """Validate many FDs against one Plan; return a coverage report."""
    try:
        plan_doc = ExtractedDocument(
            **{**req.plan, "source_route": req.plan.get("source_route", "text_pdf")}
        )
        fd_docs = [
            ExtractedDocument(**{**fd, "source_route": fd.get("source_route", "text_pdf")})
            for fd in req.fds
        ]
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extracted document payload: {error_messages}",
        ) from exc

    return cross_validate_batch(plan=plan_doc, fds=fd_docs)


@router.post("/explain-diff", response_model=DiffNarrative)
async def explain_diff_endpoint(req: ExplainDiffRequest) -> DiffNarrative:
    """Turn a diff-service DiffResponse into a Romanian-language narrative for the professor."""
    try:
        result = explain_diff(req.diff)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Diff explanation failed: {exc}") from exc

    return DiffNarrative(**result)


@router.post("/split-fd-bundle", response_model=SplitFdBundleResponse)
async def split_fd_bundle_endpoint(file: UploadFile = File(...)) -> SplitFdBundleResponse:
    """Split a multi-FD bundle PDF into individual FD PDFs.

    Returns base64-encoded per-FD PDFs along with the detected course-name
    hint and original page range. The frontend can then forward each slice
    to ``/parse`` for full extraction.
    """
    import base64

    filename = file.filename or ""
    if not _PDF_EXT.search(filename) and (file.content_type or "") not in _PDF_MIMES:
        raise HTTPException(
            status_code=415,
            detail="Bundle splitting requires a PDF file.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        slices = split_fd_bundle(file_bytes)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Splitting failed: {exc}"
        ) from exc

    import pymupdf
    with pymupdf.open(stream=file_bytes, filetype="pdf") as src:
        total_pages = src.page_count

    return SplitFdBundleResponse(
        total_pages=total_pages,
        fd_count=len(slices),
        slices=[
            FdSliceResponse(
                index=s.index,
                course_name_hint=s.course_name_hint,
                page_start=s.page_start,
                page_end=s.page_end,
                pdf_base64=base64.b64encode(s.pdf_bytes).decode("ascii"),
            )
            for s in slices
        ],
    )

# (template-shifter endpoint appended below)


def _claude_complete_text(prompt: str) -> str:
    """Plain text completion via Claude. Used by the template-shift mapper."""
    from services import claude_service as _cs

    response = _cs._get_client().messages.create(  # type: ignore[attr-defined]
        model=getattr(_cs, "_MODEL", "claude-sonnet-4-5"),
        max_tokens=getattr(_cs, "_MAX_TOKENS", 4096),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text  # type: ignore[union-attr]


def _claude_is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


@router.post("/shift-template")
async def shift_template_endpoint(
    old_fd: UploadFile = File(...),
    new_template: UploadFile = File(...),
    plan: UploadFile | None = File(None),
) -> StreamingResponse:
    old_bytes = await old_fd.read()
    new_bytes = await new_template.read()

    try:
        old_sections = extract_docx_sections(old_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid old FD docx: {exc}") from exc
    try:
        new_sections = extract_docx_sections(new_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid template docx: {exc}") from exc

    if not old_sections or not new_sections:
        raise HTTPException(status_code=422, detail="No sections detected; check headings")

    plan_meta: dict = {}
    if plan is not None:
        try:
            pdf_bytes = await plan.read()
            parsed = fast_parse_pi(pdf_bytes)
            plan_meta = parsed if isinstance(parsed, dict) else {}
        except Exception:
            traceback.print_exc()
            plan_meta = {}

    claude_callable = _claude_complete_text if _claude_is_configured() else None
    matches = map_sections(old_sections, new_sections, claude=claude_callable)

    filled_bytes = fill_template(
        template_bytes=new_bytes,
        old_sections=old_sections,
        new_sections=new_sections,
        matches=matches,
        plan_meta=plan_meta,
    )

    report = _build_shift_report(
        old_sections, new_sections, matches, plan_meta, claude_callable is not None
    )
    encoded = base64.b64encode(
        json.dumps(report.model_dump(), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    headers = {
        "Content-Disposition": 'attachment; filename="fisa_disciplinei_migrated.docx"',
        "X-Shift-Report": encoded,
    }
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


def _build_shift_report(
    old_sections, new_sections, matches, plan_meta, llm_available: bool
) -> ShiftReport:
    new_by_id = {s.id: s for s in new_sections}
    old_by_id = {s.id: s for s in old_sections}

    match_reports: list[SectionMatchReport] = []
    placeholders: list[str] = []
    for m in matches:
        new_sec = new_by_id.get(m.new_section_id)
        old_sec = old_by_id.get(m.old_section_id) if m.old_section_id else None
        new_heading = new_sec.heading if new_sec else m.new_section_id
        match_reports.append(
            SectionMatchReport(
                new_heading=new_heading,
                old_heading=old_sec.heading if old_sec else None,
                confidence=m.confidence,
                rationale=m.rationale,
            )
        )
        if m.confidence == "placeholder":
            placeholders.append(new_heading)

    admin_keys = {
        "decanul_facultatii",
        "directorul_de_departament",
        "programul_de_studii",
        "facultatea",
        "domeniul_de_licenta",
        "coordonator_program_studii",
        "rector",
    }
    admin_updates = [
        AdminUpdateReport(field=k, value=str(v))
        for k, v in (plan_meta or {}).items()
        if k in admin_keys and v
    ]

    return ShiftReport(
        matches=match_reports,
        admin_updates=admin_updates,
        placeholders=placeholders,
        llm_used=llm_available
        and any(m.confidence.startswith("llm-") for m in matches),
    )
