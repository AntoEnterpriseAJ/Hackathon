"""End-to-end test: fast parsers feed cross-validator and surface the
expected credits_mismatch (FD says 6 credits, PI lists 5)."""
from __future__ import annotations

from pathlib import Path

from services.cross_doc_validator import cross_validate
from services.fd_bundle_splitter import split_fd_bundle
from services.fd_fast_parser import parse_fd
from services.pi_fast_parser import parse_pi


_DATA = Path(__file__).resolve().parent.parent / "mock-data"


def test_fast_path_surfaces_credits_mismatch_for_ia_analiza_matematica():
    fd_bundle = (_DATA / "pdf-ia-matching/FD_RO_IA_I.pdf").read_bytes()
    pi_bytes = (_DATA / "pdf-ia-matching/PI_Informatica_aplicata_2025_2028.pdf").read_bytes()

    slices = split_fd_bundle(fd_bundle)
    fd_doc = parse_fd(slices[0].pdf_bytes)
    pi_doc = parse_pi(pi_bytes)

    assert fd_doc is not None
    assert pi_doc is not None

    result = cross_validate(fd=fd_doc, plan=pi_doc)

    codes = [v.code for v in result.field_violations] + [
        v.code for v in result.competency_violations
    ]
    # Cross-validator should at minimum locate the course and report a credits mismatch.
    assert "credits_mismatch" in codes, f"expected credits_mismatch in {codes}"
