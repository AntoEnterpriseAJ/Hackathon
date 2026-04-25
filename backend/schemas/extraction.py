"""
Typed output schema for parsed documents.

Every extracted value carries a `field_type` tag so downstream validation
can apply type-specific rules (date parsing, boolean coercion, signature
flagging) without needing to know the document type in advance.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


FieldType = Literal["string", "date", "number", "boolean", "list", "signature", "id"]
Confidence = Literal["high", "medium", "low"]
SourceRoute = Literal["text_pdf", "scanned_pdf", "image", "fast_pdfplumber"]


class ExtractedField(BaseModel):
    key: str
    value: str | float | bool | list[str] | None
    field_type: FieldType
    confidence: Confidence = "high"


class ExtractedTable(BaseModel):
    name: str
    headers: list[str]
    rows: list[list[str]]


class ExtractedDocument(BaseModel):
    document_type: str          # free-form label from Claude, e.g. "IEP", "attendance_sheet"
    summary: str
    fields: list[ExtractedField] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    source_route: SourceRoute   # which extraction path produced this document

