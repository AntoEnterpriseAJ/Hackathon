# Template Shifter (UC 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate an old Fișă a Disciplinei (FD) `.docx` into the structure of a new template `.docx`, optionally pulling admin fields from a Plan de Învățământ PDF, with one Claude call to map sections that don't fuzzy-match.

**Architecture:** Single FastAPI endpoint `POST /api/documents/shift-template` accepting multipart upload (old FD docx + new template docx + optional Plan PDF). Pipeline: `docx_section_extractor` → `template_section_mapper` (rapidfuzz + 1 Claude call) → `template_filler` (python-docx, reusing the existing admin-fill helper from `fd_docx_renderer`). Returns the filled `.docx` as `StreamingResponse`; the `ShiftReport` JSON is base64-encoded into the `X-Shift-Report` header. New Angular page at `/template-shift` mirroring the existing `draft/` and `sync-check/` layouts.

**Tech Stack:** Python 3.14, FastAPI, python-docx, rapidfuzz (new), Anthropic Claude (existing `claude_service`); Angular 19 standalone components, signals, RxJS.

**Spec:** [docs/superpowers/specs/2026-04-25-template-shifter-design.md](../specs/2026-04-25-template-shifter-design.md)

---

## File Structure

**New backend files:**
- [backend/schemas/template_shift.py](../../backend/schemas/template_shift.py) — Pydantic models (`SectionMatchReport`, `AdminUpdateReport`, `ShiftReport`)
- [backend/services/docx_section_extractor.py](../../backend/services/docx_section_extractor.py) — pure function `extract_sections(docx_bytes) -> list[Section]`
- [backend/services/template_section_mapper.py](../../backend/services/template_section_mapper.py) — `map_sections(old, new) -> list[SectionMatch]` with deterministic + Claude pass
- [backend/services/template_filler.py](../../backend/services/template_filler.py) — `fill_template(template_bytes, old_sections, matches, plan_meta) -> bytes`
- [backend/tests/test_docx_section_extractor.py](../../backend/tests/test_docx_section_extractor.py)
- [backend/tests/test_template_section_mapper.py](../../backend/tests/test_template_section_mapper.py)
- [backend/tests/test_template_filler.py](../../backend/tests/test_template_filler.py)
- [backend/tests/test_shift_template_api.py](../../backend/tests/test_shift_template_api.py)

**Modified backend files:**
- [backend/requirements.txt](../../backend/requirements.txt) — add `rapidfuzz`
- [backend/main.py](../../backend/main.py) — add `expose_headers=["X-Shift-Report"]` to CORS
- [backend/services/fd_docx_renderer.py](../../backend/services/fd_docx_renderer.py) — extract `apply_admin_fields(doc, plan_meta)` helper without changing existing behavior
- [backend/routers/documents.py](../../backend/routers/documents.py) — new endpoint `POST /shift-template`

**New frontend files:**
- `frontend-hackathon/src/app/template-shift/models/template-shift.models.ts`
- `frontend-hackathon/src/app/template-shift/services/template-shift.service.ts`
- `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.ts`
- `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.html`
- `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.scss`

**Modified frontend files:**
- `frontend-hackathon/src/app/app.routes.ts` — add `/template-shift` lazy route
- `frontend-hackathon/src/app/shared/nav/nav.component.html` — add nav link

---

## Task 1: Add rapidfuzz dependency

**Files:**
- Modify: [backend/requirements.txt](../../backend/requirements.txt)

- [ ] **Step 1: Append rapidfuzz to requirements.txt**

Add a single line at the bottom:

```
rapidfuzz>=3.9
```

- [ ] **Step 2: Install in the workspace venv**

```powershell
d:\dev\repos\hackhathoooooon\Hackathon\.venv\Scripts\python.exe -m pip install rapidfuzz>=3.9
```

Expected: `Successfully installed rapidfuzz-…`.

- [ ] **Step 3: Sanity import**

```powershell
d:\dev\repos\hackhathoooooon\Hackathon\.venv\Scripts\python.exe -c "from rapidfuzz import fuzz; print(fuzz.token_sort_ratio('a b c', 'c b a'))"
```

Expected: `100.0`.

- [ ] **Step 4: Commit**

```powershell
git add backend/requirements.txt
git commit -m "deps(backend): add rapidfuzz for template-shifter heading match"
```

---

## Task 2: Schema — `template_shift.py`

**Files:**
- Create: [backend/schemas/template_shift.py](../../backend/schemas/template_shift.py)
- Test: [backend/tests/test_shift_template_api.py](../../backend/tests/test_shift_template_api.py) (created later, schema only smoke-imported here)

- [ ] **Step 1: Create the schema file**

Content:

```python
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
```

- [ ] **Step 2: Sanity import**

```powershell
d:\dev\repos\hackhathoooooon\Hackathon\.venv\Scripts\python.exe -c "from backend.schemas.template_shift import ShiftReport; print(ShiftReport().model_dump())"
```

Expected: `{'matches': [], 'admin_updates': [], 'placeholders': [], 'llm_used': False}`.

- [ ] **Step 3: Commit**

```powershell
git add backend/schemas/template_shift.py
git commit -m "feat(template-shift): add ShiftReport pydantic schemas"
```

---

## Task 3: Section extractor — failing test

**Files:**
- Create: [backend/tests/test_docx_section_extractor.py](../../backend/tests/test_docx_section_extractor.py)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for services.docx_section_extractor."""
from __future__ import annotations

import io

import pytest
from docx import Document

from backend.services.docx_section_extractor import (
    Section,
    TableBlock,
    TextBlock,
    extract_sections,
)


def _make_docx(builder) -> bytes:
    doc = Document()
    builder(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extracts_heading_styled_sections():
    def build(doc):
        h = doc.add_paragraph("1. Date despre program")
        h.style = doc.styles["Heading 1"]
        doc.add_paragraph("Universitatea Transilvania")
        h2 = doc.add_paragraph("2. Date despre disciplina")
        h2.style = doc.styles["Heading 1"]
        doc.add_paragraph("Analiza matematica")

    sections = extract_sections(_make_docx(build))

    assert [s.heading for s in sections] == [
        "1. Date despre program",
        "2. Date despre disciplina",
    ]
    assert isinstance(sections[0].body[0], TextBlock)
    assert sections[0].body[0].paragraphs == ["Universitatea Transilvania"]


def test_extracts_numbering_pattern_when_no_heading_style():
    def build(doc):
        doc.add_paragraph("8.1 Tematica activitatilor de curs")
        doc.add_paragraph("Curs 1: Limite de functii")

    sections = extract_sections(_make_docx(build))

    assert any(s.heading.startswith("8.1") for s in sections)
    sec = next(s for s in sections if s.heading.startswith("8.1"))
    assert sec.body[0].paragraphs == ["Curs 1: Limite de functii"]


def test_includes_tables_in_body():
    def build(doc):
        h = doc.add_paragraph("3. Timpul total estimat")
        h.style = doc.styles["Heading 1"]
        table = doc.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "Curs"
        table.rows[0].cells[1].text = "28"
        table.rows[1].cells[0].text = "Seminar"
        table.rows[1].cells[1].text = "14"

    sections = extract_sections(_make_docx(build))

    sec = sections[0]
    table_blocks = [b for b in sec.body if isinstance(b, TableBlock)]
    assert len(table_blocks) == 1
    assert table_blocks[0].rows == [["Curs", "28"], ["Seminar", "14"]]


def test_empty_doc_returns_single_preamble():
    def build(doc):
        doc.add_paragraph("Just a note")

    sections = extract_sections(_make_docx(build))

    assert len(sections) == 1
    assert sections[0].level == 0
    assert sections[0].body[0].paragraphs == ["Just a note"]


def test_normalised_heading_strips_diacritics_and_numbering():
    def build(doc):
        h = doc.add_paragraph("8.1 Tematica activităților de curs")
        h.style = doc.styles["Heading 2"]

    sec = extract_sections(_make_docx(build))[0]
    assert sec.heading_norm == "tematica activitatilor de curs"
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon
.\.venv\Scripts\python.exe -m pytest backend/tests/test_docx_section_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.services.docx_section_extractor'`.

---

## Task 4: Section extractor — implementation

**Files:**
- Create: [backend/services/docx_section_extractor.py](../../backend/services/docx_section_extractor.py)

- [ ] **Step 1: Implement the extractor**

```python
"""Walk a .docx and return ordered Section objects.

A Section is a heading + the paragraphs/tables that follow it until the
next heading. Headings are detected by Word style ("Heading*") OR by a
Romanian-FD numbering pattern at the start of a paragraph (e.g.
"8.1 Tematica activităților de curs").
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

_NUMBERING_RE = re.compile(r"^\s*\d+(\.\d+)*\s+\S")


@dataclass
class TextBlock:
    paragraphs: list[str]


@dataclass
class TableBlock:
    headers: list[str]
    rows: list[list[str]]


@dataclass
class Section:
    id: str
    heading: str
    heading_norm: str
    level: int
    position: int
    body: list[TextBlock | TableBlock] = field(default_factory=list)


def extract_sections(docx_bytes: bytes) -> list[Section]:
    doc = Document(io.BytesIO(docx_bytes))
    sections: list[Section] = []
    current: Section | None = None
    text_buffer: list[str] = []

    def flush_text() -> None:
        if text_buffer and current is not None:
            current.body.append(TextBlock(paragraphs=list(text_buffer)))
        text_buffer.clear()

    position = 0
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            heading_level = _heading_level(block)
            if heading_level is not None:
                flush_text()
                current = _new_section(block.text.strip(), heading_level, position)
                sections.append(current)
                position += 1
                continue

            if current is None:
                # Implicit preamble for content before the first heading.
                current = _new_section("", 0, position)
                sections.append(current)
                position += 1

            text_buffer.append(block.text)
        elif isinstance(block, Table):
            if current is None:
                current = _new_section("", 0, position)
                sections.append(current)
                position += 1
            flush_text()
            current.body.append(_table_to_block(block))

    flush_text()
    return sections


def _iter_block_items(parent: DocxDocument) -> Iterator[Paragraph | Table]:
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _heading_level(p: Paragraph) -> int | None:
    style = (p.style.name if p.style else "") or ""
    text = (p.text or "").strip()
    if style.startswith("Heading"):
        suffix = style.removeprefix("Heading").strip()
        try:
            return int(suffix) if suffix else 1
        except ValueError:
            return 1
    if text and _NUMBERING_RE.match(text) and len(text) <= 200:
        depth = text.split()[0].count(".") + 1
        return min(depth, 4)
    return None


def _new_section(heading: str, level: int, position: int) -> Section:
    norm = _normalise_heading(heading)
    sid = hashlib.sha1(f"{position}:{norm}".encode("utf-8")).hexdigest()[:12]
    return Section(id=sid, heading=heading, heading_norm=norm, level=level, position=position)


def _normalise_heading(heading: str) -> str:
    if not heading:
        return ""
    text = heading.strip()
    # Drop leading numbering ("8.1 ", "12. ").
    text = re.sub(r"^\s*\d+(\.\d+)*\s+", "", text)
    # Strip diacritics.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _table_to_block(table: Table) -> TableBlock:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    headers = rows[0] if rows else []
    body_rows = rows[1:] if len(rows) > 1 else []
    return TableBlock(headers=headers, rows=body_rows or rows)
```

- [ ] **Step 2: Run the tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_docx_section_extractor.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 3: Commit**

```powershell
git add backend/services/docx_section_extractor.py backend/tests/test_docx_section_extractor.py
git commit -m "feat(template-shift): docx section extractor with heading + numbering detection"
```

---

## Task 5: Section mapper — failing tests (deterministic pass)

**Files:**
- Create: [backend/tests/test_template_section_mapper.py](../../backend/tests/test_template_section_mapper.py)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for services.template_section_mapper."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services.docx_section_extractor import Section, TextBlock
from backend.services.template_section_mapper import (
    SectionMatch,
    map_sections,
)


def _sec(pos: int, heading: str, body: str = "") -> Section:
    from backend.services.docx_section_extractor import _new_section

    s = _new_section(heading, 1, pos)
    if body:
        s.body.append(TextBlock(paragraphs=[body]))
    return s


def test_exact_match():
    old = [_sec(0, "1. Date despre program")]
    new = [_sec(0, "1. Date despre program")]

    matches = map_sections(old, new, claude=None)

    assert matches[0].new_section_id == new[0].id
    assert matches[0].old_section_id == old[0].id
    assert matches[0].confidence == "exact"


def test_fuzzy_match_above_threshold():
    old = [_sec(0, "8.1 Tematica activitatilor de curs")]
    new = [_sec(0, "8.1 Tematica de la activitatile de curs")]

    matches = map_sections(old, new, claude=None)

    assert matches[0].old_section_id == old[0].id
    assert matches[0].confidence == "fuzzy"


def test_unmatched_when_no_claude_available():
    old = [_sec(0, "1. Date despre program")]
    new = [_sec(0, "X. Total alta tema")]

    matches = map_sections(old, new, claude=None)

    assert matches[0].old_section_id is None
    assert matches[0].confidence == "placeholder"


def test_llm_resolves_unmatched():
    old = [_sec(0, "8.1 Tematica activitatilor de curs", body="Curs 1")]
    new = [_sec(0, "Capitolul 8 — temele cursului", body="...")]

    fake = lambda payload: '[{"new_id": "%s", "old_id": "%s", "confidence": "high", "rationale": "renamed"}]' % (
        new[0].id,
        old[0].id,
    )

    matches = map_sections(old, new, claude=fake)

    assert matches[0].old_section_id == old[0].id
    assert matches[0].confidence == "llm-high"
    assert matches[0].rationale == "renamed"


def test_llm_failure_falls_back_to_placeholder():
    old = [_sec(0, "Some heading")]
    new = [_sec(0, "Completely different label")]

    def boom(_payload):
        raise RuntimeError("network down")

    matches = map_sections(old, new, claude=boom)

    assert matches[0].old_section_id is None
    assert matches[0].confidence == "placeholder"


def test_llm_malformed_json_falls_back_to_placeholder():
    old = [_sec(0, "Some heading")]
    new = [_sec(0, "Different label entirely")]

    matches = map_sections(old, new, claude=lambda _: "not json {")

    assert matches[0].confidence == "placeholder"
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_template_section_mapper.py -v
```

Expected: `ModuleNotFoundError`.

---

## Task 6: Section mapper — implementation

**Files:**
- Create: [backend/services/template_section_mapper.py](../../backend/services/template_section_mapper.py)

- [ ] **Step 1: Implement the mapper**

```python
"""Map sections from an old FD docx onto slots in a new template docx.

Pass 1 — deterministic exact + rapidfuzz token_sort_ratio (>= 88).
Pass 2 — single Claude call for any leftovers; failures fall back to
a placeholder confidence.

The Claude callable is injected so tests can stub it. In production the
router wires in a small wrapper around services.claude_service.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Literal

from rapidfuzz import fuzz

from backend.services.docx_section_extractor import Section

LOGGER = logging.getLogger(__name__)

FUZZY_THRESHOLD = 88
LLM_BATCH_CAP = 30

Confidence = Literal[
    "exact", "fuzzy", "llm-high", "llm-medium", "llm-low", "placeholder"
]


@dataclass
class SectionMatch:
    new_section_id: str
    old_section_id: str | None
    confidence: Confidence
    rationale: str | None = None


ClaudeCallable = Callable[[str], str]


def map_sections(
    old: list[Section],
    new: list[Section],
    claude: ClaudeCallable | None,
) -> list[SectionMatch]:
    matches: list[SectionMatch] = []
    used_old: set[str] = set()

    # Pass 1 — deterministic.
    unmatched_new: list[Section] = []
    for new_sec in new:
        match = _deterministic_match(new_sec, old, used_old)
        if match is None:
            unmatched_new.append(new_sec)
            matches.append(
                SectionMatch(
                    new_section_id=new_sec.id,
                    old_section_id=None,
                    confidence="placeholder",
                )
            )
        else:
            matches.append(match)

    # Pass 2 — Claude for the gaps (if any old sections remain unused).
    unmatched_old = [s for s in old if s.id not in used_old]
    if unmatched_new and unmatched_old and claude is not None:
        llm_matches = _llm_match(unmatched_new, unmatched_old, claude)
        # Overwrite the placeholder entries we just appended.
        by_new_id = {m.new_section_id: m for m in llm_matches}
        for i, existing in enumerate(matches):
            llm = by_new_id.get(existing.new_section_id)
            if llm is None or llm.old_section_id is None:
                continue
            if llm.old_section_id in used_old:
                continue
            used_old.add(llm.old_section_id)
            matches[i] = llm

    return matches


def _deterministic_match(
    new_sec: Section,
    old: list[Section],
    used_old: set[str],
) -> SectionMatch | None:
    target = new_sec.heading_norm
    if not target:
        return None

    # Exact.
    for old_sec in old:
        if old_sec.id in used_old:
            continue
        if old_sec.heading_norm and old_sec.heading_norm == target:
            used_old.add(old_sec.id)
            return SectionMatch(
                new_section_id=new_sec.id,
                old_section_id=old_sec.id,
                confidence="exact",
            )

    # Fuzzy.
    best_score = 0.0
    best_old: Section | None = None
    for old_sec in old:
        if old_sec.id in used_old or not old_sec.heading_norm:
            continue
        score = fuzz.token_sort_ratio(target, old_sec.heading_norm)
        if score > best_score:
            best_score = score
            best_old = old_sec
    if best_old is not None and best_score >= FUZZY_THRESHOLD:
        used_old.add(best_old.id)
        return SectionMatch(
            new_section_id=new_sec.id,
            old_section_id=best_old.id,
            confidence="fuzzy",
        )
    return None


def _llm_match(
    unmatched_new: list[Section],
    unmatched_old: list[Section],
    claude: ClaudeCallable,
) -> list[SectionMatch]:
    payload = _build_prompt(unmatched_new[:LLM_BATCH_CAP], unmatched_old[:LLM_BATCH_CAP])
    try:
        raw = claude(payload)
        decisions = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError, Exception) as exc:  # noqa: BLE001 — defensive
        LOGGER.warning("Template-shift LLM mapping failed: %s", exc)
        return []

    out: list[SectionMatch] = []
    for entry in decisions if isinstance(decisions, list) else []:
        if not isinstance(entry, dict):
            continue
        new_id = entry.get("new_id")
        old_id = entry.get("old_id")
        conf = entry.get("confidence", "low")
        rationale = entry.get("rationale")
        if not new_id:
            continue
        confidence: Confidence
        if old_id is None:
            confidence = "placeholder"
        else:
            confidence = {
                "high": "llm-high",
                "medium": "llm-medium",
                "low": "llm-low",
            }.get(str(conf).lower(), "llm-low")
        out.append(
            SectionMatch(
                new_section_id=str(new_id),
                old_section_id=str(old_id) if old_id else None,
                confidence=confidence,
                rationale=str(rationale) if rationale else None,
            )
        )
    return out


def _build_prompt(new_secs: list[Section], old_secs: list[Section]) -> str:
    def preview(sec: Section) -> str:
        for block in sec.body:
            paragraphs = getattr(block, "paragraphs", None)
            if paragraphs:
                joined = " ".join(paragraphs).strip()
                if joined:
                    return joined[:120]
        return ""

    new_listing = [
        {"id": s.id, "heading": s.heading, "preview": preview(s)} for s in new_secs
    ]
    old_listing = [
        {"id": s.id, "heading": s.heading, "preview": preview(s)} for s in old_secs
    ]

    return (
        "You are mapping sections from an old Romanian university course "
        "syllabus (Fișa Disciplinei) onto slots in a new template. For each "
        "NEW section, return either the OLD section that contains the same "
        "intellectual content or null if there is no equivalent. Reply with "
        "ONLY a JSON array, no prose.\n\n"
        "Required schema:\n"
        '[{"new_id": str, "old_id": str|null, "confidence": "high"|"medium"|"low", "rationale": str}]\n\n'
        f"NEW_SECTIONS = {json.dumps(new_listing, ensure_ascii=False)}\n\n"
        f"OLD_SECTIONS = {json.dumps(old_listing, ensure_ascii=False)}\n"
    )
```

- [ ] **Step 2: Run the tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_template_section_mapper.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```powershell
git add backend/services/template_section_mapper.py backend/tests/test_template_section_mapper.py
git commit -m "feat(template-shift): deterministic + Claude section mapper"
```

---

## Task 7: Refactor `fd_docx_renderer` — extract `apply_admin_fields`

**Files:**
- Modify: [backend/services/fd_docx_renderer.py](../../backend/services/fd_docx_renderer.py)

- [ ] **Step 1: Add a thin public wrapper**

Locate the body of [render_fd_docx](../../backend/services/fd_docx_renderer.py) where it calls `_fill_section_12_approvals(doc, plan_meta)`. Right above the existing `_fill_section_12_approvals` definition (around line 190), add:

```python
def apply_admin_fields(doc, plan_meta: dict) -> None:
    """Public entry point used by both the FD drafter and the Template Shifter.

    Currently delegates to the section-12 approvals filler; future admin
    fields (data avizării in section 1, programul_de_studii overrides) can
    layer on top here without touching call sites.
    """
    _fill_section_12_approvals(doc, plan_meta)
```

- [ ] **Step 2: Update the existing call site to use the wrapper**

Replace the existing line in `render_fd_docx`:

```python
    _fill_section_12_approvals(doc, plan_meta)
```

with:

```python
    apply_admin_fields(doc, plan_meta)
```

- [ ] **Step 3: Run the existing draft smoke test to confirm no regression**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v -k "draft or render or fd_docx"
```

Expected: existing tests still PASS (no behaviour change).

- [ ] **Step 4: Commit**

```powershell
git add backend/services/fd_docx_renderer.py
git commit -m "refactor(fd-docx-renderer): expose apply_admin_fields wrapper"
```

---

## Task 8: Template filler — failing test

**Files:**
- Create: [backend/tests/test_template_filler.py](../../backend/tests/test_template_filler.py)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for services.template_filler."""
from __future__ import annotations

import io

import pytest
from docx import Document

from backend.services.docx_section_extractor import extract_sections
from backend.services.template_filler import fill_template
from backend.services.template_section_mapper import SectionMatch


def _docx_from(builder) -> bytes:
    doc = Document()
    builder(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _two_section_template(label_a: str, label_b: str) -> bytes:
    def build(doc):
        a = doc.add_paragraph(label_a)
        a.style = doc.styles["Heading 1"]
        doc.add_paragraph("")  # body slot
        b = doc.add_paragraph(label_b)
        b.style = doc.styles["Heading 1"]
        doc.add_paragraph("")
    return _docx_from(build)


def _two_section_old(label_a: str, body_a: str, label_b: str, body_b: str) -> bytes:
    def build(doc):
        a = doc.add_paragraph(label_a)
        a.style = doc.styles["Heading 1"]
        doc.add_paragraph(body_a)
        b = doc.add_paragraph(label_b)
        b.style = doc.styles["Heading 1"]
        doc.add_paragraph(body_b)
    return _docx_from(build)


def test_fill_template_carries_matched_body():
    template = _two_section_template("1. Date despre program", "2. Date despre disciplina")
    old = _two_section_old(
        "1. Date despre program", "Universitatea Transilvania",
        "2. Date despre disciplina", "Analiza matematica I",
    )
    old_sections = extract_sections(old)
    new_sections = extract_sections(template)

    matches = [
        SectionMatch(new_section_id=new_sections[0].id, old_section_id=old_sections[0].id, confidence="exact"),
        SectionMatch(new_section_id=new_sections[1].id, old_section_id=old_sections[1].id, confidence="exact"),
    ]

    out_bytes = fill_template(template, old_sections, new_sections, matches, plan_meta={})

    out = Document(io.BytesIO(out_bytes))
    text = "\n".join(p.text for p in out.paragraphs)
    assert "Universitatea Transilvania" in text
    assert "Analiza matematica I" in text


def test_fill_template_inserts_red_placeholder_when_unmatched():
    template = _two_section_template("1. Date despre program", "9. Sectiune noua")
    old = _two_section_old(
        "1. Date despre program", "Universitatea Transilvania",
        "8. Tematica", "Curs 1",
    )
    old_sections = extract_sections(old)
    new_sections = extract_sections(template)

    matches = [
        SectionMatch(new_section_id=new_sections[0].id, old_section_id=old_sections[0].id, confidence="exact"),
        SectionMatch(new_section_id=new_sections[1].id, old_section_id=None, confidence="placeholder"),
    ]

    out_bytes = fill_template(template, old_sections, new_sections, matches, plan_meta={})

    out = Document(io.BytesIO(out_bytes))
    placeholder = next(
        p for p in out.paragraphs if "Vă rugăm completați" in p.text
    )
    red_runs = [r for r in placeholder.runs if r.font.color and r.font.color.rgb is not None]
    assert red_runs, "placeholder paragraph must have a coloured run"
    assert str(red_runs[0].font.color.rgb).upper() == "FF0000"
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_template_filler.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.services.template_filler'`.

---

## Task 9: Template filler — implementation

**Files:**
- Create: [backend/services/template_filler.py](../../backend/services/template_filler.py)

- [ ] **Step 1: Implement the filler**

```python
"""Render a new-template .docx populated with content from the old FD."""
from __future__ import annotations

import io
from typing import Iterator

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

from backend.services.docx_section_extractor import (
    Section,
    TableBlock,
    TextBlock,
    _heading_level,
)
from backend.services.fd_docx_renderer import apply_admin_fields
from backend.services.template_section_mapper import SectionMatch

PLACEHOLDER_TEXT = "Vă rugăm completați aici conform noului format."


def fill_template(
    template_bytes: bytes,
    old_sections: list[Section],
    new_sections: list[Section],
    matches: list[SectionMatch],
    plan_meta: dict,
) -> bytes:
    """Return the bytes of the filled new-template docx."""
    doc = Document(io.BytesIO(template_bytes))

    old_by_id = {s.id: s for s in old_sections}
    matches_by_new_id = {m.new_section_id: m for m in matches}

    body = doc.element.body
    children = list(body.iterchildren())
    # Walk the body, find each heading paragraph, replace the slot until the next heading.
    new_idx = 0
    i = 0
    while i < len(children):
        child = children[i]
        if child.tag != qn("w:p"):
            i += 1
            continue
        para = Paragraph(child, doc)
        if _heading_level(para) is None:
            i += 1
            continue
        # End of slot = index of next heading (or end of body).
        j = i + 1
        while j < len(children):
            nxt = children[j]
            if nxt.tag == qn("w:p") and _heading_level(Paragraph(nxt, doc)) is not None:
                break
            j += 1

        if new_idx < len(new_sections):
            new_sec = new_sections[new_idx]
            match = matches_by_new_id.get(new_sec.id)
            old_sec = old_by_id.get(match.old_section_id) if match and match.old_section_id else None

            # Remove existing slot content (keep the heading paragraph at index i).
            for stale in children[i + 1 : j]:
                body.remove(stale)
            # Insert replacement content before the next heading (or at end).
            anchor_index = i + 1  # next position after heading
            anchor = children[j] if j < len(children) else None
            if old_sec is not None:
                _append_section_body(doc, anchor, old_sec)
            else:
                _append_placeholder(doc, anchor)

            # Refresh children list because we mutated the tree.
            children = list(body.iterchildren())
            # Advance i past the (possibly different number of) inserted blocks.
            # Find the index of the next heading by re-scanning.
            i = _index_of_next_heading(children, doc, start=i + 1)
            new_idx += 1
        else:
            i += 1

    apply_admin_fields(doc, plan_meta or {})

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _append_section_body(doc: DocxDocument, anchor, section: Section) -> None:
    for block in section.body:
        if isinstance(block, TextBlock):
            for text in block.paragraphs:
                p = doc.add_paragraph(text)
                if anchor is not None:
                    anchor.addprevious(p._p)
        elif isinstance(block, TableBlock):
            cols = max((len(r) for r in block.rows), default=1)
            t = doc.add_table(rows=len(block.rows) or 1, cols=cols)
            for r_idx, row in enumerate(block.rows):
                for c_idx, cell in enumerate(row):
                    if c_idx < cols:
                        t.rows[r_idx].cells[c_idx].text = cell
            if anchor is not None:
                anchor.addprevious(t._tbl)


def _append_placeholder(doc: DocxDocument, anchor) -> None:
    p = doc.add_paragraph()
    run = p.add_run(PLACEHOLDER_TEXT)
    run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)
    if anchor is not None:
        anchor.addprevious(p._p)


def _index_of_next_heading(children: list, doc: DocxDocument, start: int) -> int:
    for k in range(start, len(children)):
        c = children[k]
        if c.tag == qn("w:p") and _heading_level(Paragraph(c, doc)) is not None:
            return k
    return len(children)
```

- [ ] **Step 2: Run the tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_template_filler.py -v
```

Expected: both tests PASS.

- [ ] **Step 3: Commit**

```powershell
git add backend/services/template_filler.py backend/tests/test_template_filler.py
git commit -m "feat(template-shift): docx filler with placeholder + admin-fill reuse"
```

---

## Task 10: API endpoint — failing test

**Files:**
- Create: [backend/tests/test_shift_template_api.py](../../backend/tests/test_shift_template_api.py)

- [ ] **Step 1: Write the failing test**

```python
"""Integration test for POST /api/documents/shift-template."""
from __future__ import annotations

import base64
import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.main import app


def _docx_bytes(headings_with_body: list[tuple[str, str]]) -> bytes:
    doc = Document()
    for heading, body in headings_with_body:
        h = doc.add_paragraph(heading)
        h.style = doc.styles["Heading 1"]
        doc.add_paragraph(body)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_shift_template_round_trips_docx_and_report(monkeypatch):
    # Force the deterministic path — no Claude needed for identical headings.
    client = TestClient(app)

    old = _docx_bytes([
        ("1. Date despre program", "Universitatea Transilvania"),
        ("8. Tematica", "Curs 1: Limite"),
    ])
    template = _docx_bytes([
        ("1. Date despre program", ""),
        ("8. Tematica", ""),
    ])

    response = client.post(
        "/api/documents/shift-template",
        files={
            "old_fd": ("old.docx", old, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "new_template": ("tpl.docx", template, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    raw_report = response.headers["x-shift-report"]
    report = json.loads(base64.b64decode(raw_report).decode("utf-8"))
    assert report["llm_used"] is False
    assert any(m["confidence"] == "exact" for m in report["matches"])

    out = Document(io.BytesIO(response.content))
    text = "\n".join(p.text for p in out.paragraphs)
    assert "Universitatea Transilvania" in text
    assert "Curs 1: Limite" in text


def test_shift_template_rejects_invalid_docx():
    client = TestClient(app)
    response = client.post(
        "/api/documents/shift-template",
        files={
            "old_fd": ("old.docx", b"not a docx", "application/octet-stream"),
            "new_template": ("tpl.docx", b"also not a docx", "application/octet-stream"),
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_shift_template_api.py -v
```

Expected: 404 (endpoint not registered yet).

---

## Task 11: API endpoint — implementation

**Files:**
- Modify: [backend/routers/documents.py](../../backend/routers/documents.py)
- Modify: [backend/main.py](../../backend/main.py)

- [ ] **Step 1: Expose the report header through CORS**

Replace the CORS middleware block in [backend/main.py](../../backend/main.py):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Shift-Report"],
)
```

- [ ] **Step 2: Add new imports to `routers/documents.py`**

Near the other `services.*` imports add:

```python
import base64
import json

from services.docx_section_extractor import extract_sections
from services.template_filler import fill_template
from services.template_section_mapper import map_sections
from schemas.template_shift import (
    AdminUpdateReport,
    SectionMatchReport,
    ShiftReport,
)
```

- [ ] **Step 3: Add the endpoint at the bottom of `routers/documents.py`**

```python
@router.post("/shift-template")
async def shift_template_endpoint(
    old_fd: UploadFile = File(...),
    new_template: UploadFile = File(...),
    plan: UploadFile | None = File(None),
) -> StreamingResponse:
    old_bytes = await old_fd.read()
    new_bytes = await new_template.read()

    try:
        old_sections = extract_sections(old_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid old FD docx: {exc}") from exc
    try:
        new_sections = extract_sections(new_bytes)
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

    def claude_call(prompt: str) -> str:
        return claude_service.complete(prompt)

    claude_callable = claude_call if claude_service.is_configured() else None
    matches = map_sections(old_sections, new_sections, claude=claude_callable)

    filled_bytes = fill_template(
        template_bytes=new_bytes,
        old_sections=old_sections,
        new_sections=new_sections,
        matches=matches,
        plan_meta=plan_meta,
    )

    report = _build_shift_report(old_sections, new_sections, matches, plan_meta, claude_callable is not None)
    encoded = base64.b64encode(json.dumps(report.model_dump(), ensure_ascii=False).encode("utf-8")).decode("ascii")

    headers = {
        "Content-Disposition": 'attachment; filename="fisa_disciplinei_migrated.docx"',
        "X-Shift-Report": encoded,
    }
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


def _build_shift_report(old_sections, new_sections, matches, plan_meta, llm_used: bool) -> ShiftReport:
    new_by_id = {s.id: s for s in new_sections}
    old_by_id = {s.id: s for s in old_sections}

    match_reports = []
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

    admin_updates = [
        AdminUpdateReport(field=k, value=str(v))
        for k, v in (plan_meta or {}).items()
        if k in {
            "decanul_facultatii",
            "directorul_de_departament",
            "programul_de_studii",
            "facultatea",
            "domeniul_de_licenta",
            "coordonator_program_studii",
            "rector",
        }
        and v
    ]

    return ShiftReport(
        matches=match_reports,
        admin_updates=admin_updates,
        placeholders=placeholders,
        llm_used=llm_used and any(m.confidence.startswith("llm-") for m in matches),
    )
```

- [ ] **Step 4: Add the missing top-level `import io` to documents.py if not present**

If `import io` is not already among the imports at the top of [backend/routers/documents.py](../../backend/routers/documents.py), add it.

- [ ] **Step 5: Make sure `claude_service` exposes `is_configured` and `complete`**

Open [backend/services/claude_service.py](../../backend/services/claude_service.py) and verify a function `complete(prompt: str) -> str` and `is_configured() -> bool` exist. If they do not, add minimal wrappers around the existing Claude client (e.g. delegate to the same call path used by `template_validator`/`competency_mapper`). If unsure, run:

```powershell
.\.venv\Scripts\python.exe -c "from backend.services import claude_service; print([n for n in dir(claude_service) if not n.startswith('_')])"
```

Pick existing function names that match the responsibilities, and wire them into the `claude_callable` block above instead of `complete`/`is_configured`.

- [ ] **Step 6: Run the API tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_shift_template_api.py -v
```

Expected: both tests PASS.

- [ ] **Step 7: Run the full backend test suite to confirm no regression**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add backend/main.py backend/routers/documents.py backend/tests/test_shift_template_api.py
git commit -m "feat(template-shift): POST /shift-template endpoint with X-Shift-Report header"
```

---

## Task 12: Frontend — models + service

**Files:**
- Create: `frontend-hackathon/src/app/template-shift/models/template-shift.models.ts`
- Create: `frontend-hackathon/src/app/template-shift/services/template-shift.service.ts`

- [ ] **Step 1: Create the models file**

```typescript
export type ShiftConfidence =
  | 'exact'
  | 'fuzzy'
  | 'llm-high'
  | 'llm-medium'
  | 'llm-low'
  | 'placeholder';

export interface SectionMatchReport {
  new_heading: string;
  old_heading: string | null;
  confidence: ShiftConfidence;
  rationale?: string | null;
}

export interface AdminUpdateReport {
  field: string;
  value: string;
}

export interface ShiftReport {
  matches: SectionMatchReport[];
  admin_updates: AdminUpdateReport[];
  placeholders: string[];
  llm_used: boolean;
}

export interface ShiftResult {
  blob: Blob;
  report: ShiftReport;
  filename: string;
}
```

- [ ] **Step 2: Create the service**

```typescript
import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { ShiftReport, ShiftResult } from '../models/template-shift.models';

@Injectable({ providedIn: 'root' })
export class TemplateShiftService {
  private readonly http = inject(HttpClient);

  migrate(oldFd: File, template: File, plan: File | null): Observable<ShiftResult> {
    const form = new FormData();
    form.append('old_fd', oldFd, oldFd.name);
    form.append('new_template', template, template.name);
    if (plan) {
      form.append('plan', plan, plan.name);
    }

    return this.http
      .post('/api/documents/shift-template', form, {
        observe: 'response',
        responseType: 'blob',
      })
      .pipe(
        map((response: HttpResponse<Blob>) => {
          const headerValue = response.headers.get('X-Shift-Report') ?? '';
          const report = decodeReport(headerValue);
          return {
            blob: response.body ?? new Blob(),
            report,
            filename: 'fisa_disciplinei_migrated.docx',
          };
        }),
      );
  }
}

function decodeReport(headerValue: string): ShiftReport {
  if (!headerValue) {
    return { matches: [], admin_updates: [], placeholders: [], llm_used: false };
  }
  const json = atob(headerValue);
  return JSON.parse(decodeURIComponent(escape(json))) as ShiftReport;
}
```

- [ ] **Step 3: Commit**

```powershell
git add frontend-hackathon/src/app/template-shift/models frontend-hackathon/src/app/template-shift/services
git commit -m "feat(template-shift): angular models + service for /shift-template"
```

---

## Task 13: Frontend — page component

**Files:**
- Create: `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.ts`
- Create: `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.html`
- Create: `frontend-hackathon/src/app/template-shift/template-shift-page/template-shift-page.component.scss`

- [ ] **Step 1: Create the component TypeScript**

```typescript
import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { ShiftReport } from '../models/template-shift.models';
import { TemplateShiftService } from '../services/template-shift.service';

@Component({
  selector: 'app-template-shift-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './template-shift-page.component.html',
  styleUrls: ['./template-shift-page.component.scss'],
})
export class TemplateShiftPageComponent {
  private readonly service = inject(TemplateShiftService);

  readonly oldFd = signal<File | null>(null);
  readonly template = signal<File | null>(null);
  readonly plan = signal<File | null>(null);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly report = signal<ShiftReport | null>(null);
  readonly downloadUrl = signal<string | null>(null);
  readonly downloadName = signal<string>('fisa_disciplinei_migrated.docx');

  pickFile(target: 'oldFd' | 'template' | 'plan', event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    if (target === 'oldFd') this.oldFd.set(file);
    if (target === 'template') this.template.set(file);
    if (target === 'plan') this.plan.set(file);
  }

  canMigrate(): boolean {
    return !!this.oldFd() && !!this.template() && !this.loading();
  }

  migrate(): void {
    const oldFd = this.oldFd();
    const template = this.template();
    if (!oldFd || !template) return;

    this.loading.set(true);
    this.errorMessage.set(null);
    this.report.set(null);
    const previous = this.downloadUrl();
    if (previous) URL.revokeObjectURL(previous);
    this.downloadUrl.set(null);

    this.service.migrate(oldFd, template, this.plan()).subscribe({
      next: (result) => {
        this.report.set(result.report);
        this.downloadName.set(result.filename);
        this.downloadUrl.set(URL.createObjectURL(result.blob));
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? err?.message ?? 'Migration failed');
        this.loading.set(false);
      },
    });
  }

  groupedMatches(): { label: string; entries: ShiftReport['matches'] }[] {
    const r = this.report();
    if (!r) return [];
    const groups: Record<string, ShiftReport['matches']> = {
      'Exact': [], 'Fuzzy': [], 'LLM': [], 'Placeholder': [],
    };
    for (const m of r.matches) {
      if (m.confidence === 'exact') groups['Exact'].push(m);
      else if (m.confidence === 'fuzzy') groups['Fuzzy'].push(m);
      else if (m.confidence.startsWith('llm-')) groups['LLM'].push(m);
      else groups['Placeholder'].push(m);
    }
    return Object.entries(groups)
      .filter(([, v]) => v.length > 0)
      .map(([label, entries]) => ({ label, entries }));
  }
}
```

- [ ] **Step 2: Create the template HTML**

```html
<section class="template-shift">
  <header>
    <h2>🔄 Template Shifter</h2>
    <p>Migrate an old Fișa Disciplinei into the structure of a new template.</p>
  </header>

  <div class="uploaders">
    <label>
      <span>Old FD (.docx)</span>
      <input type="file" accept=".docx" (change)="pickFile('oldFd', $event)" />
    </label>
    <label>
      <span>New template (.docx)</span>
      <input type="file" accept=".docx" (change)="pickFile('template', $event)" />
    </label>
    <label>
      <span>Plan de Învățământ (.pdf, optional)</span>
      <input type="file" accept=".pdf" (change)="pickFile('plan', $event)" />
    </label>
  </div>

  <button type="button" [disabled]="!canMigrate()" (click)="migrate()">
    {{ loading() ? 'Migrating…' : 'Migrate' }}
  </button>

  <p class="error" *ngIf="errorMessage() as msg">{{ msg }}</p>

  <ng-container *ngIf="report() as r">
    <div class="download" *ngIf="downloadUrl() as url">
      <a [href]="url" [download]="downloadName()">⬇ Download migrated FD</a>
    </div>

    <section class="results">
      <h3>Mapping report</h3>
      <p class="meta">LLM used: {{ r.llm_used ? 'yes' : 'no' }}</p>
      <div class="group" *ngFor="let group of groupedMatches()">
        <h4>{{ group.label }} ({{ group.entries.length }})</h4>
        <ul>
          <li *ngFor="let m of group.entries">
            <strong>{{ m.new_heading }}</strong>
            <ng-container *ngIf="m.old_heading"> ← {{ m.old_heading }}</ng-container>
            <em *ngIf="m.rationale"> — {{ m.rationale }}</em>
          </li>
        </ul>
      </div>
      <div class="group" *ngIf="r.admin_updates.length">
        <h4>Admin auto-fill ({{ r.admin_updates.length }})</h4>
        <ul>
          <li *ngFor="let u of r.admin_updates"><strong>{{ u.field }}:</strong> {{ u.value }}</li>
        </ul>
      </div>
    </section>
  </ng-container>
</section>
```

- [ ] **Step 3: Create the SCSS**

```scss
.template-shift {
  max-width: 960px;
  margin: 2rem auto;
  padding: 1.5rem;
  font-family: system-ui, sans-serif;

  header h2 { margin-bottom: 0.25rem; }
  header p { color: #555; margin-top: 0; }

  .uploaders {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;

    label {
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      padding: 0.75rem;
      border: 1px dashed #b8c4d4;
      border-radius: 6px;
      background: #f9fbfd;
      span { font-weight: 600; }
    }
  }

  button {
    padding: 0.6rem 1.2rem;
    border-radius: 6px;
    border: 0;
    background: #1f6feb;
    color: white;
    font-weight: 600;
    cursor: pointer;
    &:disabled { opacity: 0.5; cursor: not-allowed; }
  }

  .error { color: #b91c1c; margin-top: 1rem; }

  .download { margin: 1.25rem 0; }
  .download a {
    display: inline-block;
    padding: 0.5rem 1rem;
    background: #16a34a;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-weight: 600;
  }

  .results { margin-top: 1.5rem; }
  .results .meta { color: #666; }
  .results .group { margin-top: 1rem; }
  .results .group h4 { margin-bottom: 0.4rem; }
  .results .group ul { margin: 0; padding-left: 1.25rem; }
  .results .group li { margin: 0.2rem 0; }
}
```

- [ ] **Step 4: Build the frontend to confirm no compilation errors**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon\frontend-hackathon
npx ng build --configuration development
```

Expected: build succeeds; the new files compile.

- [ ] **Step 5: Commit**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon
git add frontend-hackathon/src/app/template-shift
git commit -m "feat(template-shift): angular page with three uploaders + report panel"
```

---

## Task 14: Wire route and nav

**Files:**
- Modify: `frontend-hackathon/src/app/app.routes.ts`
- Modify: `frontend-hackathon/src/app/shared/nav/nav.component.html`

- [ ] **Step 1: Add the lazy route**

In `app.routes.ts`, add a new entry directly after the `draft` route and before the wildcard:

```typescript
  {
    path: 'template-shift',
    loadComponent: () =>
      import('./template-shift/template-shift-page/template-shift-page.component').then(
        (m) => m.TemplateShiftPageComponent,
      ),
  },
```

- [ ] **Step 2: Add the nav link**

In `nav.component.html`, add a new `<li>` after the `📝 FD Drafter` item:

```html
      <li>
        <a routerLink="/template-shift" routerLinkActive="active">
          🔄 Template Shifter
        </a>
      </li>
```

- [ ] **Step 3: Build the frontend again**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon\frontend-hackathon
npx ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon
git add frontend-hackathon/src/app/app.routes.ts frontend-hackathon/src/app/shared/nav/nav.component.html
git commit -m "feat(template-shift): wire /template-shift route + nav entry"
```

---

## Task 15: End-to-end smoke test

**Files:**
- No file changes; validation only.

- [ ] **Step 1: Start the backend**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --app-dir D:\dev\repos\hackhathoooooon\Hackathon\backend
```

- [ ] **Step 2: Start the frontend (new terminal)**

```powershell
cd d:\dev\repos\hackhathoooooon\Hackathon\frontend-hackathon
npx ng serve --port 4200 --host 127.0.0.1
```

- [ ] **Step 3: Manual smoke**

Open `http://127.0.0.1:4200/template-shift`, upload an old FD docx + the new template docx (and optionally a Plan PDF), click **Migrate**. Verify:
- A `.docx` download appears.
- Mapping report panel shows at least one Exact/Fuzzy/LLM/Placeholder group.
- Opening the downloaded file in Word: matched sections carry old-FD content; unmatched sections show the red Romanian placeholder; if a Plan was uploaded, section 12 shows Decan + Director departament.

- [ ] **Step 4: Final regression run**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit a short release note (only if anything was tweaked during smoke)**

If you adjusted any code during smoke, commit it now. Otherwise skip.

---

## Self-Review (post-write)

- **Spec coverage:** All five spec sections (User flow, Architecture, Backend modules, Frontend module, Error handling, Testing) map to tasks 1–15. ShiftReport schema (Task 2) ↔ spec §"schemas/template_shift.py". docx_section_extractor (Task 4) ↔ spec §"services/docx_section_extractor.py". template_section_mapper deterministic + Claude (Tasks 5–6) ↔ spec §"Pass 1 / Pass 2". template_filler with placeholder + admin reuse (Tasks 7–9) ↔ spec §"services/template_filler.py" and §"admin-fill pass". Endpoint + CORS expose-headers (Tasks 10–11) ↔ spec §"routers/documents.py" and §"Response shape". Frontend page mirrors `draft/`/`sync-check/` (Tasks 12–14). Smoke (Task 15) ↔ DoD.
- **Placeholder scan:** No "TBD"/"implement later"/"add error handling later" lines. Every code step is self-contained.
- **Type consistency:** `Section`, `TextBlock`, `TableBlock`, `SectionMatch`, `ShiftReport`, `SectionMatchReport`, `AdminUpdateReport` names are stable across tasks. The `apply_admin_fields` helper added in Task 7 is consumed by Task 9. The `claude` keyword argument on `map_sections` is consistent across Tasks 5/6/11.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-25-template-shifter.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

Which approach?
