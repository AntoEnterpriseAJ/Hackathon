"""Tests for services.template_section_mapper."""
from __future__ import annotations

from services.docx_section_extractor import (
    Section,
    TextBlock,
    _new_section,
)
from services.template_section_mapper import map_sections


def _sec(pos: int, heading: str, body: str = "") -> Section:
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
    # Same words, slight reorder + diacritics — well above the 88 threshold.
    old = [_sec(0, "8.1 Tematica activitatilor de curs")]
    new = [_sec(0, "8.1 Tematica de curs activitatilor")]

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

    def fake(_payload):
        return (
            '[{"new_id": "%s", "old_id": "%s", "confidence": "high", "rationale": "renamed"}]'
            % (new[0].id, old[0].id)
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
