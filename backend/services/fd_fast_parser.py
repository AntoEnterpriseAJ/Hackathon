"""Deterministic fast parser for a single Fișa Disciplinei (FD) PDF.

Extracts the structured fields downstream consumers actually use
(cross-validator, sync-check, copilot) directly from text via pdfplumber.
No Claude calls. Returns ``None`` if the PDF doesn't look parseable so
the caller can fall back to the LLM path.
"""
from __future__ import annotations

import io
import re
from typing import Iterable

import pdfplumber

from schemas.extraction import ExtractedDocument, ExtractedField


# --- Section 1: program identity ---------------------------------------------
_RE_FACULTATEA = re.compile(r"1\.2\s*Facultatea\s+(.+)")
_RE_DEPARTAMENT = re.compile(r"1\.3\s*Departamentul\s+(.+)")
_RE_DOMENIU = re.compile(r"1\.4\s*Domeniul\s+de\s+studii[^\n]*?\)\s*(.+)")
_RE_CICLU = re.compile(r"1\.5\s*Ciclul\s+de\s+studii[^\n]*?\)\s*(.+)")
_RE_PROGRAM = re.compile(r"1\.6\s*Programul\s+de\s+studii[^\n]*?\s+(.+)")

# --- Section 2: course identity ----------------------------------------------
_RE_DENUMIRE = re.compile(r"2\.1\s*Denumirea\s+disciplinei\s+(.+)")
_RE_TITULAR_CURS = re.compile(r"2\.2\s*Titularul\s+activităților\s+de\s+curs\s+(.+)")
# 2.3 "Titularul activităților de seminar/ laborator/ <NAME>\nproiect".
# Some FDs split the label across two lines; we capture the value that
# follows the second slash on the same line.
_RE_TITULAR_SLP = re.compile(
    r"2\.3\s*Titularul\s+activit[ăa][țt]ilor\s+de\s+seminar[/ ]+\s*laborator[/ ]+\s*(.+)"
)
# Numeric fields can be followed inline by the value OR on the next line
# ("2.4 Anul de studiu 2.5 Semestrul ...\n1 1 E DC"). Reject section-number
# tokens like "2.5" by requiring 1–2 digits with no dot.
_RE_AN = re.compile(r"2\.4\s*Anul\s+de\s+studiu\s+(?!\d+\.)(\d{1,2})\b")
_RE_SEM = re.compile(r"2\.5\s*Semestrul\s+(?!\d+\.)(\d{1,2})\b")
_RE_TIP_EVAL = re.compile(r"2\.6\s*Tipul\s+de\s+evaluare\s+(?!\d+\.)([A-Z]{1,3})\b")
# 2.7 has two sub-rows on the same line: "Conținut3) DC" + "Obligativitate4) DI"
_RE_REGIM_CONTINUT = re.compile(r"Con[țt]inut[^A-Za-z]*([A-Z]{1,3})")
_RE_REGIM_OBLIG = re.compile(r"Obligativitate[^A-Za-z]*([A-Z]{1,3})")

# --- Section 3: hours --------------------------------------------------------
# "3.1 Număr de ore pe săptămână 5 din care: 3.2 curs 3 3.3 seminar/ laborator/ 2"
_RE_ORE_SAPT = re.compile(
    r"3\.1\s*Num[ăa]r\s+de\s+ore\s+pe\s+s[ăa]pt[ăa]m[ââ]n[ăa]\s+(\d+)"
)
# Capture the curs hours after the "3.2 curs" label, but only if the value
# sits on the same line. The negative lookahead `(?!\.\d)` keeps us from
# accidentally grabbing the "3" of a following "3.3" label, and `[^\S\n]+`
# (whitespace excluding newlines) keeps us on the current line.
_RE_CURS_SAPT = re.compile(r"3\.2\s*curs[^\S\n]+(\d+)(?!\.\d)")
# Some FDs omit the "curs" label, so 3.2 sits next to a bare value:
#   "... 3.2 2 3.3 seminar/ laborator/ 0/2/0"
_RE_CURS_SAPT_BARE = re.compile(r"3\.2[^\S\n]+(\d+)(?!\.\d)")
# Seminar/laborator hours: same-line only, otherwise we leak into the values
# row that sits below the labels (handled by `_parse_section3_multiline`).
_RE_SEM_SAPT = re.compile(r"3\.3\s*seminar[^\d\n]*(\d+)\b")
# Compact slash format used by some FDs after "3.3 seminar/ laborator/":
#   "0/2/0" → seminar=0, laborator=2, proiect=0  (or any C/S/L variant).
# Captures the whole slash group so we can sum the components.
_RE_SLP_SLASH_SAPT = re.compile(r"3\.3\s*seminar[^\n]*?((?:\d+/)+\d+)\b")
_RE_TOTAL_PLAN = re.compile(
    r"3\.4\s*Total\s+ore\s+din\s+planul\s+de\s+[îi]nv[ăa][țt][ăa]m[ââ]nt\s+(\d+)"
)
_RE_TOTAL_CURS = re.compile(r"3\.5\s*curs[^\S\n]+(\d+)(?!\.\d)")
_RE_TOTAL_CURS_BARE = re.compile(r"3\.5[^\S\n]+(\d+)(?!\.\d)")
_RE_TOTAL_SEM = re.compile(r"3\.6\s*seminar[^\d\n]*(\d+)\b")
_RE_SLP_SLASH_TOTAL = re.compile(r"3\.6\s*seminar[^\n]*?((?:\d+/)+\d+)\b")
_RE_TOTAL_STUD = re.compile(r"3\.7\s*Total\s+ore\s+de\s+activitate(?:\s+a)?\s+(\d+)")
_RE_TOTAL_SEM_GLOBAL = re.compile(r"3\.8\s*Total\s+ore\s+pe\s+semestru\s+(\d+)")
# Section 3.9 in real FDs reads e.g. "Numărul de credite5) 6" — the
# parenthesised digit is a footnote marker, so we explicitly skip it before
# capturing the actual credit value.
_RE_CREDITE = re.compile(
    r"3\.9\s*Num[ăa]rul\s+de\s+credite\s*(?:\d+\s*\))?\s*(\d+(?:[.,]\d+)?)"
)

# --- Section 7: obiective ----------------------------------------------------
# 7.1 "Obiectivul general al disciplinei <body>" — body may span several
# lines; we capture greedily until the next 7.x / 8.x heading.
_RE_OBIECTIV_GENERAL = re.compile(
    r"7\.1\s*Obiectivul\s+general\s+al\s+disciplinei\s+(.+?)(?=\n\s*7\.\d|\n\s*8\.|\Z)",
    re.DOTALL,
)

# --- Section 8: competence codes (CP*/CT*) -----------------------------------
_RE_COMPETENTA = re.compile(r"\b(CP\d+|CT\d+)\b")

# --- Bibliografie ------------------------------------------------------------
# A bibliography block starts with a "Bibliografie" heading on its own line
# and runs until the next FD section we know about. We DON'T terminate on
# any "<digit>. <Uppercase>" line because that pattern also matches numbered
# bibliography entries themselves (e.g. "1. S. Chiriță, ..."). Instead we
# stop at the next sub-section heading ("8.2 ...") OR an explicit known
# top-level heading keyword (Coroborarea, Evaluare, Repartizarea, Bibliografie).
_RE_BIB_BLOCK = re.compile(
    r"(?im)^[ \t]*Bibliografie[^\n]*\n(.+?)"
    r"(?="
    r"^[ \t]*\d+\.\d+[ \t]+[A-Za-zȘȚĂÎÂșțăîâ]"          # e.g. "8.2 Seminar..."
    r"|^[ \t]*\d+\.?[ \t]+(?:Coroborarea|Evaluare|Repartizarea|Standard)\b"
    r"|^[ \t]*Bibliografie\b"
    r"|\Z"
    r")",
    re.DOTALL,
)
# Inside a block, an entry begins with either a bullet (• - *), a leading
# number ("1. ", "12. ") or a bracketed citation key ("[1]", "[12]").
# Use that prefix as a split anchor.
_RE_BIB_ENTRY_SPLIT = re.compile(r"(?m)^\s*(?:[\u2022\-\*]|\d{1,3}\.|\[\d{1,3}\])\s+")
# Lines we never want to keep as bibliography entries (form footers, page
# markers, stray whitespace stubs).
_RE_BIB_NOISE = re.compile(r"^(?:F\d{2}\.\d|Pag(?:e|ina)?\b|\d+\s*$)", re.IGNORECASE)


def parse_fd(pdf_bytes: bytes) -> ExtractedDocument | None:
    """Parse a single FD PDF deterministically.

    Returns an ``ExtractedDocument`` on success, ``None`` on failure
    (so the caller can fall back to the Claude path).
    """
    if not pdf_bytes:
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            )
    except Exception:
        return None

    if not full_text.strip():
        return None

    fields: list[ExtractedField] = []

    def _add_str(key: str, value: str | None) -> None:
        if value:
            fields.append(ExtractedField(
                key=key, value=value.strip(), field_type="string"
            ))

    def _add_num(key: str, value: str | None) -> None:
        if value is None:
            return
        try:
            num = float(value)
        except ValueError:
            return
        if num.is_integer():
            num_val: float | int = int(num)
        else:
            num_val = num
        fields.append(ExtractedField(
            key=key, value=float(num_val), field_type="number"
        ))

    def _first(pattern: re.Pattern[str]) -> str | None:
        m = pattern.search(full_text)
        if not m:
            return None
        # Strip trailing footnote markers, whitespace, and adjacent labels.
        raw = m.group(1)
        # Cut at the next "X.Y " section number on the same line.
        raw = re.split(r"\s+\d+\.\d+\s", raw, maxsplit=1)[0]
        return re.sub(r"\s+", " ", raw).strip(" .,;")

    # Program identity
    _add_str("facultatea", _first(_RE_FACULTATEA))
    _add_str("departamentul", _first(_RE_DEPARTAMENT))
    _add_str("domeniul_de_studii", _first(_RE_DOMENIU))
    _add_str("ciclul_de_studii", _first(_RE_CICLU))
    _add_str("programul_de_studii", _first(_RE_PROGRAM))

    # Course identity
    _add_str("denumirea_disciplinei", _first(_RE_DENUMIRE))
    _add_str("titular_curs", _first(_RE_TITULAR_CURS))
    _add_str("titular_seminar_laborator_proiect", _first(_RE_TITULAR_SLP))

    # Section 2.4-2.7 has two layouts: (a) inline `2.4 ... <val> 2.5 ...` and
    # (b) labels-on-one-line, values-on-the-next. Try inline first, then
    # fall back to the multi-line pattern.
    inline = {
        "anul_de_studiu": _first(_RE_AN),
        "semestrul": _first(_RE_SEM),
        "tipul_de_evaluare": _first(_RE_TIP_EVAL),
    }
    if not all(inline.values()):
        ml = _parse_section2_multiline(full_text)
        for k, v in ml.items():
            inline.setdefault(k, None)
            if not inline[k] and v:
                inline[k] = v
    _add_str("anul_de_studiu", inline.get("anul_de_studiu"))
    _add_str("semestrul", inline.get("semestrul"))
    _add_str("tipul_de_evaluare", inline.get("tipul_de_evaluare"))
    _add_str("regimul_disciplinei_continut", _first(_RE_REGIM_CONTINUT))
    _add_str("regimul_disciplinei_obligativitate", _first(_RE_REGIM_OBLIG))

    # Hours
    # Section 3.1/3.2/3.3 has multiple layouts. We resolve them in order:
    #   (a) "3.1 Număr de ore pe săptămână N din care: 3.2 curs N 3.3 seminar... N"
    #   (b) "3.1 Număr de ore pe săptămână din care: 3.2 N 3.3 seminar/ laborator/ N/N/N"
    #   (c) "3.1 Număr de ore pe săptămână din care: 3.2 3.3 seminar/ laborator/ N/N/N"
    #   (d) labels-on-one-line, values-on-the-next (handled by
    #       `_parse_section3_multiline`).
    sec3_ml = _parse_section3_multiline(full_text)

    # Curs hours: prefer multi-line column, then labelled, then bare.
    curs_w = sec3_ml.get("curs_w") or _first(_RE_CURS_SAPT) or _first(_RE_CURS_SAPT_BARE)
    # Seminar/lab/proiect: prefer multi-line, then slash form, then first digit.
    if sec3_ml.get("slp_w") is not None:
        slp_w: str | None = sec3_ml.get("slp_w")
    else:
        slp_slash = _first(_RE_SLP_SLASH_SAPT)
        if slp_slash:
            try:
                slp_w_val = sum(int(p) for p in slp_slash.split("/") if p.isdigit())
                slp_w = str(slp_w_val)
            except ValueError:
                slp_w = _first(_RE_SEM_SAPT)
        else:
            slp_w = _first(_RE_SEM_SAPT)
    # Total weekly hours: explicit value if present, else curs + S/L/P sum.
    total_w_raw = sec3_ml.get("total_w") or _first(_RE_ORE_SAPT)
    if total_w_raw is None and (curs_w or slp_w):
        total_w_raw = str(int(curs_w or 0) + int(slp_w or 0))

    _add_num("numar_ore_pe_saptamana_total", total_w_raw)
    _add_num("ore_curs_pe_saptamana", curs_w)
    _add_num("ore_seminar_laborator_proiect_pe_saptamana", slp_w)

    # Same shape for "total per semester" block (3.4–3.6).
    total_curs_w = (
        sec3_ml.get("total_curs")
        or _first(_RE_TOTAL_CURS)
        or _first(_RE_TOTAL_CURS_BARE)
    )
    if sec3_ml.get("total_slp") is not None:
        slp_total: str | None = sec3_ml.get("total_slp")
    else:
        slp_total_slash = _first(_RE_SLP_SLASH_TOTAL)
        if slp_total_slash:
            try:
                slp_total_val = sum(int(p) for p in slp_total_slash.split("/") if p.isdigit())
                slp_total = str(slp_total_val)
            except ValueError:
                slp_total = _first(_RE_TOTAL_SEM)
        else:
            slp_total = _first(_RE_TOTAL_SEM)

    _add_num("total_ore_plan_invatamant", sec3_ml.get("total_plan") or _first(_RE_TOTAL_PLAN))
    _add_num("total_ore_curs", total_curs_w)
    _add_num("total_ore_seminar_laborator_proiect", slp_total)
    _add_num("total_ore_studiu_individual", _first(_RE_TOTAL_STUD))
    _add_num("total_ore_pe_semestru", _first(_RE_TOTAL_SEM_GLOBAL))
    _add_num("numarul_de_credite", _first(_RE_CREDITE))

    # Obiectivul general (section 7.1) — may be multi-line.
    obiectiv_match = _RE_OBIECTIV_GENERAL.search(full_text)
    if obiectiv_match:
        obiectiv = re.sub(r"\s+", " ", obiectiv_match.group(1)).strip(" .,;•")
        if obiectiv:
            fields.append(ExtractedField(
                key="obiective_generale_ale_disciplinei",
                value=obiectiv,
                field_type="string",
            ))

    # Competence codes (deduped, order-preserving), then split CP/CT.
    seen: set[str] = set()
    competente: list[str] = []
    for m in _RE_COMPETENTA.finditer(full_text):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            competente.append(code)
    if competente:
        fields.append(ExtractedField(
            key="competente_referite",
            value=competente,
            field_type="list",
        ))
        cp_codes = [c for c in competente if c.startswith("CP")]
        ct_codes = [c for c in competente if c.startswith("CT")]
        if cp_codes:
            fields.append(ExtractedField(
                key="competente_profesionale",
                value=cp_codes,
                field_type="list",
            ))
        if ct_codes:
            fields.append(ExtractedField(
                key="competente_transversale",
                value=ct_codes,
                field_type="list",
            ))

    # Bibliografie — collect all entries from every "Bibliografie" block.
    bib_entries: list[str] = []
    for bm in _RE_BIB_BLOCK.finditer(full_text):
        block = bm.group(1)
        # Split on bullet/number prefix; ignore anything before the first prefix.
        parts = _RE_BIB_ENTRY_SPLIT.split(block)
        if len(parts) <= 1:
            # No prefix found — treat each non-empty line as an entry.
            parts = [ln for ln in block.splitlines() if ln.strip()]
        else:
            parts = parts[1:]  # drop the pre-first-prefix preamble
        for raw in parts:
            entry = re.sub(r"\s+", " ", raw).strip(" .,;")
            if len(entry) < 10:
                continue
            if _RE_BIB_NOISE.match(entry):
                continue
            bib_entries.append(entry)
    if bib_entries:
        fields.append(ExtractedField(
            key="bibliografie",
            value=bib_entries,
            field_type="list",
        ))

    # Need at least course name + credits to consider this a successful parse.
    if not _has_field(fields, "denumirea_disciplinei") or not _has_field(
        fields, "numarul_de_credite"
    ):
        return None

    course_name = _value(fields, "denumirea_disciplinei") or "FD"
    credits_val = _value(fields, "numarul_de_credite")
    summary = f"Fișa disciplinei: {course_name} ({credits_val} credite)"

    return ExtractedDocument(
        document_type="fisa_disciplinei",
        summary=summary,
        fields=fields,
        tables=[],
        source_route="fast_pdfplumber",
    )


def _has_field(fields: Iterable[ExtractedField], key: str) -> bool:
    return any(f.key == key and f.value not in (None, "") for f in fields)


def _value(fields: Iterable[ExtractedField], key: str):
    for f in fields:
        if f.key == key:
            return f.value
    return None


_RE_SEC2_LABEL_LINE = re.compile(
    r"2\.4\s*Anul\s+de\s+studiu\s+2\.5\s*Semestrul\s+2\.6\s*Tipul\s+de\s+evaluare",
    re.IGNORECASE,
)


def _parse_section2_multiline(text: str) -> dict[str, str | None]:
    """Handle FDs whose section 2.4-2.7 places labels on one line and the
    values on the following line, e.g.:

        2.4 Anul de studiu  2.5 Semestrul  2.6 Tipul de evaluare  2.7 ...
        I 1 V disciplinei Obligativitate3) DO

    Returns a dict with anul_de_studiu / semestrul / tipul_de_evaluare,
    or empty values if the layout doesn't match.
    """
    out: dict[str, str | None] = {
        "anul_de_studiu": None,
        "semestrul": None,
        "tipul_de_evaluare": None,
    }
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not _RE_SEC2_LABEL_LINE.search(line):
            continue
        if i + 1 >= len(lines):
            break
        value_line = lines[i + 1].strip()
        # Take the first three whitespace-separated tokens.
        tokens = value_line.split()
        if len(tokens) < 3:
            break
        out["anul_de_studiu"] = tokens[0]
        out["semestrul"] = tokens[1]
        out["tipul_de_evaluare"] = tokens[2]
        break
    return out


# Detect the labels-only header lines for the section-3 hours blocks.
# Both 3.1-3.3 (weekly) and 3.4-3.6 (per-semester totals) follow the same
# layout: three column labels on one line, three values on the next.
_RE_SEC3_HEADER_WEEKLY = re.compile(
    r"3\.1\s*Num[ăa]r\s+de\s+ore\s+pe\s+s[ăa]pt[ăa]m[ââ]n[ăa].*3\.2.*3\.3",
    re.IGNORECASE,
)
_RE_SEC3_HEADER_TOTAL = re.compile(
    r"3\.4\s*Total\s+ore\s+din\s+planul.*3\.5.*3\.6",
    re.IGNORECASE,
)


def _sum_slash(token: str) -> str | None:
    """Sum a slash-separated group like \"0/2/0\". Returns ``None`` if not
    in that shape."""
    if "/" not in token:
        return None
    parts = token.split("/")
    if not all(p.isdigit() for p in parts):
        return None
    return str(sum(int(p) for p in parts))


def _parse_section3_multiline(text: str) -> dict[str, str | None]:
    """Handle FDs whose section 3.1-3.3 / 3.4-3.6 place column labels on one
    line and the numeric values on the following line, e.g.:

        3.1 Număr de ore pe săptămână din care: 3.2 curs 3.3 seminar/ laborator/
        4 2 0/2/0
        proiect

    Returns a dict with weekly + total hour fields, all optional.
    """
    out: dict[str, str | None] = {
        "total_w": None,
        "curs_w": None,
        "slp_w": None,
        "total_plan": None,
        "total_curs": None,
        "total_slp": None,
    }
    lines = text.split("\n")

    def _parse_value_line(value_line: str) -> tuple[str | None, str | None, str | None]:
        """Return (col1, col2, col3) where col3 may be a slash-summed value."""
        tokens = value_line.strip().split()
        if not tokens:
            return None, None, None
        # Drop tokens that aren't numeric or slash-numeric (stray words from
        # wrapped labels can appear at the end of the line).
        numeric: list[str] = []
        for tok in tokens:
            if tok.isdigit() or _sum_slash(tok) is not None:
                numeric.append(tok)
            else:
                # Stop at the first non-numeric token to keep alignment.
                break
        if len(numeric) < 2:
            return None, None, None
        c1 = numeric[0] if numeric[0].isdigit() else None
        c2 = numeric[1] if len(numeric) > 1 and numeric[1].isdigit() else None
        c3_raw = numeric[2] if len(numeric) > 2 else None
        c3 = _sum_slash(c3_raw) if c3_raw else None
        if c3 is None and c3_raw and c3_raw.isdigit():
            c3 = c3_raw
        return c1, c2, c3

    for i, line in enumerate(lines):
        if i + 1 >= len(lines):
            break
        if _RE_SEC3_HEADER_WEEKLY.search(line):
            t, c, s = _parse_value_line(lines[i + 1])
            out["total_w"] = out["total_w"] or t
            out["curs_w"] = out["curs_w"] or c
            out["slp_w"] = out["slp_w"] or s
        elif _RE_SEC3_HEADER_TOTAL.search(line):
            t, c, s = _parse_value_line(lines[i + 1])
            out["total_plan"] = out["total_plan"] or t
            out["total_curs"] = out["total_curs"] or c
            out["total_slp"] = out["total_slp"] or s
    return out
