"""
Render document pages to base64-encoded PNG strings for Claude Vision.
Works for both scanned PDFs and raw image files (TIFF, BMP, JPEG, PNG).
No temp files — everything is processed in memory.
"""
import base64
import pathlib

import pymupdf

_MAX_PAGES = 20
_RENDER_DPI = 150

# PyMuPDF filetype hints for common image extensions
_EXT_REMAP: dict[str, str] = {"jpg": "jpeg", "tif": "tiff"}


def extract_page_images(file_bytes: bytes, filename: str, *, is_pdf: bool) -> list[str]:
    """
    Convert a PDF or image file into a list of base64-encoded PNG strings.

    For PDFs:   renders up to _MAX_PAGES pages.
    For images: renders the single image as one page.

    Args:
        file_bytes: Raw file bytes.
        filename:   Original filename, used to infer filetype for non-PDFs.
        is_pdf:     True if the file is a PDF; False for image files.

    Returns:
        List of base64-encoded PNG strings, one per page/image.
    """
    if is_pdf:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    else:
        ext = pathlib.Path(filename).suffix.lstrip(".").lower()
        filetype = _EXT_REMAP.get(ext, ext) or "png"
        doc = pymupdf.open(stream=file_bytes, filetype=filetype)

    images: list[str] = []
    for i in range(min(doc.page_count, _MAX_PAGES)):
        pix = doc[i].get_pixmap(dpi=_RENDER_DPI)
        png_bytes = pix.tobytes("png")
        images.append(base64.standard_b64encode(png_bytes).decode("utf-8"))

    doc.close()
    return images
