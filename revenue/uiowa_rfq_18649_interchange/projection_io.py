"""Non-authoritative document readers retained for the existing UIOWA CLI.

Paragraph/PDF text is useful to readers but is never an assessment import.
The byte-only PDF fallback does not assert that the bytes form a valid PDF.
"""
from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

try:
    from .transport import InterchangeError
except ImportError:
    from transport import InterchangeError


def project_docx(path):
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 64 * 1024 * 1024:
                raise InterchangeError("DOCX document part exceeds supported 64 MiB")
            xml = archive.read(info)
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise InterchangeError("DOCX document cannot contain DTD/entity declarations")
        root = ET.fromstring(xml)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, OSError) as exc:
        raise InterchangeError(f"docx unreadable: {exc}") from exc
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(w + "p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == w + "t":
                parts.append(node.text or "")
            elif node.tag == w + "tab":
                parts.append("\t")
            elif node.tag in (w + "br", w + "cr"):
                parts.append("\n")
        text = "".join(parts)
        if text:
            paragraphs.append(text)
    return {"schema": "uiowa.interchange.docx-projection.v1", "source": path.name,
            "status": "partial" if paragraphs else "unreadable",
            "warnings": ["DOCX projection is paragraph text only; layout and page numbers are unknown."],
            "paragraphs": paragraphs, "authority": "none", "assessment": "not_elevated"}


def project_pdf(path):
    path = Path(path)
    # Keep the historical return shape and explicit non-authority. A successful
    # parser is distinguishable from missing dependency or malformed bytes.
    size = path.stat().st_size
    result = {"schema": "uiowa.interchange.pdf-projection.v1", "source": path.name,
              "status": "unknown_text", "bytes": size, "text": "",
              "warnings": ["PDF projection does not perform OCR."],
              "authority": "none", "assessment": "not_elevated"}
    try:
        from pypdf import PdfReader
    except ImportError:
        result["warnings"].append("PDF text is unknown: optional pypdf dependency is unavailable.")
        return result
    try:
        reader = PdfReader(path)
        result["text"] = "\n".join(page.extract_text() or "" for page in reader.pages)
        result["pages"] = len(reader.pages)
        result["status"] = "text_extracted" if result["text"] else "unknown_text"
        result["warnings"].append("Extracted text is a reader projection; layout, ordering and source authority are not verified.")
    except Exception as exc:
        result["warnings"].append(f"PDF text is unknown: parser reported {type(exc).__name__}.")
    return result
