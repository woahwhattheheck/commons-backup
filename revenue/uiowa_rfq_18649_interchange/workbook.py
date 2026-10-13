"""Styled XLSX transport through artifact_tool; stdlib reader for the transport sheet.

The workbook's Guide explains that Reader is a projection, not an input surface.
The importer checks Reader against Transport so edits are never silently ignored.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

try:
    from . import transport as t
except ImportError:
    import transport as t

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
PACKAGE_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
LIMIT = 32767
OOXML_ESCAPE = re.compile(r"_x[0-9A-Fa-f]{4}_")


def _xml_safe_json(text: str) -> str:
    """Keep literal escape-looking strings as JSON escapes, not OOXML escapes."""
    text = re.sub(r"_(?=x[0-9A-Fa-f]{4}_)", lambda m: r"\u005f", text)
    return text.replace("\ufffe", r"\ufffe").replace("\uffff", r"\uffff")


def _needs_escape(text: str) -> bool:
    return (any(ord(c) < 32 or c in "\ufffe\uffff" for c in text)
            or bool(OOXML_ESCAPE.search(text)))


def xlsx_rows(document: Any) -> list[list[str]]:
    """The same JSON literals, with XML-sensitive spellings escaped in JSON."""
    return [[_xml_safe_json(cell) for cell in row] for row in t.to_rows(document)]


def _decode_ooxml(text: str) -> str:
    # One pass is critical: _x005F_x0041_ names literal _x0041_, not A.
    decoded = OOXML_ESCAPE.sub(lambda m: chr(int(m[0][2:6], 16)), text)
    try:
        return decoded.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeError as exc:
        raise t.InterchangeError("unpaired surrogate in XLSX string") from exc


def display_rows(document: Any) -> list[list[str]]:
    rows = [["JSON pointer", "JSON type", "Reader value (not editable input)"]]
    for pointer, kind, literal in t.to_rows(document)[2:]:
        location, value = t.loads(pointer[2:]), t.loads(literal[2:])
        if kind in ("object", "array"):
            display = f"{value} member(s)" if kind == "object" else f"{value} item(s)"
        elif kind == "null":
            display = "NULL (present, no value)"
        elif kind == "string":
            if value == "":
                display = 'EMPTY STRING ("")'
            elif _needs_escape(value):
                display = "JSON string: " + _xml_safe_json(json.dumps(value, ensure_ascii=False))
            else:
                display = "Text: " + value
        else:
            display = kind + ": " + t.canonical_json(value)
        safe_location = (_xml_safe_json(json.dumps(location, ensure_ascii=False))
                         if _needs_escape(location) else location)
        rows.append(["Path: " + (safe_location or "<root>"), kind, display])
    return rows


def _supported(matrix: list[list[str]]) -> None:
    if len(matrix) > 1048576:
        raise t.InterchangeError("XLSX row capacity exceeded; use CSV/JSON")
    for i, row in enumerate(matrix, 1):
        for j, cell in enumerate(row, 1):
            if len(cell.encode("utf-16-le")) // 2 > LIMIT:
                raise t.InterchangeError(f"XLSX cell {i}:{j} exceeds {LIMIT} UTF-16 units; use CSV/JSON")


def build_workbook(document: Any):
    """Return an artifact_tool workbook; create cells as text, never formula data."""
    from artifact_tool import Workbook
    typed, reader = xlsx_rows(document), display_rows(document)
    _supported(typed); _supported(reader)
    wb = Workbook.create()
    guide = wb.worksheets.add("Guide")
    for name in ("Reader", "Transport"):
        wb.worksheets.add(name)
    guide_rows = [
        ["UIOWA / INTERCHANGE", "Synthetic preparation · format integrity only"],
        ["Purpose", "Move an entire JSON document without changing its assessment meaning."],
        ["Transport", "Canonical import sheet: pointer / kind / value. Keep all rows and prefixes."],
        ["Reader", "Human-readable projection. It is checked against Transport on import; edits are not silently ignored."],
        ["Missing values", "Absent key = no member; null = present with no value; empty string = present text of length zero."],
        ["Exact text", "Dates, time-zone offsets, large identifiers, decimal strings and formula-like text remain text."],
        ["Editing", "Edit canonical JSON, then regenerate. This workbook is a transport, not an assessment editor."],
        ["Integrity receipt", t.document_sha256(document)],
        ["Receipt meaning", "Canonical JSON SHA-256; not source-byte identity, provenance, currentness or approval."],
        ["Node count", str(len(typed) - 2)],
        ["Independent checks", "Node-count formula below counts Transport entries. It does not score maturity."],
        ["Count from Transport", ""],
        ["Limits", "XLSX: 32,767 UTF-16 units per cell; larger values fail explicitly. CSV/JSON remain available."],
    ]
    guide.get_range_by_indexes(0, 0, len(guide_rows), 2).values = guide_rows
    guide.get_range("B12").formulas = [[f"=COUNTA(Transport!A3:A{len(typed)})"]]
    guide.get_range("A1:B1").format = {"fill": "#17324D", "font": {"bold": True, "color": "#FFFFFF"}, "row_height": 34}
    guide.get_range("A2:A13").format = {"font": {"bold": True}, "column_width": 25}
    guide.get_range("B1:B13").format.column_width = 95
    guide.get_range("A1:B13").format.wrap_text = True
    guide.get_range("A2:B13").format.row_height = 42
    guide.freeze_panes.freeze_rows(1)
    for name, matrix in [("Reader", reader), ("Transport", typed)]:
        sheet = wb.worksheets.get_item(name)
        sheet.get_range_by_indexes(0, 0, len(matrix), 3).values = matrix
        sheet.get_range_by_indexes(0, 0, len(matrix), 3).set_number_format("@")
        sheet.get_range_by_indexes(0, 0, len(matrix), 3).format.wrap_text = True
        sheet.get_range_by_indexes(0, 0, len(matrix), 3).format.row_height = 34
        sheet.get_range(f"A1:A{len(matrix)}").format.column_width = 52
        sheet.get_range(f"B1:B{len(matrix)}").format.column_width = 14
        sheet.get_range(f"C1:C{len(matrix)}").format.column_width = 92
        header_end = 2 if name == "Transport" else 1
        sheet.get_range(f"A1:C{header_end}").format = {
            "fill": "#17324D", "font": {"bold": True, "color": "#FFFFFF"}, "wrap_text": True}
        sheet.freeze_panes.freeze_rows(header_end)
        # Reader height grows with long notes instead of clipping them.
        for i, row in enumerate(matrix[header_end:], header_end):
            height = min(409, max(34, 16 * (len(row[2]) // 90 + 2)))
            sheet.get_range_by_indexes(i, 0, 1, 3).format.row_height = height
    return wb


def write_xlsx(document: Any, path: str | Path):
    """Create an XLSX file and return the workbook for inspection/rendering."""
    from artifact_tool import SpreadsheetFile
    wb = build_workbook(document)
    # Open destination exclusively; no source or existing artifact is replaced.
    with Path(path).open("xb") as output:
        blob = SpreadsheetFile.export_xlsx(wb)
        output.write(blob.data if hasattr(blob, "data") else bytes(blob))
    return wb


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    raw = archive.read(name)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise t.InterchangeError("DTD/entity declarations are not part of the XLSX interchange")
    return ET.fromstring(raw)


def _sheets(archive: zipfile.ZipFile) -> dict[str, str]:
    root = _xml(archive, "xl/workbook.xml")
    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    targets = {}
    for rel in relationships:
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        resolved = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in PurePosixPath(resolved).parts:
            raise t.InterchangeError("non-canonical workbook relationship")
        targets[rel.get("Id")] = resolved
    sheets = {}
    for sheet in root.findall("s:sheets/s:sheet", NS):
        name = sheet.get("name")
        if name in sheets:
            raise t.InterchangeError("duplicate worksheet name")
        sheets[name] = targets.get(sheet.get("{" + NS["r"] + "}id"), "")
    return sheets


def _read_text_table(archive: zipfile.ZipFile, sheet_path: str,
                     shared: list[str]) -> list[list[str]]:
    root = _xml(archive, sheet_path)
    result = []
    for expected_row, row in enumerate(root.findall("s:sheetData/s:row", NS), 1):
        if row.get("r") != str(expected_row):
            raise t.InterchangeError("non-contiguous worksheet rows")
        values = ["", "", ""]
        occupied = set()
        for cell in row.findall("s:c", NS):
            ref = cell.get("r", "")
            match = re.fullmatch(r"([ABC])([1-9][0-9]*)", ref)
            if not match or int(match[2]) != expected_row or ref in occupied:
                raise t.InterchangeError(f"invalid or duplicate worksheet cell: {ref}")
            occupied.add(ref)
            if cell.find("s:f", NS) is not None:
                raise t.InterchangeError(f"formula in a data sheet at {ref}")
            kind = cell.get("t")
            raw = cell.findtext("s:v", default="", namespaces=NS)
            if kind == "s":
                try:
                    index = int(raw)
                    if index < 0:
                        raise ValueError("negative index")
                    text = shared[index]
                except (ValueError, IndexError) as exc:
                    raise t.InterchangeError(f"invalid shared string at {ref}") from exc
            elif kind == "inlineStr":
                text = _decode_ooxml("".join(node.text or "" for node in cell.findall("s:is/s:t", NS)
                                            + cell.findall("s:is/s:r/s:t", NS)))
            elif kind == "str":
                text = _decode_ooxml(raw)
            elif kind in (None, "n") and raw == "":
                text = ""
            else:
                raise t.InterchangeError(f"non-text transport cell {ref}: {kind}")
            values[ord(match[1]) - ord("A")] = text
        result.append(values)
    return result


def read_xlsx(path: str | Path) -> Any:
    """Read typed Transport and cross-check Reader without evaluating formulas.

    Accepts the format's XLSX, not arbitrary user workbooks. Guide formulas are
    presentation-only; no formula evaluator or external-link fetch runs here.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise t.InterchangeError("duplicate ZIP member names")
            if any(info.file_size > 64 * 1024 * 1024 for info in archive.infolist()):
                raise t.InterchangeError("XLSX part exceeds supported 64 MiB")
            shared = []
            if "xl/sharedStrings.xml" in names:
                for si in _xml(archive, "xl/sharedStrings.xml"):
                    shared.append(_decode_ooxml("".join(node.text or "" for node in
                        si.findall("s:t", NS) + si.findall("s:r/s:t", NS))))
            sheets = _sheets(archive)
            if not sheets.get("Transport") or not sheets.get("Reader"):
                raise t.InterchangeError("workbook requires Transport and Reader sheets")
            document = t.from_rows(_read_text_table(archive, sheets["Transport"], shared))
            if _read_text_table(archive, sheets["Reader"], shared) != display_rows(document):
                raise t.InterchangeError("Reader differs from Transport; regenerate from canonical JSON")
            return document
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError) as exc:
        raise t.InterchangeError(f"invalid interchange workbook: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "import"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            value = t.read_json(args.source)
            write_xlsx(value, args.destination)
        else:
            value = read_xlsx(args.source)
            t.write_json(value, args.destination)
        print(json.dumps({"result": "PASS", "document_sha256": t.document_sha256(value),
                          "authority": "FORMAT_INTEGRITY_ONLY"}))
    except (t.InterchangeError, OSError) as exc:
        parser.exit(2, f"interchange: {exc}\n")


if __name__ == "__main__":
    main()
