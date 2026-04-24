"""
Central configuration — reads .env and resolves plugin implementations.
To add a new extractor/parser/differ/analyzer, register it in the
corresponding REGISTRY dict and set the env var.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Plugin registries — add new implementations here
# ---------------------------------------------------------------------------

EXTRACTOR_REGISTRY: dict[str, str] = {
    "pdfplumber": "app.extractors.pdfplumber_extractor.PdfPlumberExtractor",
}

PARSER_REGISTRY: dict[str, str] = {
    "fd": "app.parsers.fd_parser.FDSectionParser",
    "pi": "app.parsers.pi_parser.PISectionParser",
}

DIFFER_REGISTRY: dict[str, str] = {
    "difflib": "app.differs.difflib_differ.DifflibDiffer",
}

ANALYZER_REGISTRY: dict[str, str] = {
    "regex": "app.analyzers.regex_analyzer.RegexAnalyzer",
}

# ---------------------------------------------------------------------------
# Active selections
# ---------------------------------------------------------------------------

ACTIVE_EXTRACTOR = os.getenv("EXTRACTOR", "pdfplumber")
ACTIVE_PARSER = os.getenv("PARSER", "fd")
ACTIVE_DIFFER = os.getenv("DIFFER", "difflib")
ACTIVE_ANALYZER = os.getenv("ANALYZER", "regex")

FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")
]


def _import_class(dotted_path: str):
    """Dynamically import a class from a dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_extractor():
    cls = _import_class(EXTRACTOR_REGISTRY[ACTIVE_EXTRACTOR])
    return cls()


def get_parser():
    cls = _import_class(PARSER_REGISTRY[ACTIVE_PARSER])
    return cls()


def get_differ():
    cls = _import_class(DIFFER_REGISTRY[ACTIVE_DIFFER])
    return cls()


def get_analyzer():
    cls = _import_class(ANALYZER_REGISTRY[ACTIVE_ANALYZER])
    return cls()
