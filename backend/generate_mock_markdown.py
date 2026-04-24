"""
Regenerate paired .md files for each PDF in mock-data/ using the same
Claude pipeline that the /parse endpoint uses.

Usage (from backend/ with venv active):
    python generate_mock_markdown.py

Output:
    mock-data/fisa_disciplina.parsed.md
    mock-data/plan_invatamant.full.parsed.md
"""
import os
import sys
import pathlib

# Make sure the backend package root is on the path when run directly.
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent / ".env")

from services import pdf_router, scan_extractor, text_extractor
from services.claude_service import (
    generate_markdown_from_text,
    generate_markdown_from_images,
    generate_markdown_from_images_paged,
)

MOCK_DIR = pathlib.Path(__file__).parent / "mock-data"

TARGETS = [
    {
        "pdf":    MOCK_DIR / "fisa_disciplina-1-7.pdf",
        "output": MOCK_DIR / "fisa_disciplina.parsed.md",
    },
    {
        "pdf":    MOCK_DIR / "plan_invatamant.pdf",
        "output": MOCK_DIR / "plan_invatamant.full.parsed.md",
    },
]


def generate(pdf_path: pathlib.Path, output_path: pathlib.Path) -> None:
    print(f"\n→ {pdf_path.name}")
    file_bytes = pdf_path.read_bytes()
    route = pdf_router.detect_route(file_bytes)
    print(f"  route: {route}")

    if route == "text_pdf":
        text = text_extractor.extract_text(file_bytes)
        markdown = generate_markdown_from_text(text)
    else:
        num_pages = scan_extractor.count_pdf_pages(file_bytes)
        print(f"  pages: {num_pages}")
        if num_pages > scan_extractor._PAGE_BATCH_THRESHOLD:
            markdown = generate_markdown_from_images_paged(file_bytes)
        else:
            page_images = scan_extractor.extract_page_images(
                file_bytes, pdf_path.name, is_pdf=True
            )
            markdown = generate_markdown_from_images(page_images)

    output_path.write_text(markdown, encoding="utf-8")
    print(f"  ✓ written → {output_path.name}")


if __name__ == "__main__":
    for target in TARGETS:
        if not target["pdf"].exists():
            print(f"  ✗ PDF not found: {target['pdf']} — skipping")
            continue
        generate(target["pdf"], target["output"])

    print("\nDone.")
