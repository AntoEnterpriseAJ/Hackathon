import re

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from pydantic import ValidationError

from schemas.extraction import ExtractedDocument
from services import claude_service, pdf_router, scan_extractor, text_extractor

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    documents: list[dict] = []


class ChatResponse(BaseModel):
    reply: str

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
        if is_image:
            source_route = "image"
            page_images = scan_extractor.extract_page_images(
                file_bytes, filename, is_pdf=False
            )
            raw = claude_service.extract_from_images(page_images)

        else:  # PDF
            route = pdf_router.detect_route(file_bytes)
            source_route = route

            if route == "text_pdf":
                text = text_extractor.extract_text(file_bytes)
                raw = claude_service.extract_from_text(text)
            else:  # scanned_pdf
                page_images = scan_extractor.extract_page_images(
                    file_bytes, filename, is_pdf=True
                )
                raw = claude_service.extract_from_images(page_images)

        raw = _normalize_extracted_payload(raw)
        return ExtractedDocument(**raw, source_route=source_route)

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
