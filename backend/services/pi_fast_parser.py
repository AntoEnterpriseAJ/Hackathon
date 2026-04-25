"""Deterministic fast parser for a Plan de Învățământ (PI) PDF.

Walks the per-year curriculum pages with pdfplumber's table extractor and
emits canonical ``ExtractedTable`` rows shaped for the cross-validator
(``s1_c``, ``s1_s``, ``s1_l``, ``s1_p``, ``s1_pr``, ``s1_si``, ``s1_v``,
``s1_cr`` and the ``s2_*`` mirror).

Returns ``None`` when no curriculum tables can be recovered.
"""
from __future__ import annotations

import io
import re
from typing import Iterable

import pdfplumber

from schemas.extraction import ExtractedDocument, ExtractedField, ExtractedTable


_YEAR_HEADER_RE = re.compile(
    r"valabil\s+(?:[îi]n\s+)?an(?:ul)?\s+universitar\s+(\d{4})\s*[-–]\s*(\d{4})",
    re.IGNORECASE,
)
_PROGRAM_RE = re.compile(r"Programul\s+de\s+studii\s*\n?\s*(.+)", re.IGNORECASE)
_FACULTATEA_RE = re.compile(r"Facultatea\s+(.+)", re.IGNORECASE)
_DOMENIU_LIC_RE = re.compile(r"Domeniul\s+de\s+licen[țt][ăa]\s+(.+)", re.IGNORECASE)

_CRITERIU_TO_SUFFIX = {
    "obligatoriu": "obligatorii",
    "optional": "optionale",
    "opţional": "optionale",
    "opțional": "optionale",
    "facultativ": "facultative",
}

# Canonical column layout (PI year tables):
#   0:nr_crt 1:disciplina 2:c1 3:c2
#   4:s1_c  5:s1_s  6:s1_l  7:s1_p  8:s1_si  9:s1_pr 10:s1_v ... 13:s1_cr
#   14:s2_c 15:s2_s 16:s2_l 17:s2_p 18:s2_si 19:s2_pr 20:s2_v ... 23:s2_cr
_HEADERS = [
    "nr_crt", "disciplina", "c1", "c2",
    "s1_c", "s1_s", "s1_l", "s1_p", "s1_si", "s1_pr", "s1_v",
    "s1_extra1", "s1_extra2", "s1_cr",
    "s2_c", "s2_s", "s2_l", "s2_p", "s2_si", "s2_pr", "s2_v",
    "s2_extra1", "s2_extra2", "s2_cr",
]


def parse_pi(pdf_bytes: bytes) -> ExtractedDocument | None:
    if not pdf_bytes:
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return _parse(pdf)
    except Exception:
        return None


def _parse(pdf) -> ExtractedDocument | None:
    fields: list[ExtractedField] = []
    tables: list[ExtractedTable] = []

    # Pull program identity from front-matter (page 1 usually).
    head_text = "\n".join(
        (pdf.pages[i].extract_text() or "") for i in range(min(2, len(pdf.pages)))
    )
    _add_match(fields, "programul_de_studii", _PROGRAM_RE, head_text)
    _add_match(fields, "facultatea", _FACULTATEA_RE, head_text)
    _add_match(fields, "domeniul_de_licenta", _DOMENIU_LIC_RE, head_text)

    # Scan the *full* document text for the official competence catalog
    # (CP1..CPn / CT1..CTn with their human-readable titles). Most PIs declare
    # them outside of any table, in narrative prose like
    # "CP1. Programarea în limbaje de nivel înalt".
    full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    catalog = _extract_competency_catalog(full_text)
    if catalog:
        fields.append(ExtractedField(
            key="competente_catalog",
            # Encode as "CODE: title" strings so we stay within the existing
            # ExtractedField schema (list[str]); consumers split on ': '.
            value=[f"{c['code']}: {c['title']}" for c in catalog],
            field_type="list",
        ))

    # Pull the signature block (Rector / Decan / Director departament /
    # Coordonator program studii) from the curriculum pages footer. These
    # names feed Section 12 (Aprobări) of the FD draft renderer.
    _extract_signatories(full_text, fields)

    # Walk pages, detecting curriculum-year pages by header text.
    current_year: int | None = None
    for page in pdf.pages:
        page_text = page.extract_text() or ""
        year = _detect_year(page_text, current_year)
        if year is None:
            continue
        current_year = year

        page_tables = page.extract_tables() or []
        for raw_table in page_tables:
            extracted = _table_from_rows(raw_table, year)
            if extracted is not None:
                tables.append(extracted)

    if not tables:
        return None

    program = _value(fields, "programul_de_studii") or "Plan de învățământ"
    summary = f"Plan de învățământ — {program} ({len(tables)} tabele)"

    doc = ExtractedDocument(
        document_type="plan_de_invatamant",
        summary=summary,
        fields=fields,
        tables=tables,
        source_route="fast_pdfplumber",
    )
    _normalize_year_labels(doc)
    return doc


# ---------- helpers ----------

def _detect_year(page_text: str, current: int | None) -> int | None:
    """Detect which study year (1..n) the current page belongs to.

    Heuristic: the per-year header line reads
    ``... valabil în an universitar 2025-2026``. Each successive page
    that doesn't reset that header inherits the previous year (most year
    tables span only a single page in real PIs anyway).
    """
    m = _YEAR_HEADER_RE.search(page_text)
    if not m:
        return None
    # Year ordinal = (start_year - first_seen_start_year) + 1
    # We don't know the first year, so fall back to detecting "Anul I/II/III"
    # by counting page occurrences. Simpler: extract the start year and map.
    start = int(m.group(1))
    return start  # caller normalizes via _year_label below


def _year_label(year_int: int, year_base: int | None) -> str:
    if year_base is None:
        return "i"
    delta = year_int - year_base
    return {0: "i", 1: "ii", 2: "iii", 3: "iv", 4: "v"}.get(delta, str(delta + 1))


def _table_from_rows(raw_table: list[list[str | None]], year_int: int) -> ExtractedTable | None:
    """Convert one pdfplumber table into a canonical ExtractedTable.

    Returns ``None`` if the table doesn't look like a curriculum table.
    """
    if not raw_table or len(raw_table) < 3:
        return None

    header_row = _join_cells(raw_table[0])
    if "discipline" not in header_row.lower():
        return None

    criteriu = _detect_criteriu(header_row)
    if criteriu is None:
        return None

    rows: list[list[str]] = []
    for raw_row in raw_table[2:]:  # skip the C/S/L/P/... sub-header
        row = [_clean_cell(c) for c in raw_row]
        if not row or not row[0]:
            continue
        first = row[0].strip().lower()
        if first.startswith("total") or "didactice" in first:
            continue
        # pad/truncate to canonical width
        if len(row) < len(_HEADERS):
            row = row + [""] * (len(_HEADERS) - len(row))
        else:
            row = row[: len(_HEADERS)]
        rows.append(row)

    if not rows:
        return None

    # Year label is approximate; use the start year (e.g., 2025) for now and
    # normalize later. The cross-validator only inspects the suffix
    # (anul_i / anul_ii / anul_iii), so we map the *order* of distinct years.
    name = f"discipline_{criteriu}_anul_year{year_int}"
    return ExtractedTable(name=name, headers=list(_HEADERS), rows=rows)


def _detect_criteriu(header_text: str) -> str | None:
    text = header_text.lower()
    for key, suffix in _CRITERIU_TO_SUFFIX.items():
        if key in text:
            return suffix
    return None


def _clean_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell)).strip()


def _join_cells(row: list[str | None]) -> str:
    return " ".join(_clean_cell(c) for c in row if c)


def _add_match(
    fields: list[ExtractedField],
    key: str,
    pattern: re.Pattern[str],
    text: str,
) -> None:
    m = pattern.search(text)
    if not m:
        return
    val = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
    if val:
        fields.append(ExtractedField(key=key, value=val, field_type="string"))


def _value(fields: Iterable[ExtractedField], key: str):
    for f in fields:
        if f.key == key:
            return f.value
    return None


def _normalize_year_labels(doc: ExtractedDocument) -> None:
    """Rewrite ``..._anul_year2025`` suffixes into ``..._anul_i/ii/iii``.

    Done as a post-pass after all tables are gathered so we know the
    chronological order of years in the document.
    """
    seen_years: list[int] = []
    for t in doc.tables:
        m = re.search(r"_anul_year(\d{4})$", t.name)
        if m:
            y = int(m.group(1))
            if y not in seen_years:
                seen_years.append(y)
    seen_years.sort()
    label_for: dict[int, str] = {}
    for idx, y in enumerate(seen_years):
        label_for[y] = {0: "i", 1: "ii", 2: "iii", 3: "iv", 4: "v"}.get(idx, str(idx + 1))

    for t in doc.tables:
        m = re.search(r"^(.*)_anul_year(\d{4})$", t.name)
        if m:
            base, ystr = m.group(1), int(m.group(2))
            t.name = f"{base}_anul_{label_for.get(ystr, 'i')}"


# Title prefix that introduces a person's name in UTCN signature blocks
# (PROF. DR., CONF. DR., LECT. DR., ASIST. DR., ȘEF LUCR. DR., etc.).
# Matches at the *start* of a name and is used to split a two-column line
# (e.g. "CONF. DR. NICUSOR MINCULETE CONF. DR. ALEXANDRA BAICOIANU") into
# the left and right column names.
_TITLE_PREFIX_RE = re.compile(
    r"\b(?:PROF|CONF|LECT|ASIST|[ȘS]EF\s+LUCR)\.?\s*DR\.?",
    re.IGNORECASE,
)


def _extract_signatories(full_text: str, fields: list[ExtractedField]) -> None:
    """Extract Rector / Decan / Director departament / Coordonator names.

    Looks for label rows of the form ``RECTOR, DECAN,`` and
    ``DIRECTOR DEPARTAMENT, COORDONATOR PROGRAM STUDII,`` followed on the
    next line by the corresponding pair of names. The two columns are
    glued by ``pdfplumber`` into a single string (e.g. ``"PROF. DR. IOAN
    VASILE ABRUDAN CONF. DR. ION GABRIEL STAN"``); we split at the second
    occurrence of a title prefix.

    Stores the first hit (the document repeats the block on every year
    page) under canonical keys consumed by the FD draft renderer.
    """
    lines = full_text.splitlines()

    pairs: list[tuple[str, str, str, str]] = []  # (label_left, label_right, name_left, name_right)
    for i, line in enumerate(lines[:-1]):
        upper = line.upper().strip().rstrip(",")
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not nxt:
            continue
        names = _split_two_column_names(nxt)
        if names is None:
            continue
        left, right = names
        if "RECTOR" in upper and "DECAN" in upper:
            pairs.append(("rector", "decanul_facultatii", left, right))
        elif "DIRECTOR" in upper and "DEPARTAMENT" in upper and "COORDONATOR" in upper:
            pairs.append(
                ("directorul_de_departament", "coordonator_program_studii", left, right)
            )

    seen: set[str] = {f.key for f in fields}
    for left_key, right_key, left_val, right_val in pairs:
        if left_key not in seen and left_val:
            fields.append(ExtractedField(key=left_key, value=left_val, field_type="string"))
            seen.add(left_key)
        if right_key not in seen and right_val:
            fields.append(ExtractedField(key=right_key, value=right_val, field_type="string"))
            seen.add(right_key)


def _split_two_column_names(line: str) -> tuple[str, str] | None:
    """Split a name-row like ``"PROF. DR. X Y CONF. DR. A B"`` into
    ``("PROF. DR. X Y", "CONF. DR. A B")`` using title-prefix anchors.

    Returns ``None`` if the line doesn't contain at least two title
    prefixes (i.e. it is not a two-column signatures row).
    """
    matches = list(_TITLE_PREFIX_RE.finditer(line))
    if len(matches) < 2:
        return None
    second = matches[1]
    left = line[: second.start()].strip(" ,;\t")
    right = line[second.start() :].strip(" ,;\t")
    if not left or not right:
        return None
    return _normalize_person(left), _normalize_person(right)


def _normalize_person(raw: str) -> str:
    """Pretty-print an upper-case PDF name like ``CONF. DR. NICUSOR MINCULETE``
    into ``Conf. dr. Nicusor MINCULETE`` so it reads naturally in the FD docx.

    Last-name diacritics cannot be recovered from the PDF text layer, so we
    keep the surname in CAPS to match the visual style of the printed PI.
    """
    raw = re.sub(r"\s+", " ", raw).strip()
    m = _TITLE_PREFIX_RE.match(raw)
    if not m:
        return raw
    title = m.group(0).rstrip(".").strip()
    rest = raw[m.end() :].strip(" .,")
    title_pretty = _pretty_title(title)
    if not rest:
        return title_pretty
    parts = rest.split()
    if len(parts) >= 2:
        # Last token = surname (kept caps); everything before = given names.
        given = " ".join(p.capitalize() for p in parts[:-1])
        surname = parts[-1].upper()
        return f"{title_pretty} {given} {surname}"
    return f"{title_pretty} {parts[0].capitalize()}"


def _pretty_title(title_raw: str) -> str:
    t = re.sub(r"\s+", " ", title_raw).strip().lower()
    # collapse "prof dr" / "prof. dr" → "Prof. dr."
    t = t.replace(".", "")
    parts = [p for p in t.split() if p]
    if not parts:
        return ""
    head = parts[0].capitalize()  # Prof / Conf / Lect / Asist / Sef
    tail = " ".join(p.lower() for p in parts[1:])  # dr
    return f"{head}. {tail}." if tail else f"{head}."


# Matches lines that introduce a competency definition, e.g.
#   "CP1. Programarea în limbaje de nivel înalt"
#   "CT 2. Aplicarea principiilor și normelor de etică..."
# We capture up to a line break or any structural marker that signals the end
# of the title (footnote refs, page breaks, sub-section labels).
_RE_COMPETENCY_LINE = re.compile(
    r"^\s*(CP|CT)\s*0?(\d+)\.?\s+(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_competency_catalog(text: str) -> list[dict[str, str]]:
    """Pull the official CP/CT catalog out of a PI's narrative text.

    Returns a list of ``{"code": "CP1", "title": "..."}`` dicts ordered by
    code (CP first, then CT). Skips false-positive sub-headings like
    "CP1. Cunoștințe" by requiring the title to be a plausible competence
    description (length >= 8 chars, contains a space).
    """
    found: dict[str, str] = {}
    for m in _RE_COMPETENCY_LINE.finditer(text):
        prefix = m.group(1).upper()
        num = int(m.group(2))
        code = f"{prefix}{num}"
        title = m.group(3).strip()
        # Strip trailing footnote markers and over-long fragments.
        title = re.sub(r"\s*\d+\)\s*$", "", title)
        if len(title) < 8 or " " not in title:
            continue
        # Keep the first occurrence (definitions usually precede their detail blocks).
        found.setdefault(code, title)

    def _sort_key(code: str) -> tuple[int, int]:
        prefix_rank = 0 if code.startswith("CP") else 1
        return (prefix_rank, int(code[2:]))

    return [{"code": c, "title": found[c]} for c in sorted(found, key=_sort_key)]
