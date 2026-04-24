"""API routes for diff operations."""

from flask import Blueprint, request, jsonify
import importlib

from config import (
    EXTRACTOR_REGISTRY, PARSER_REGISTRY, DIFFER_REGISTRY, ANALYZER_REGISTRY,
    ACTIVE_EXTRACTOR, ACTIVE_PARSER, ACTIVE_DIFFER, ACTIVE_ANALYZER,
    FLASK_DEBUG
)
from app.models.response import DiffResponse, DiffSummary

diff_bp = Blueprint("diff", __name__, url_prefix="/api/diff")


def _load_implementation(registry: dict, active_type: str):
    """Dynamically load an implementation class."""
    if active_type not in registry:
        raise ValueError(f"Unknown type: {active_type}. Available: {list(registry.keys())}")
    
    dotted_path = registry[active_type]
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


@diff_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "debug": FLASK_DEBUG}, 200


@diff_bp.route("/", methods=["POST"])
def diff_documents():
    """
    Compare two PDF documents.
    
    Expects multipart/form-data with:
    - file_old: first PDF file
    - file_new: second PDF file
    - parser_type (optional): "fd" or "pi" (default: "fd")
    
    Returns JSON with section diffs and logic changes.
    """
    try:
        # Check files
        if "file_old" not in request.files or "file_new" not in request.files:
            return {"error": "Missing files: file_old, file_new"}, 400
        
        file_old = request.files["file_old"]
        file_new = request.files["file_new"]
        
        if file_old.filename == "" or file_new.filename == "":
            return {"error": "Empty filenames"}, 400
        
        # Get parser type from request or use default
        parser_type = request.form.get("parser_type", ACTIVE_PARSER)
        if parser_type not in PARSER_REGISTRY:
            return {
                "error": f"Unknown parser_type: {parser_type}. Available: {list(PARSER_REGISTRY.keys())}"
            }, 400
        
        # Load implementations
        extractor = _load_implementation(EXTRACTOR_REGISTRY, ACTIVE_EXTRACTOR)
        parser = _load_implementation(PARSER_REGISTRY, parser_type)
        differ = _load_implementation(DIFFER_REGISTRY, ACTIVE_DIFFER)
        analyzer = _load_implementation(ANALYZER_REGISTRY, ACTIVE_ANALYZER)
        
        # Extract
        old_pages = extractor.extract(file_old.stream)
        new_pages = extractor.extract(file_new.stream)
        
        # Parse
        old_sections = parser.parse(old_pages)
        new_sections = parser.parse(new_pages)
        
        # Diff
        section_diffs = differ.diff(old_sections, new_sections)
        
        # Analyze
        logic_changes = analyzer.analyze(old_sections, new_sections, section_diffs)
        
        # Build response
        summary = DiffSummary(
            total_sections=len(set(old_sections.keys()) | set(new_sections.keys())),
            modified=sum(1 for s in section_diffs if s.status == "modified"),
            added=sum(1 for s in section_diffs if s.status == "added"),
            removed=sum(1 for s in section_diffs if s.status == "removed"),
            unchanged=sum(1 for s in section_diffs if s.status == "equal"),
            logic_changes_count=len(logic_changes)
        )
        
        response = DiffResponse(
            sections=section_diffs,
            logic_changes=logic_changes,
            summary=summary
        )
        
        return response.to_dict(), 200
    except ValueError as e:
        # Expected input/data errors should be surfaced as client errors.
        return {"error": str(e)}, 400
    
    except Exception as e:
        if FLASK_DEBUG:
            import traceback
            traceback.print_exc()
        return {"error": str(e)}, 500
