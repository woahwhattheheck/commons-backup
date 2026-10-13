"""Read explicitly embedded JSON from recovered reader documents.

Recovered from the KESTREL-I96 contribution and composed with the canonical
transport's strict JSON semantics. Never infer records from edited prose,
worksheet views or page text; payload consistency is not source authenticity.
"""
from __future__ import annotations
import base64
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from . import transport as t
except ImportError:
    import transport as t

InterchangeError = t.InterchangeError
SCHEMA = "uiowa-rfq18649-interchange/v1"
DOC_PART = "customXml/uiowa-interchange.xml"
PDF_ATTACHMENT = "uiowa-interchange.json"
MAX_BYTES = 16 * 1024 * 1024
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _load_payload(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise InterchangeError("Embedded JSON exceeds 16 MiB")
    return t.loads(raw.decode("utf-8"))

def _read_part(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
        if info.file_size > MAX_BYTES:
            raise InterchangeError(f"Oversized document part: {name}")
        return archive.read(name)
    except KeyError as exc:
        raise InterchangeError(f"Missing document part: {name}") from exc

def _xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise InterchangeError("Document type/entity declarations are not supported")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise InterchangeError(f"Invalid document XML: {exc}") from exc

def read_xlsx_cells(path: str | Path, sheet_name: str) -> dict[str, str]:
    """Read existing OOXML cells for verification only; no spreadsheet edits."""
    with zipfile.ZipFile(path) as archive:
        book = _xml(_read_part(archive, "xl/workbook.xml"))
        sheet = next((s for s in book.findall("s:sheets/s:sheet", NS) if s.get("name") == sheet_name), None)
        if sheet is None:
            raise InterchangeError(f"Missing worksheet {sheet_name}")
        rel_id = sheet.get("{" + NS["r"] + "}id")
        relationships = _xml(_read_part(archive, "xl/_rels/workbook.xml.rels"))
        rel = next((r for r in relationships if r.get("Id") == rel_id), None)
        if rel is None or rel.get("TargetMode") == "External":
            raise InterchangeError("Invalid worksheet relationship")
        target = rel.get("Target", "")
        name = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in name.split("/"):
            raise InterchangeError("Unexpected worksheet path")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(t.text or "" for t in item.findall(".//s:t", NS))
                       for item in _xml(_read_part(archive, "xl/sharedStrings.xml"))]
        result = {}
        for cell in _xml(_read_part(archive, name)).findall(".//s:sheetData/s:row/s:c", NS):
            if cell.find("s:f", NS) is not None and sheet_name == "Canonical":
                raise InterchangeError("Formula found in canonical payload sheet")
            kind = cell.get("t")
            value = cell.findtext("s:v", default="", namespaces=NS)
            if kind == "s":
                try:
                    value = strings[int(value)]
                except (ValueError, IndexError) as exc:
                    raise InterchangeError("Invalid shared string reference") from exc
            elif kind == "inlineStr":
                value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
            result[cell.get("r", "")] = value
        return result

def load_xlsx(path: str | Path) -> dict[str, Any]:
    cells = read_xlsx_cells(path, "Canonical")
    if cells.get("A1") != SCHEMA:
        raise InterchangeError("Unknown canonical worksheet schema")
    try:
        count = int(cells.get("B3", ""))
    except ValueError as exc:
        raise InterchangeError("Invalid payload chunk count") from exc
    if not 1 <= count <= 10000:
        raise InterchangeError("Invalid payload chunk count")
    chunks = []
    for i in range(count):
        value = cells.get(f"B{i+5}", "")
        if not value.startswith("b64:") or cells.get(f"A{i+5}") != str(i):
            raise InterchangeError("Missing, reordered or invalid canonical chunk")
        chunks.append(value[4:])
    try:
        raw = base64.b64decode("".join(chunks), validate=True)
    except ValueError as exc:
        raise InterchangeError("Invalid base64 payload") from exc
    bundle = _load_payload(raw)
    if cells.get("B2") != t.document_sha256(bundle):
        raise InterchangeError("Canonical worksheet digest mismatch")
    # Review views are not accepted as edited machine source. Roundtrip is from
    # this explicit sheet only; renderer / Office edits require separate review.
    return bundle

def load_docx(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        root = _xml(_read_part(archive, DOC_PART))
    if root.tag != "uiowa-interchange" or root.get("encoding") != "base64-utf8-json":
        raise InterchangeError("Unsupported DOCX canonical payload")
    try:
        raw = base64.b64decode(root.text or "", validate=True)
    except ValueError as exc:
        raise InterchangeError("Invalid DOCX payload encoding") from exc
    bundle = _load_payload(raw)
    if root.get("sha256") != t.document_sha256(bundle):
        raise InterchangeError("DOCX canonical payload digest mismatch")
    return bundle

def load_pdf(path: str | Path) -> dict[str, Any]:
    from pypdf import PdfReader
    values = PdfReader(str(path)).attachments.get(PDF_ATTACHMENT, [])
    if len(values) != 1:
        raise InterchangeError("Expected one explicit canonical JSON attachment")
    return _load_payload(values[0])

def read_embedded(path: str | Path) -> Any:
    """Read the disclosed payload only; ordinary projections are not imports."""
    path = Path(path)
    readers = {".xlsx": load_xlsx, ".docx": load_docx, ".pdf": load_pdf}
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise InterchangeError("Embedded input must be XLSX, DOCX or PDF")
    try:
        return reader(path)
    except InterchangeError:
        raise
    except Exception as exc:
        raise InterchangeError(f"Embedded payload unreadable: {type(exc).__name__}: {exc}") from exc
