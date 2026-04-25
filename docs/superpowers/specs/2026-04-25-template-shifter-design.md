# UC 4 — Template Shifter (MVP)

**Status:** Design approved 2026-04-25
**Scope:** Hackathon MVP (Scope B in brainstorm)
**Spec source:** Hackathon "Catalog Use Cases" — Nivel 4 „The Template Shifter"

## Goal

Given an old `.docx` Fișă a Disciplinei (FD) and a new `.docx` template
(`Template_FD_2026.docx`), produce a filled new-template `.docx` that
preserves the intellectual content from the old FD while conforming to the
new structure. Optionally accept a Plan de Învățământ PDF for silent
admin-field updates (Decan, Director departament, an universitar, credite).

## Out of scope (MVP)

- Logic-change adaptation (e.g. splitting lab hours per theme when the new
  template demands finer granularity). Handled by a future Scope-C iteration.
- "Review & Apply" UI showing each mapping decision with override controls.
  Future Scope-D iteration; backend will already emit a structured report
  that a future UI can consume.
- Bulk migration across N FDs in one shot. Overlaps with UC 3.2 Smart Updater.
- Template authoring with explicit `{{token}}` markers. Hybrid path supports
  it if present, but we don't ship templates with tokens.

## User flow

1. User opens **🔄 Template Shifter** page from the nav.
2. Uploads three files:
   - **Old FD** (`.docx`) — required
   - **New template** (`.docx`) — required
   - **Plan de Învățământ** (`.pdf`) — optional, enables admin auto-fill
3. Clicks **Migrate**.
4. Backend returns the filled `.docx` plus a JSON `ShiftReport`.
5. Page shows a per-section results panel (matched / admin-filled / placeholder)
   and a download button for the migrated file.

## Architecture

```
┌────────────────────────────────────────────────────────┐
│ POST /api/documents/shift-template                     │
│  multipart: old_fd.docx, new_template.docx, plan?.pdf  │
└────────────────────┬───────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 docx_section_extractor    pi_fast_parser (existing)
        │                         │
        ▼                         ▼
   old_blocks[]              plan_meta{}
        │                         │
        └─────────┬───────────────┘
                  ▼
         template_section_mapper
         (deterministic + Claude)
                  ▼
             mapping{}
                  ▼
         template_filler
         (python-docx)
                  ▼
   filled.docx (body) + ShiftReport (X-Shift-Report header)
```

### Response shape

Single endpoint returns `StreamingResponse` with the filled `.docx`. The
`ShiftReport` JSON is base64-encoded and placed in the `X-Shift-Report`
response header. This matches the existing pattern of `/draft-fd-docx` and
keeps the front-end to a single round-trip. CORS exposes the header.

## Backend modules

### `services/docx_section_extractor.py`

Walks a `.docx` with `python-docx` and returns an ordered list of
`Section` objects.

```python
@dataclass
class TextBlock:
    paragraphs: list[str]   # one entry per paragraph, empty string preserves blanks

@dataclass
class TableBlock:
    headers: list[str]
    rows: list[list[str]]

@dataclass
class Section:
    id: str                 # stable hash of (heading + position)
    heading: str            # raw heading text (e.g. "8.1 Tematica activităților de curs")
    heading_norm: str       # lowercase + diacritic-stripped + numbering-stripped
    level: int              # 1, 2, 3 based on style or numbering depth
    body: list[TextBlock | TableBlock]
    position: int           # original document order
```

Section boundaries:
- Any paragraph whose style name starts with `Heading` (Word built-in).
- Any paragraph whose text matches `^\d+(\.\d+)*\s+\S` (Romanian FD numbering).
- The first non-heading paragraph of the document is wrapped in an implicit
  "preamble" section with `level=0`.

Pure, deterministic, no I/O beyond reading the bytes. No Claude.

### `services/template_section_mapper.py`

Two-pass mapping.

**Pass 1 — deterministic.**
1. Build canonical key for each heading: lowercase, strip diacritics,
   collapse whitespace, drop leading section numbers.
2. Exact key match → confidence `exact`.
3. Else `rapidfuzz.fuzz.token_sort_ratio(a, b) >= 88` → confidence `fuzzy`.
4. Else mark `unmatched`.

**Pass 2 — LLM (one round-trip).**
- Inputs: list of unmatched new-template headings + list of unmatched
  old-FD headings (each with first ~120 chars of body for context).
- Cap each side at 30; batch if larger.
- Prompt asks Claude to return a JSON array
  `[{"new_id": str, "old_id": str|null, "confidence": "high|medium|low", "rationale": str}]`.
- `null` means no equivalent exists in the old FD → renderer will insert a
  red placeholder.
- Malformed JSON or HTTP failure → log, treat all unmatched as placeholders.

**Output:**

```python
@dataclass
class SectionMatch:
    new_section_id: str
    old_section_id: str | None
    confidence: Literal["exact", "fuzzy", "llm-high", "llm-medium", "llm-low", "placeholder"]
    rationale: str | None
```

### `services/template_filler.py`

Walks the new template `.docx` (loaded fresh from the uploaded bytes) and,
for each detected section slot:

- If `match.old_section_id` is set: replace the slot's body with the
  old-FD section's body blocks. Tables map cell-by-cell when shapes match;
  otherwise the old table is appended in full and the new template's empty
  table left as-is with a placeholder note.
- If `match.old_section_id` is None: insert a single red paragraph
  `Vă rugăm completați aici conform noului format.` (run color = `FF0000`).

After all section slots are filled, run the **admin-fill pass**:
- Reuse `pi_fast_parser` output (when Plan was uploaded) to override
  canonical fields in section 1 ("Date despre program") and section 12
  ("Aprobări"): `decanul_facultatii`, `directorul_de_departament`,
  `programul_de_studii`, `facultatea`, `domeniul_de_licenta`,
  `coordonator_program_studii`. Today's date is written for "data avizării".
- Refactor the relevant parts of `fd_docx_renderer._fill_section_12_approvals`
  into a shared helper consumed by both `fd_docx_renderer` and
  `template_filler`. No behavior change for the existing `/draft-fd-docx`.

### `routers/documents.py`

One new endpoint:

```python
@router.post("/shift-template")
async def shift_template_endpoint(
    old_fd: UploadFile = File(...),
    new_template: UploadFile = File(...),
    plan: UploadFile | None = File(None),
) -> StreamingResponse: ...
```

Returns the filled `.docx`. `X-Shift-Report` header carries
`base64(json.dumps(ShiftReport.model_dump()))`. CORS configuration adds
`X-Shift-Report` to `expose_headers`.

### `schemas/template_shift.py`

```python
class SectionMatchReport(BaseModel):
    new_heading: str
    old_heading: str | None
    confidence: Literal["exact", "fuzzy", "llm-high", "llm-medium", "llm-low", "placeholder"]
    rationale: str | None = None

class AdminUpdateReport(BaseModel):
    field: str          # e.g. "decanul_facultatii"
    value: str

class ShiftReport(BaseModel):
    matches: list[SectionMatchReport]
    admin_updates: list[AdminUpdateReport]
    placeholders: list[str]   # heading texts left blank
    llm_used: bool
```

## Frontend module

`frontend-hackathon/src/app/template-shift/` mirroring `draft/`:

- `template-shift-page/template-shift-page.component.{ts,html,scss}` — three
  uploaders, "Migrate" button, status signals, results panel grouped by
  match confidence (✅ exact / 🟡 fuzzy / 🤖 LLM / 🚧 placeholder).
- `services/template-shift.service.ts` — `migrate(oldFd, newTpl, plan?)`
  returns `{ blob, report }`. Reads `X-Shift-Report` from the response,
  base64-decodes, parses JSON.
- `models/template-shift.models.ts` — TypeScript mirror of `ShiftReport`.
- Add route `/template-shift` to `app.routes.ts`.
- Add nav entry "🔄 Template Shifter" to `nav.component.html`.

## Error handling & graceful degradation

| Condition | Behaviour |
|---|---|
| `old_fd` not a valid `.docx` | 422 `"Invalid old FD docx"` |
| `new_template` not a valid `.docx` | 422 `"Invalid template docx"` |
| `plan` provided but parser returns None | Skip admin-fill, log warning, continue. |
| Section extractor finds zero sections in either file | 422 `"No sections detected; check headings"` |
| Claude call fails / times out / returns malformed JSON | Skip LLM pass, mark all unmatched as placeholder, set `report.llm_used = false` |
| Filler fails on a single section | Insert placeholder for that section only, continue |

## Testing

### Unit tests

- `tests/test_docx_section_extractor.py`
  - Headings via `Heading 1`/`Heading 2` styles.
  - Headings via numbering pattern (`8.1 Tematica…`).
  - Mixed paragraphs + tables in body.
  - Empty document → returns single preamble.
- `tests/test_template_section_mapper.py`
  - Exact, fuzzy, and unmatched cases (deterministic only, Claude mocked out).
  - LLM path: mock Claude to return a known JSON list, assert mapping.
  - LLM path: mock Claude to raise → assert all unmatched become placeholder
    and `llm_used == False`.
- `tests/test_template_filler.py`
  - Golden-file: synthetic `old.docx` + `template.docx` → filled `.docx`
    inspected with `python-docx`, assert specific paragraphs/tables.
  - Placeholder insertion has red font run.
- `tests/test_shift_template_api.py`
  - Multipart POST with the three files; mock Claude.
  - Assert response is `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
  - Assert `X-Shift-Report` header decodes to a valid `ShiftReport`.

### Frontend

- Light smoke on `template-shift.service.ts`: build a fake response with
  `X-Shift-Report` header, assert the service decodes it.

### Manual smoke

End-to-end with the existing `FD_RO_IA_I.pdf` (converted to docx via
the `pdf_to_docx.py` helper if needed) + a hand-edited "new template"
docx that renames a couple of section headings.

## Dependencies

Already in `backend/requirements.txt`:
- `python-docx`
- `pdfplumber` (for the optional Plan path)
- `httpx` / `anthropic` (Claude)

New addition: `rapidfuzz` for the fuzzy heading matcher (small, pure-Python
fallback).

## Risks & open questions

- **Heading detection in real faculty templates.** Some `.docx` files use
  manual bold paragraphs instead of Word heading styles. The numbering
  regex covers the common FD shape (`1. … 12.`) but if a template uses
  unnumbered bold-only headings, extraction quality drops. Mitigation:
  treat any all-bold paragraph shorter than 80 chars as a candidate
  heading at level 2; behind a feature flag if it causes false positives.
- **Table shape mismatches.** When the old FD's "Tematica" table has 3
  columns and the new template's has 4, the filler defers to "append old
  table verbatim and leave new table empty with a note". Acceptable for
  MVP; a future iteration can do per-cell semantic mapping.
- **Claude latency on the LLM pass.** A single batched call with
  ≤30 unmatched sections per side typically returns in <8s; the existing
  `validateTimeoutMs = 60s` on the frontend is safe.
- **Localization of placeholder text.** Hardcoded Romanian for now;
  matches the rest of the app.

## Definition of done

- `POST /api/documents/shift-template` returns a valid filled `.docx`
  for the smoke test inputs in <30s end-to-end (including LLM call).
- Section 1 (Date despre program) shows the correct programul_de_studii,
  facultatea, domeniul_de_licenta when Plan was uploaded.
- Section 12 (Aprobări) shows Decan + Director departament when Plan was
  uploaded.
- Body sections that have a clear equivalent in the old FD carry over
  the original content.
- Body sections without an equivalent show the red Romanian placeholder.
- `X-Shift-Report` round-trips to the frontend and the page renders the
  per-section breakdown.
- Unit tests + API integration test pass.
- New "🔄 Template Shifter" entry visible in the nav and reachable.
