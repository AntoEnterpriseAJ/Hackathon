"""Tests for the FD field normalizer."""
from __future__ import annotations

from schemas.extraction import ExtractedDocument, ExtractedField
from services.fd_field_normalizer import (
    looks_like_fd,
    normalize_fd_fields,
)


def _make_doc(fields: list[dict], document_type: str = "FIȘA DISCIPLINEI") -> ExtractedDocument:
    return ExtractedDocument(
        document_type=document_type,
        summary="",
        fields=[ExtractedField(**f) for f in fields],
        tables=[],
        source_route="text_pdf",
    )


def test_aliases_collapse_to_canonical_keys():
    doc = _make_doc([
        {"key": "titular_curs", "value": "Lect. dr. X", "field_type": "string"},
        {"key": "titular_seminar_laborator", "value": "Lect. dr. Y", "field_type": "string"},
        {"key": "obiective_generale", "value": "...", "field_type": "string"},
        {"key": "credite", "value": "5", "field_type": "string"},
    ])

    out = normalize_fd_fields(doc)
    keys = {f.key for f in out.fields}

    assert "titularul_activitatilor_de_curs" in keys
    assert "titularul_activitatilor_de_seminar_laborator_proiect" in keys
    assert "obiective_generale_ale_disciplinei" in keys
    assert "numarul_de_credite" in keys


def test_numeric_string_coerced_to_number():
    doc = _make_doc([
        {"key": "anul_de_studiu", "value": "3", "field_type": "string"},
        {"key": "semestrul", "value": "2", "field_type": "string"},
        {"key": "credite", "value": "4,5", "field_type": "string"},
    ])

    out = normalize_fd_fields(doc)
    by_key = {f.key: f for f in out.fields}

    assert by_key["anul_de_studiu"].value == 3.0
    assert by_key["anul_de_studiu"].field_type == "number"
    assert by_key["semestrul"].value == 2.0
    assert by_key["numarul_de_credite"].value == 4.5


def test_roman_numeral_coerced_to_number():
    doc = _make_doc([
        {"key": "anul_de_studiu", "value": "III", "field_type": "string"},
        {"key": "semestrul", "value": "II", "field_type": "string"},
    ])

    out = normalize_fd_fields(doc)
    by_key = {f.key: f for f in out.fields}

    assert by_key["anul_de_studiu"].value == 3.0
    assert by_key["semestrul"].value == 2.0


def test_diacritics_and_casing_match_aliases():
    doc = _make_doc([
        {"key": "Titularul Cursului", "value": "Prof. Z", "field_type": "string"},
        {"key": "BIBLIOGRAFIA", "value": "...", "field_type": "string"},
    ])

    out = normalize_fd_fields(doc)
    keys = {f.key for f in out.fields}
    assert "titularul_activitatilor_de_curs" in keys
    assert "bibliografie" in keys


def test_unknown_keys_preserved():
    doc = _make_doc([
        {"key": "denumirea_disciplinei", "value": "X", "field_type": "string"},
        {"key": "some_random_extra_field", "value": "v", "field_type": "string"},
    ])

    out = normalize_fd_fields(doc)
    keys = {f.key for f in out.fields}
    assert "some_random_extra_field" in keys


def test_already_canonical_doc_is_idempotent():
    doc = _make_doc([
        {"key": "denumirea_disciplinei", "value": "Analiză", "field_type": "string"},
        {"key": "titularul_activitatilor_de_curs", "value": "Lect.", "field_type": "string"},
        {"key": "anul_de_studiu", "value": 1.0, "field_type": "number"},
        {"key": "semestrul", "value": 1.0, "field_type": "number"},
        {"key": "numarul_de_credite", "value": 5.0, "field_type": "number"},
    ])

    out = normalize_fd_fields(doc)
    out2 = normalize_fd_fields(out)
    assert [f.model_dump() for f in out.fields] == [f.model_dump() for f in out2.fields]
    by_key = {f.key: f.value for f in out.fields}
    assert by_key["anul_de_studiu"] == 1.0
    assert by_key["numarul_de_credite"] == 5.0


def test_non_fd_document_untouched():
    doc = _make_doc(
        [{"key": "angajator", "value": "X", "field_type": "string"}],
        document_type="contract_de_munca",
    )
    out = normalize_fd_fields(doc)
    # No FD signature in document_type, no canonical FD keys in fields
    # → untouched.
    assert out.fields[0].key == "angajator"


def test_duplicate_aliases_first_wins():
    doc = _make_doc([
        {"key": "titular_curs", "value": "First", "field_type": "string"},
        {"key": "titularul_cursului", "value": "Second", "field_type": "string"},
    ])
    out = normalize_fd_fields(doc)
    matches = [f for f in out.fields if f.key == "titularul_activitatilor_de_curs"]
    assert len(matches) == 1
    assert matches[0].value == "First"


def test_looks_like_fd_by_document_type():
    doc = _make_doc([], document_type="Fisa Disciplinei")
    assert looks_like_fd(doc)


def test_looks_like_fd_by_field_signature():
    doc = _make_doc(
        [{"key": "denumirea_disciplinei", "value": "X", "field_type": "string"}],
        document_type="form",
    )
    assert looks_like_fd(doc)
