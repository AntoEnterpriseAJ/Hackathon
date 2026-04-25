"""
Call Claude Sonnet 4.6 with forced tool_use to guarantee structured JSON output.

Forced tool_use means Claude will ALWAYS respond with a ToolUseBlock matching
the defined input_schema — no need to parse free-form text.
"""
import json
import os

import anthropic

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 16384

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Extraction tool schema — Claude is forced to return data matching this shape
# ---------------------------------------------------------------------------

_EXTRACTION_TOOL: dict = {
    "name": "extract_document_data",
    "description": (
        "Extract structured data from a school document. "
        "Every extracted value must carry a field_type tag so downstream "
        "validation can apply type-specific rules without knowing the document type."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "description": (
                    "Free-form document type label, e.g. 'IEP', 'attendance_sheet', "
                    "'parent_communication', 'permission_slip', 'report_card', 'form'."
                ),
            },
            "summary": {
                "type": "string",
                "description": "1-3 sentence summary of the document's content and purpose.",
            },
            "fields": {
                "type": "array",
                "description": (
                    "All important key-value pairs extracted from the document. "
                    "Each entry has a key (snake_case), a value, a field_type, and a confidence."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "snake_case field name, e.g. 'student_name', 'effective_date'",
                        },
                        "value": {
                            "description": (
                                "The extracted value. "
                                "Dates must be ISO-8601 (YYYY-MM-DD). "
                                "Booleans must be true/false (not 'Yes'/'No'). "
                                "Lists must be JSON arrays of strings. "
                                "Numbers must be numeric."
                            ),
                        },
                        "field_type": {
                            "type": "string",
                            "enum": ["string", "date", "number", "boolean", "list", "signature", "id"],
                            "description": (
                                "string — plain text; "
                                "date — ISO-8601 date; "
                                "number — numeric value; "
                                "boolean — true/false; "
                                "list — array of strings; "
                                "signature — field requiring a human signature; "
                                "id — identifier like student ID or case number."
                            ),
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": (
                                "high — clearly visible and unambiguous; "
                                "medium — inferred or partially legible; "
                                "low — uncertain, may need human review."
                            ),
                        },
                    },
                    "required": ["key", "value", "field_type", "confidence"],
                },
            },
            "tables": {
                "type": "array",
                "description": "Tabular data extracted from the document.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Descriptive table name, e.g. 'goals', 'attendance_records'.",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Column header names in snake_case.",
                        },
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "description": "Data rows — each row has the same number of cells as headers.",
                        },
                    },
                    "required": ["name", "headers", "rows"],
                },
            },
        },
        "required": ["document_type", "summary", "fields", "tables"],
    },
}

_SYSTEM_PROMPT = (
    "You are an assistant that helps teachers extract and organize information "
    "from school documents, with special focus on Romanian academic and university paperwork. "
    "Common inputs include curriculum plans, discipline sheets, administrative forms, tables, legends, and approval pages. "
    "Extract ALL important fields and preserve Romanian text exactly as written, including diacritics and institutional terminology. "
    "Do not translate headings, course names, faculty names, departments, or program labels. "
    "Normalize dates to ISO-8601 (YYYY-MM-DD) when they are clear. "
    "Convert Yes/No answers to boolean true/false. "
    "Use field_type:'list' for competencies, occupations, grouped notes, bullet lists, legends, and similar multi-value sections. "
    "Use field_type:'signature' for any field requiring or representing a human signature or signatory block. "
    "Use field_type:'id' for form references, document codes, approval numbers, and official identifiers. "
    "Use numeric values for credits, hours, totals, percentages, academic years, and counts when the value is unambiguous. "
    "Use null when a field exists but is blank or not filled in. "
    "Preserve tabular content in the tables array whenever the document contains repeated grids such as semesters, disciplines, or balances. "
    "Keep table columns logically separated and do not merge unrelated columns. "
    "Mark confidence 'medium' or 'low' for handwritten, partially legible, ambiguous, or layout-dependent values. "
    "Do not invent data absent from the document."
)

_SUGGESTION_TOOL: dict = {
    "name": "suggest_template_fixes",
    "description": (
        "Suggest 2-3 compliant fixes for a template that violated one or more guards. "
        "Return a short explanation and structured patch options only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "explanation": {
                "type": "string",
                "description": "Short explanation of why the current template is invalid.",
            },
            "suggestions": {
                "type": "array",
                "description": "Candidate compliant fixes expressed as structured patches.",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "label": {"type": "string"},
                        "reason": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "patch": {
                            "type": "object",
                            "description": (
                                "Partial template update to apply if the user accepts this suggestion."
                            ),
                        },
                    },
                    "required": ["code", "label", "reason", "confidence", "patch"],
                },
            },
        },
        "required": ["explanation", "suggestions"],
    },
}

_SUGGESTION_SYSTEM_PROMPT = (
    "You are a correction assistant for Romanian academic templates. "
    "You help repair structured templates for grading, discipline sheets, curriculum forms, and related university paperwork. "
    "Given a user instruction, current template state, schema summary, guard rules, and current violations, produce only compliant candidate fixes. "
    "Return 2 to 3 concrete patch suggestions when possible. "
    "Never propose a patch that still violates the guards. "
    "Do not return prose-only advice without a patch. "
    "Do not repeat invalid states. "
    "Prefer minimal patch changes that preserve the user's apparent intent while satisfying the rules. "
    "For grading or assessment templates, keep grading weights internally consistent, respect hard caps such as a maximum exam percentage, and preserve totals such as 100% distributions."
)

_GUARD_DRAFT_TOOL: dict = {
    "name": "suggest_guard_drafts",
    "description": (
        "Suggest editable guard drafts for extracted template fields. "
        "Return field-scoped options with one selected default per field."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "guard_drafts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "selected_code": {"type": "string"},
                        "rationale": {"type": "string"},
                        "suggestions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string"},
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                    "guard": {
                                        "type": "object",
                                        "properties": {
                                            "code": {"type": "string"},
                                            "kind": {"type": "string"},
                                            "field": {"type": "string"},
                                            "message": {"type": "string"},
                                            "params": {"type": "object"},
                                        },
                                        "required": ["code", "kind", "field", "message", "params"],
                                    },
                                },
                                "required": ["code", "label", "description", "guard"],
                            },
                        },
                    },
                    "required": ["field", "selected_code", "rationale", "suggestions"],
                },
            }
        },
        "required": ["guard_drafts"],
    },
}

_GUARD_DRAFT_SYSTEM_PROMPT = (
    "You are an academic template guard assistant. "
    "Given an extracted template, inferred schema, and deterministic baseline guard drafts, "
    "return only field-level guard suggestions that would help a user review and export a guards file. "
    "Each field should have a selected default and 1-3 meaningful alternatives. "
    "Prefer concise, machine-usable guard definitions over prose."
)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def extract_from_text(text: str) -> dict:
    """Extract structured data from plain text content."""
    messages = [
        {
            "role": "user",
            "content": (
                "Extract this document into the current structured schema. "
                "Capture document metadata, institutional details, academic structure, signatories, legends, totals, and tabular data when present. "
                "Return fields for scalar or list facts and tables for repeated grids.\n\n"
                f"{text}"
            ),
        }
    ]
    return _call_claude(messages)


def extract_from_images_paged(file_bytes: bytes) -> dict:
    """
    Extract from a scanned PDF by sending one page at a time to Claude,
    then merge all results. Used automatically for PDFs > _PAGE_BATCH_THRESHOLD pages.
    """
    from services import scan_extractor  # local import to avoid circular
    from schemas.extraction import ExtractedDocument
    from routers.documents import _normalize_extracted_payload

    num_pages = scan_extractor.count_pdf_pages(file_bytes)
    all_fields: list = []
    all_tables: list = []
    document_type: str | None = None
    summary_parts: list[str] = []
    seen_field_keys: set[str] = set()
    seen_table_names: set[str] = set()

    for i in range(min(num_pages, scan_extractor._MAX_PAGES)):
        b64 = scan_extractor.extract_single_page_image(file_bytes, i)
        raw = extract_from_images([b64])
        raw = _normalize_extracted_payload(raw)
        page_doc = ExtractedDocument(**raw, source_route="scanned_pdf")

        if document_type is None and page_doc.document_type not in (None, "", "form"):
            document_type = page_doc.document_type
        if page_doc.summary:
            summary_parts.append(page_doc.summary)

        for f in page_doc.fields:
            if f.key not in seen_field_keys:
                seen_field_keys.add(f.key)
                all_fields.append(f.model_dump())

        for t in page_doc.tables:
            tname = t.name
            base_name = tname
            suffix = 2
            while tname in seen_table_names:
                tname = f"{base_name}_p{i + 1}_{suffix}"
                suffix += 1
            seen_table_names.add(tname)
            all_tables.append({**t.model_dump(), "name": tname})

    return {
        "document_type": document_type or "form",
        "summary": " ".join(dict.fromkeys(summary_parts)),  # deduplicate order-preserving
        "fields": all_fields,
        "tables": all_tables,
    }


def extract_from_images(page_images: list[str]) -> dict:
    """Extract structured data from base64-encoded PNG page images."""
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        }
        for b64 in page_images
    ]
    content.append(
        {
            "type": "text",
            "text": (
                "Extract this Romanian academic or administrative document into the current structured schema. "
                "Preserve Romanian text exactly, capture titles, institutions, academic years, semesters, courses, credits, hours, legends, approvals, signatures, and any repeated tables."
            ),
        }
    )
    return _call_claude([{"role": "user", "content": content}])


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------
#
# DEV-ONLY UTILITIES. These functions are not invoked by any HTTP route.
# They exist for `backend/generate_mock_markdown.py` (a one-off CLI used to
# pre-generate `mock-data/*.parsed.md`) and for future on-demand markdown
# rendering. Do not call them from request handlers — they cost a full
# Claude round-trip on top of structured extraction and the runtime app
# never reads the resulting markdown.

_MARKDOWN_SYSTEM_PROMPT = (
    "You are an expert document parser specialized in converting Romanian academic and administrative "
    "PDFs into clean, well-structured Markdown documents. "
    "Preserve the original structure as much as possible: titles, section headings, subheadings, tables, "
    "footnotes, notes, year and semester organization, discipline and course names, credits, hours, "
    "exam or evaluation type, abbreviations, and legends. "
    "Convert all tables into valid Markdown tables with aligned columns. "
    "Do not merge unrelated columns and do not drop empty columns that carry meaning. "
    "If a table is too complex for clean Markdown, represent it using structured bullet sections instead. "
    "Do not summarize — output a faithful conversion that keeps all information from the document. "
    "Preserve Romanian text exactly as written, including all diacritics. "
    "Do not translate headings, course names, faculty names, department names, or institutional labels."
)


def generate_markdown_from_text(text: str) -> str:
    """Convert plain-text document content to a faithful Markdown representation."""
    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_MARKDOWN_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Convert the following document into a clean, well-structured Markdown document. "
                    "Preserve all content, structure, tables, and Romanian text exactly.\n\n"
                    f"{text}"
                ),
            }
        ],
    )
    return response.content[0].text  # type: ignore[union-attr]


def generate_markdown_from_images(page_images: list[str]) -> str:
    """Convert page images (base64-encoded PNGs) to a faithful Markdown representation."""
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        }
        for b64 in page_images
    ]
    content.append(
        {
            "type": "text",
            "text": (
                "Convert this Romanian academic or administrative document into a clean, well-structured "
                "Markdown document. Preserve all content, structure, tables as Markdown tables, "
                "Romanian text, and diacritics exactly."
            ),
        }
    )
    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_MARKDOWN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text  # type: ignore[union-attr]


def generate_markdown_from_images_paged(file_bytes: bytes) -> str:
    """
    Convert a multi-page scanned PDF to Markdown by collecting all page images
    (up to _MAX_PAGES) and sending them in a single Claude call.
    """
    from services import scan_extractor as _scan  # local import to avoid circular

    num_pages = _scan.count_pdf_pages(file_bytes)
    page_images = [
        _scan.extract_single_page_image(file_bytes, i)
        for i in range(min(num_pages, _scan._MAX_PAGES))
    ]
    return generate_markdown_from_images(page_images)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


_CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant for teachers. "
    "You help with school paperwork, drafting parent communications, "
    "summarizing documents, creating checklists, and extracting action items. "
    "Be concise, practical, and professional. "
    "When document context is provided, base your answers strictly on that content."
)


def chat(user_message: str, document_contexts: list[dict]) -> dict:
    """
    Answer a teacher's question, optionally grounded in extracted document data.

    Returns a dict ``{"reply": str, "followups": list[str]}``.
    """
    content_parts: list[dict] = []

    if document_contexts:
        doc_block = "The following documents have been uploaded and parsed:\n\n"
        for i, doc in enumerate(document_contexts, 1):
            doc_block += f"--- Document {i}: {doc.get('document_type', 'unknown')} ---\n"
            doc_block += f"Summary: {doc.get('summary', '')}\n"
            fields = doc.get("fields", [])
            if fields:
                doc_block += "Fields:\n"
                for f in fields:
                    if isinstance(f, dict):
                        conf = f" [{f.get('confidence','high')}]" if f.get("confidence") != "high" else ""
                        doc_block += f"  {f.get('key')}: {f.get('value')}{conf}\n"
                    else:
                        # legacy dict[str,str] fallback
                        for k, v in f.items():
                            doc_block += f"  {k}: {v}\n"
            tables = doc.get("tables", [])
            if tables:
                doc_block += f"Tables: {len(tables)} table(s)\n"
                for t in tables:
                    if isinstance(t, dict):
                        doc_block += f"  {t.get('name', '')}: " + " | ".join(t.get("headers", [])) + "\n"
                    elif t:
                        doc_block += "  " + " | ".join(str(c) for c in t[0]) + "\n"
            doc_block += "\n"
        content_parts.append({"type": "text", "text": doc_block})

    content_parts.append({"type": "text", "text": user_message})

    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_CHAT_SYSTEM_PROMPT,
        tools=[_CHAT_REPLY_TOOL],
        tool_choice={"type": "tool", "name": "answer_with_followups"},
        messages=[{"role": "user", "content": content_parts}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            payload = dict(block.input)  # type: ignore[union-attr]
            reply = str(payload.get("reply", "")).strip()
            raw_followups = payload.get("followups", []) or []
            followups: list[str] = []
            if isinstance(raw_followups, list):
                for item in raw_followups[:3]:
                    s = str(item).strip()
                    if s:
                        followups.append(s)
            return {"reply": reply, "followups": followups}

    # Fallback: no tool_use returned (shouldn't happen with tool_choice).
    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = block.text  # type: ignore[union-attr]
            break
    return {"reply": text, "followups": []}


_CHAT_REPLY_TOOL: dict = {
    "name": "answer_with_followups",
    "description": (
        "Answer the user's question and propose 2-3 short, document-specific "
        "follow-up questions the user might naturally ask next."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": (
                    "The full answer to the user's question. Markdown allowed "
                    "(bold, lists, code). Concise and grounded in the provided "
                    "document context. Romanian if the user wrote in Romanian."
                ),
            },
            "followups": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-3 short follow-up questions (sub 60 caractere fiecare) "
                    "specifice documentului discutat. Limba urmează limba "
                    "răspunsului. Fără ghilimele, fără numerotare."
                ),
            },
        },
        "required": ["reply", "followups"],
    },
}


def generate_template_suggestions(
    *,
    user_message: str,
    template: dict,
    schema: dict,
    guards: list[dict],
    violations: list[dict],
    max_suggestions: int,
) -> dict:
    """Return structured semantic suggestions for an invalid template."""
    messages = [
        {
            "role": "user",
            "content": (
                "Generate compliant fix suggestions for this invalid template. "
                f"Return at most {max_suggestions} suggestions.\n\n"
                f"User instruction:\n{user_message}\n\n"
                f"Current template (JSON):\n{_to_json_block(template)}\n\n"
                f"Schema (JSON):\n{_to_json_block(schema)}\n\n"
                f"Guards (JSON):\n{_to_json_block(guards)}\n\n"
                f"Current violations (JSON):\n{_to_json_block(violations)}\n"
            ),
        }
    ]
    return _call_claude_tool(
        messages=messages,
        system_prompt=_SUGGESTION_SYSTEM_PROMPT,
        tool=_SUGGESTION_TOOL,
        tool_name="suggest_template_fixes",
    )


def generate_guard_drafts(
    *,
    document_type: str,
    template: dict,
    schema: dict,
    baseline_guard_drafts: list[dict],
) -> dict:
    messages = [
        {
            "role": "user",
            "content": (
                "Generate editable guard drafts for this extracted template. "
                "Keep suggestions grounded in the current field values and the baseline options.\n\n"
                f"Document type:\n{document_type}\n\n"
                f"Template (JSON):\n{_to_json_block(template)}\n\n"
                f"Schema (JSON):\n{_to_json_block(schema)}\n\n"
                f"Baseline guard drafts (JSON):\n{_to_json_block(baseline_guard_drafts)}\n"
            ),
        }
    ]
    return _call_claude_tool(
        messages=messages,
        system_prompt=_GUARD_DRAFT_SYSTEM_PROMPT,
        tool=_GUARD_DRAFT_TOOL,
        tool_name="suggest_guard_drafts",
    )


def _call_claude(messages: list[dict]) -> dict:
    return _call_claude_tool(
        messages=messages,
        system_prompt=_SYSTEM_PROMPT,
        tool=_EXTRACTION_TOOL,
        tool_name="extract_document_data",
    )


def _to_json_block(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _call_claude_tool(
    *,
    messages: list[dict],
    system_prompt: str,
    tool: dict,
    tool_name: str,
) -> dict:
    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=messages,
    )

    if not response.content:
        raise RuntimeError("Claude returned an empty response (no content blocks).")

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude response exceeded the maximum token limit. "
            "Try sending a smaller payload or fewer pages."
        )

    block = response.content[0]
    if not hasattr(block, "input") or not isinstance(block.input, dict):
        raise RuntimeError(
            f"Unexpected Claude response block type '{type(block).__name__}'; "
            "expected a ToolUseBlock with structured input."
        )

    return block.input
