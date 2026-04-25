"""Integration tests for POST /api/documents/cross-validate using real mock data.

Drives the FastAPI app through TestClient (no live server required) and uses
the parsed JSON in backend/mock-data/ as the FD ↔ Plan pair the validator
must reason about end-to-end.
"""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
MOCK_DIR = Path(__file__).resolve().parent.parent / "mock-data"


@pytest.fixture(scope="module")
def fd_payload() -> dict:
    return json.loads((MOCK_DIR / "fisa_disciplina.parsed.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plan_payload() -> dict:
    return json.loads((MOCK_DIR / "plan_invatamant.full.parsed.json").read_text(encoding="utf-8"))


def _post(fd: dict, plan: dict) -> dict:
    response = client.post(
        "/api/documents/cross-validate",
        json={"fd": fd, "plan": plan},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_real_mock_pair_is_invalid_with_known_violations(fd_payload, plan_payload) -> None:
    """The bundled mock pair has two real extraction inconsistencies.

    Asserts the demo case the UI relies on:
      - credits_mismatch: FD says 6, Plan says 5
      - competency_not_in_plan: CP4 is in FD but missing from Plan
    """
    body = _post(fd_payload, plan_payload)

    assert body["status"] == "invalid"
    assert body["fd_course_name"] == "Analiză matematică"

    plan_match = body["plan_match"]
    assert plan_match is not None
    assert plan_match["course_code"] == "APO01-ID"
    assert plan_match["credits"] == 5.0

    field_codes = [v["code"] for v in body["field_violations"]]
    assert "credits_mismatch" in field_codes

    comp_codes = [v["code"] for v in body["competency_violations"]]
    assert "competency_not_in_plan" in comp_codes
    cp_violation = next(
        v for v in body["competency_violations"] if v["code"] == "competency_not_in_plan"
    )
    assert "CP4" in cp_violation["fields"]


def test_patched_mock_pair_is_valid(fd_payload, plan_payload) -> None:
    """Same FD with credits=5 and CP4→CP1 should produce a clean (valid) result."""
    fd_fixed = copy.deepcopy(fd_payload)

    # Patch credits 6 → 5 in the field list
    for field in fd_fixed.get("fields", []):
        if field.get("key") == "numarul_de_credite":
            field["value"] = 5.0

    # Replace CP 4 references with CP 1 (which exists in the plan)
    def _scrub(node):
        if isinstance(node, dict):
            return {k: _scrub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_scrub(item) for item in node]
        if isinstance(node, str):
            return node.replace("CP 4", "CP 1").replace("CP4", "CP1")
        return node

    fd_fixed = _scrub(fd_fixed)

    body = _post(fd_fixed, plan_payload)

    assert body["status"] == "valid", body.get("summary")
    assert body["field_violations"] == []
    assert body["competency_violations"] == []


def test_unrelated_fd_returns_no_match(plan_payload) -> None:
    """An FD whose course_name is not in the plan should yield status=no_match."""
    bogus_fd = {
        "document_type": "form",
        "summary": "Synthetic FD for an unknown course",
        "fields": [
            {
                "key": "denumirea_disciplinei",
                "value": "Curs Inexistent În Plan XYZ",
                "field_type": "string",
                "confidence": "high",
            },
            {
                "key": "numarul_de_credite",
                "value": 5.0,
                "field_type": "number",
                "confidence": "high",
            },
        ],
        "tables": [],
        "source_route": "text_pdf",
    }

    body = _post(bogus_fd, plan_payload)

    assert body["status"] == "no_match"
    assert body["plan_match"] is None or body["plan_match"].get("match_confidence") == "none"


def test_invalid_payload_returns_422() -> None:
    """Missing 'fd' field should be a Pydantic 422, not a 500."""
    response = client.post(
        "/api/documents/cross-validate",
        json={"plan": {}},
    )
    assert response.status_code == 422
