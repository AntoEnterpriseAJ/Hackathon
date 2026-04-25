"""Canonicalise Fișa Disciplinei (FD) field keys and coerce numeric values.

Claude's vision/text extraction may emit semantically-equivalent but
lexically-different keys for the same FD field (e.g. ``titular_curs`` vs
``titularul_activitatilor_de_curs``). It may also return ``"III"`` or
``"5"`` (string) where the canonical schema expects a number.

This module provides a single ``normalize_fd_fields`` entry point that
maps any recognised alias to the canonical FD key and coerces the few
numeric scalar fields. It is intentionally conservative: keys it does
not recognise are left untouched so unrelated documents and unknown
fields are not mangled.
"""
from __future__ import annotations

import re
from typing import Iterable

from schemas.extraction import ExtractedDocument, ExtractedField


# --- Canonical key aliases ---------------------------------------------------
#
# Each entry maps a canonical FD key to the alternative keys Claude has been
# observed (or is reasonably expected) to emit. Aliases are matched
# case-insensitively against the *normalised* form of the incoming key
# (lower-case, diacritics stripped, non-alphanumerics → underscore).

_ALIASES: dict[str, tuple[str, ...]] = {
    "denumirea_disciplinei": (
        "denumire_disciplina",
        "nume_disciplina",
        "titlu_disciplina",
        "disciplina",
    ),
    "titularul_activitatilor_de_curs": (
        "titular_curs",
        "titular_de_curs",
        "titularul_cursului",
        "cadru_didactic_curs",
        "lector_curs",
        "profesor_curs",
    ),
    "titularul_activitatilor_de_seminar_laborator_proiect": (
        "titular_seminar",
        "titular_laborator",
        "titular_proiect",
        "titular_seminar_laborator",
        "titular_seminar_laborator_proiect",
        "titularul_seminarului",
        "cadru_didactic_seminar",
        "cadru_didactic_seminar_laborator",
    ),
    "obiective_generale_ale_disciplinei": (
        "obiective_generale",
        "obiectivele_generale",
        "obiectivele_generale_ale_disciplinei",
        "obiective_disciplina",
        "obiectiv_general",
    ),
    "competente_profesionale": (
        "competente_profesionale_dobandite",
        "competente_profesionale_specifice",
        "competente_specifice_profesionale",
    ),
    "competente_transversale": (
        "competente_transversale_dobandite",
        "competente_transversale_specifice",
    ),
    "bibliografie": (
        "bibliografia",
        "bibliografie_obligatorie",
        "bibliografie_minimala",
        "bibliografie_recomandata",
        "referinte_bibliografice",
    ),
    "anul_de_studiu": (
        "anul",
        "an_studiu",
        "an_de_studiu",
        "anul_studiu",
    ),
    "semestrul": (
        "semestru",
        "sem",
    ),
    "tipul_de_evaluare": (
        "tip_evaluare",
        "forma_de_evaluare",
        "forma_evaluare",
        "evaluare",
    ),
    "numar_credite": (
        "credite",
        "nr_credite",
        "numar_de_credite",
        "numarul_de_credite",
        "puncte_credit",
        "ects",
        "credite_ects",
    ),
}


# --- Internal helpers --------------------------------------------------------

_DIACRITIC_MAP = str.maketrans({
    "ă": "a", "â": "a", "Ă": "a", "Â": "a",
    "î": "i", "Î": "i",
    "ș": "s", "ş": "s", "Ș": "s", "Ş": "s",
    "ț": "t", "ţ": "t", "Ț": "t", "Ţ": "t",
})

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_key(key: str) -> str:
    """Lower-case, strip diacritics, collapse non-alphanumerics to ``_``."""
    if not key:
        return ""
    s = key.translate(_DIACRITIC_MAP).lower().strip()
    s = _NON_ALNUM.sub("_", s).strip("_")
    return s


def _build_lookup() -> dict[str, str]:
    """alias-norm → canonical key. Canonical keys map to themselves."""
    out: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        out[_norm_key(canonical)] = canonical
        for alias in aliases:
            out[_norm_key(alias)] = canonical
    return out


_LOOKUP = _build_lookup()


# Roman numeral parser for the small range FD documents actually use (I–XII).
_ROMAN_RE = re.compile(r"^[ivxlcdmIVXLCDM]+$")
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(s: str) -> int | None:
    s = s.strip().lower()
    if not s or not _ROMAN_RE.match(s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_VALUES[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total if total > 0 else None


_NUMERIC_FIELDS = {"anul_de_studiu", "semestrul", "numar_credite"}


def _coerce_numeric(value):
    """Return float for any value that *looks* numeric; otherwise None.

    Accepts ints, floats, decimal strings (``"5"``, ``"3.5"``,
    ``"3,5"``), and roman numerals (``"III"``).
    """
    if isinstance(value, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Try plain decimal (allow comma as decimal separator).
        try:
            return float(s.replace(",", "."))
        except ValueError:
            pass
        # Fall back to roman numerals.
        roman = _roman_to_int(s)
        if roman is not None:
            return float(roman)
    return None


# --- Public API --------------------------------------------------------------

def looks_like_fd(doc: ExtractedDocument) -> bool:
    """Heuristic: does this document look like a Fișa Disciplinei?"""
    dt = _norm_key(doc.document_type or "")
    if "fis" in dt and "disciplin" in dt:
        return True
    # Fallback: presence of FD-specific canonical keys (or aliases) in fields.
    fd_signals = {"denumirea_disciplinei", "titularul_activitatilor_de_curs"}
    for f in doc.fields:
        if _LOOKUP.get(_norm_key(f.key)) in fd_signals:
            return True
    return False


def normalize_fd_fields(doc: ExtractedDocument) -> ExtractedDocument:
    """Return a copy of ``doc`` with FD field keys canonicalised and the
    well-known numeric scalars coerced to numbers.

    Non-FD documents are returned unchanged. Unknown keys are preserved
    as-is. If two incoming fields collapse onto the same canonical key,
    the first occurrence wins (later duplicates are dropped silently).
    """
    if not looks_like_fd(doc):
        return doc

    seen: set[str] = set()
    new_fields: list[ExtractedField] = []
    for f in doc.fields:
        canonical = _LOOKUP.get(_norm_key(f.key), f.key)
        if canonical in seen:
            continue
        seen.add(canonical)

        new_value = f.value
        new_type = f.field_type
        if canonical in _NUMERIC_FIELDS:
            coerced = _coerce_numeric(f.value)
            if coerced is not None:
                new_value = coerced
                new_type = "number"

        if canonical == f.key and new_value is f.value and new_type == f.field_type:
            new_fields.append(f)
        else:
            new_fields.append(
                ExtractedField(
                    key=canonical,
                    value=new_value,
                    field_type=new_type,
                    confidence=f.confidence,
                )
            )

    return doc.model_copy(update={"fields": new_fields})


__all__ = ["normalize_fd_fields", "looks_like_fd"]
