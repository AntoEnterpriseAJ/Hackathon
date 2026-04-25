"""
Diff narrative explainer — takes a DiffResponse from diff-service and asks
Claude to produce a plain-Romanian summary aimed at a professor.

This is the L5 "Delta Report" from the brief: turn structured diffs into
human-readable explanations of what changed and what the user should do.
"""
from __future__ import annotations

from typing import Any

from services import claude_service


_SYSTEM_PROMPT = (
    "Ești un asistent academic care raportează schimbările dintre două versiuni "
    "ale unui document academic românesc (Fișa Disciplinei sau Plan de Învățământ). "
    "Scrii în română, telegrafic și factual.\n\n"
    "REGULI ABSOLUTE — Încalcarea oricăreia face raportul inutil:\n"
    "1. FIECARE bullet din key_changes ȘI action_items TREBUIE să înceapă cu "
    "numele exact al secțiunii din date, între paranteze drepte. Format obligatoriu: "
    "'[Nume secțiune] <descriere schimbare>'. "
    "Folosește numele exact din câmpul 'Secțiune:' din input.\n"
    "2. Când raportezi un procent sau număr, spune EXPLICIT la ce componentă "
    "se referă (curs, seminar, laborator, examen final, examen parțial, temă, etc.) "
    "— nu folosi termeni vagi ca 'evaluare' sau 'pondere'.\n"
    "3. Când raportezi o referință bibliografică adăugată/eliminată, spune în "
    "ce secțiune (ex. 'Bibliografie curs', 'Bibliografie seminar').\n"
    "4. Niciun adjectiv inutil, nicio introducere, nicio concluzie. Doar fapte.\n"
    "5. Ignoră schimbările pur cosmetice (spații, majuscule, ordine de cuvinte).\n"
    "6. Dacă nu există schimbări semnificative, spune asta într-o singură propoziție.\n\n"
    "EXEMPLE GREȘITE (NU folosi acest stil):\n"
    "  ✗ 'Evaluare curs: 67% → 50%'\n"
    "  ✗ 'Pondere notă finală: 100% → 25%'\n"
    "  ✗ 'Adăugat: referință bibliografică .NET documentation'\n\n"
    "EXEMPLE CORECTE (folosește acest stil):\n"
    "  ✓ '[10. Evaluare] Examen final: 67% → 50%'\n"
    "  ✓ '[10. Evaluare] Activitate seminar: 0% → 25% (nou)'\n"
    "  ✓ '[8.2 Bibliografie curs] Adăugat: .NET documentation, Microsoft Corporation'"
)


def explain_diff(diff_response: dict[str, Any]) -> dict[str, Any]:
    """Generate a narrative explanation of a DiffResponse.

    Returns a dict with:
      - narrative: str (full plain-Romanian summary)
      - key_changes: list[str] (bullet-pointed important changes)
      - action_items: list[str] (things the professor must address)
    """
    summary_block = _format_diff_for_prompt(diff_response)

    user_message = (
        "Mai jos este rezultatul comparației dintre două versiuni ale unui "
        "document academic. Generează un raport explicativ în română.\n\n"
        f"{summary_block}\n\n"
        "Returnează rezultatul folosind tool-ul 'explain_document_diff'."
    )

    response = claude_service._get_client().messages.create(
        model=claude_service._MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_EXPLAIN_TOOL],
        tool_choice={"type": "tool", "name": "explain_document_diff"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return _coerce_explain_payload(dict(block.input))  # type: ignore[union-attr]

    raise RuntimeError("Claude did not return a tool_use block for explain_diff.")


def _coerce_explain_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Defensively normalize Claude's tool_use output.

    Claude occasionally returns ``key_changes`` / ``action_items`` as a single
    JSON-encoded string (``'["a", "b"]'``) instead of a real list. Pydantic
    rejects that with ``list_type``. Detect and recover.
    """
    import json as _json

    for key in ("key_changes", "action_items"):
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = _json.loads(stripped)
                    if isinstance(parsed, list):
                        payload[key] = [str(x) for x in parsed]
                        continue
                except _json.JSONDecodeError:
                    pass
            # Last-resort: split on newlines into list items.
            payload[key] = [
                line.strip(" -•\t") for line in stripped.splitlines() if line.strip()
            ]
        elif value is None:
            payload[key] = []
        elif isinstance(value, list):
            payload[key] = [str(x) for x in value]

    if not isinstance(payload.get("narrative"), str):
        payload["narrative"] = str(payload.get("narrative") or "")

    return payload


_EXPLAIN_TOOL: dict = {
    "name": "explain_document_diff",
    "description": (
        "Produce a Romanian-language narrative explaining the changes between "
        "two versions of an academic document, plus key changes and action items."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {
                "type": "string",
                "description": (
                    "MAXIM 2 propoziții scurte (sub 40 de cuvinte total) care rezumă "
                    "ce s-a schimbat. Fără introduceri, fără 'aȜi avut', fără saluturi. "
                    "Doar faptul. Exemplu: 'Examenul final a scăzut de la 70% la 60%. "
                    "S-au adăugat 3 teme noi de laborator.'"
                ),
            },
            "key_changes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-7 puncte. FIECARE bullet TREBUIE să înceapă cu numele exact al "
                    "secțiunii între paranteze drepte: '[Nume secțiune] <schimbare>'. "
                    "FIECARE valoare numerică trebuie să spună la ce componentă se referă "
                    "(curs / seminar / laborator / examen final / etc.). "
                    "Exemplu CORECT: '[10. Evaluare] Examen final: 67% → 50%'. "
                    "Exemplu GREȘIT: 'Evaluare curs: 67% → 50%'."
                ),
            },
            "action_items": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Doar acțiuni concrete. FIECARE începe cu '[Nume secțiune]' și "
                    "identifică explicit componenta afectată. Imperativ. Sub 22 cuvinte. "
                    "Exemplu: '[10. Evaluare] Redistribuiți 17% scoase din examenul final "
                    "la activitatea de seminar'. Listă goală dacă nu e nimic de făcut."
                ),
            },
        },
        "required": ["narrative", "key_changes", "action_items"],
    },
}


def _format_diff_for_prompt(diff: dict[str, Any]) -> str:
    # Prompt budgets — keep the LLM input bounded so adding a 200-entry
    # bibliography to a diff doesn't blow past Claude's input token limit.
    MAX_SECTIONS = 20            # at most 20 changed sections in the prompt
    MAX_LINES_PER_SECTION = 30   # at most 30 emitted lines per section
    MAX_LINE_CHARS = 240         # truncate any single line beyond this
    MAX_TOTAL_CHARS = 60_000     # hard ceiling on the whole prompt body

    def _trim(text: str) -> str:
        text = text.strip()
        return text if len(text) <= MAX_LINE_CHARS else text[: MAX_LINE_CHARS - 1] + "…"

    parts: list[str] = []

    summary = diff.get("summary") or {}
    if summary:
        parts.append(
            "REZUMAT NUMERIC:\n"
            f"  - Total secțiuni: {summary.get('total_sections', '?')}\n"
            f"  - Modificate: {summary.get('modified', 0)}\n"
            f"  - Adăugate: {summary.get('added', 0)}\n"
            f"  - Eliminate: {summary.get('removed', 0)}\n"
            f"  - Neschimbate: {summary.get('unchanged', 0)}\n"
            f"  - Schimbări de logică: {summary.get('logic_changes_count', 0)}"
        )

    logic_changes = diff.get("logic_changes") or []
    if logic_changes:
        parts.append("\nSCHIMBĂRI DE LOGICĂ DETECTATE:")
        for lc in logic_changes:
            parts.append(
                f"  • [{lc.get('severity', 'info')}] {lc.get('type', '?')} "
                f"în secțiunea '{lc.get('section', '?')}': "
                f"{lc.get('old_value', '?')} → {lc.get('new_value', '?')}. "
                f"{lc.get('description', '')}"
            )

    sections = diff.get("sections") or []
    modified_sections = [s for s in sections if s.get("status") in {"modified", "added", "removed"}]
    truncated_sections = 0
    if len(modified_sections) > MAX_SECTIONS:
        truncated_sections = len(modified_sections) - MAX_SECTIONS
        modified_sections = modified_sections[:MAX_SECTIONS]
    if modified_sections:
        parts.append("\nSECȚIUNI MODIFICATE/ADĂUGATE/ELIMINATE:")
        for sec in modified_sections:
            name = sec.get("name", "?")
            status = sec.get("status", "?")
            parts.append(f"\n  Secțiune: '{name}' [{status}]")
            # Emit changes with surrounding context lines so the LLM can see
            # table row labels / headers that immediately precede a numeric change.
            all_lines = sec.get("lines") or []
            change_idx = {
                i for i, ln in enumerate(all_lines)
                if ln.get("type") in {"remove", "add", "replace"}
            }
            keep_idx = set(change_idx)
            for i in change_idx:
                for j in (i - 2, i - 1, i + 1, i + 2):
                    if 0 <= j < len(all_lines):
                        keep_idx.add(j)
            emitted = 0
            prev_i = -2
            for i in sorted(keep_idx):
                if emitted >= MAX_LINES_PER_SECTION:
                    parts.append("    ... (restul liniilor omise)")
                    break
                if i > prev_i + 1:
                    parts.append("    ...")
                line = all_lines[i]
                t = line.get("type", "?")
                old_t = _trim(line.get("old_text") or "")
                new_t = _trim(line.get("new_text") or "")
                if t == "remove":
                    parts.append(f"    - {old_t}")
                elif t == "add":
                    parts.append(f"    + {new_t}")
                elif t == "replace":
                    parts.append(f"    - {old_t}")
                    parts.append(f"    + {new_t}")
                else:  # equal / context
                    ctx = (new_t or old_t)
                    if ctx:
                        parts.append(f"      {ctx}")
                prev_i = i
                emitted += 1
        if truncated_sections:
            parts.append(
                f"\n  ... ({truncated_sections} secțiuni modificate suplimentare omise)"
            )

    if not parts:
        return "Diferența nu conține modificări semnificative."

    body = "\n".join(parts)
    if len(body) > MAX_TOTAL_CHARS:
        body = body[:MAX_TOTAL_CHARS] + "\n... (raport trunchiat — prea multe schimbări)"
    return body
