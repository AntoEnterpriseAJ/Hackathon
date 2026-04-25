"""Map sections from an old FD docx onto slots in a new template docx.

Pass 1 — deterministic exact + rapidfuzz token_sort_ratio (>= 88).
Pass 2 — single Claude call for any leftovers; failures fall back to
a placeholder confidence.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from rapidfuzz import fuzz

from services.docx_section_extractor import Section

LOGGER = logging.getLogger(__name__)

FUZZY_THRESHOLD = 88
LLM_BATCH_CAP = 30

Confidence = Literal[
    "exact", "fuzzy", "llm-high", "llm-medium", "llm-low", "placeholder"
]


@dataclass
class SectionMatch:
    new_section_id: str
    old_section_id: Optional[str]
    confidence: Confidence
    rationale: Optional[str] = None


ClaudeCallable = Callable[[str], str]


def map_sections(
    old: list[Section],
    new: list[Section],
    claude: Optional[ClaudeCallable],
) -> list[SectionMatch]:
    matches: list[SectionMatch] = []
    used_old: set[str] = set()

    for new_sec in new:
        match = _deterministic_match(new_sec, old, used_old)
        if match is None:
            matches.append(
                SectionMatch(
                    new_section_id=new_sec.id,
                    old_section_id=None,
                    confidence="placeholder",
                )
            )
        else:
            matches.append(match)

    unmatched_new_ids = {
        m.new_section_id for m in matches if m.confidence == "placeholder"
    }
    unmatched_new = [s for s in new if s.id in unmatched_new_ids]
    unmatched_old = [s for s in old if s.id not in used_old]

    if unmatched_new and unmatched_old and claude is not None:
        llm_matches = _llm_match(unmatched_new, unmatched_old, claude)
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
) -> Optional[SectionMatch]:
    target = new_sec.heading_norm
    if not target:
        return None

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

    best_score = 0.0
    best_old: Optional[Section] = None
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
    payload = _build_prompt(
        unmatched_new[:LLM_BATCH_CAP], unmatched_old[:LLM_BATCH_CAP]
    )
    try:
        raw = claude(payload)
        decisions = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — defensive: any failure → placeholders
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
        if old_id is None:
            confidence: Confidence = "placeholder"
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
