import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pydantic import ValidationError

from schemas.extraction import ExtractedDocument
from schemas.template_validation import SemanticSuggestionResult, ValidationResult
from services import claude_service, pdf_router, scan_extractor, text_extractor
from services.template_suggester import suggest_template_fixes
from services.template_validator import validate_template

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
async def parse_document(file: UploadFile = File(...)) -> ExtractedDocument:
    """
    Accept a PDF or image file and return structured extracted data.

    Routing logic:
      1. Image file (.png/.jpg/etc.)  → scan_extractor → Claude Vision
      2. Text-based PDF               → text_extractor → Claude text prompt
      3. Scanned PDF (image-only)     → scan_extractor → Claude Vision
    """
    print("reached /parse endpoint")  # Debug log to confirm endpoint is hit
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

    try:
        _markdown_fn = None
        if is_image:
            source_route = "image"
            page_images = scan_extractor.extract_page_images(
                file_bytes, filename, is_pdf=False
            )
            raw = claude_service.extract_from_images(page_images)
            _markdown_fn = lambda: claude_service.generate_markdown_from_images(page_images)  # noqa: E731

        else:  # PDF
            route = pdf_router.detect_route(file_bytes)
            source_route = route

            if route == "text_pdf":
                text = text_extractor.extract_text(file_bytes)
                raw = claude_service.extract_from_text(text)
                _markdown_fn = lambda: claude_service.generate_markdown_from_text(text)  # noqa: E731
            else:  # scanned_pdf
                num_pages = scan_extractor.count_pdf_pages(file_bytes)
                if num_pages > scan_extractor._PAGE_BATCH_THRESHOLD:
                    raw = claude_service.extract_from_images_paged(file_bytes)
                    _markdown_fn = lambda: claude_service.generate_markdown_from_images_paged(file_bytes)  # noqa: E731
                else:
                    page_images = scan_extractor.extract_page_images(
                        file_bytes, filename, is_pdf=True
                    )
                    raw = claude_service.extract_from_images(page_images)
                    _markdown_fn = lambda: claude_service.generate_markdown_from_images(page_images)  # noqa: E731

        raw = _normalize_extracted_payload(raw)
        extracted = ExtractedDocument(**raw, source_route=source_route)

        if _markdown_fn is not None:
            try:
                extracted.markdown_content = _markdown_fn()
            except Exception as md_exc:
                print(f"Markdown generation failed (non-fatal): {md_exc}")

        return extracted

    except RuntimeError as exc:
        # e.g. missing API key
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise HTTPException(
            status_code=500,
            detail=f"Parsed document validation failed: {error_messages}",
        ) from exc
    except Exception as exc:
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
