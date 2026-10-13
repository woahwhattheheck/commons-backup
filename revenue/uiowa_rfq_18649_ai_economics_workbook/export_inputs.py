#!/usr/bin/env python3
"""Export editable workbook cells through the canonical economics validator.

Uses the standard library and never consumes cached formula output. The four-case
template has a stable cell map; unexpected labels, formulas in editable cells,
partial ranges, and malformed numeric values are errors rather than imputation.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import importlib.util
import json
from pathlib import Path
import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def load_core(core_dir: Path):
    source = core_dir / "economics.py"
    spec = importlib.util.spec_from_file_location("uiowa_economics_core", source)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load the canonical calculator at {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_input_cells(workbook: Path):
    with zipfile.ZipFile(workbook) as archive:
        if sum(info.file_size for info in archive.infolist()) > 32 * 1024 * 1024:
            raise ValueError("Workbook exceeds the 32 MiB expanded-size limit")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.itertext()) for node in root.findall("s:si", NS)]
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = [s for s in root.findall("s:sheets/s:sheet", NS) if s.get("name") == "Inputs"]
        if len(sheets) != 1:
            raise ValueError("Exactly one Inputs worksheet is required")
        rel_id = sheets[0].get(f"{{{REL}}}id")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = [r.get("Target") for r in relationships.findall(f"{{{PKG_REL}}}Relationship") if r.get("Id") == rel_id]
        if len(targets) != 1 or targets[0] is None:
            raise ValueError("Inputs worksheet relationship is missing")
        target = targets[0]
        member = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        if not member.startswith("xl/worksheets/"):
            raise ValueError("Unexpected Inputs worksheet location")
        tree = ET.fromstring(archive.read(member))
        cells = {}
        for node in tree.findall("s:sheetData/s:row/s:c", NS):
            address = node.get("r")
            if address in cells:
                raise ValueError(f"Duplicate cell {address}")
            value = node.findtext("s:v", default=None, namespaces=NS)
            kind = node.get("t", "n")
            if kind == "s":
                value = strings[int(value)]
            elif kind == "inlineStr":
                value = "".join(node.find("s:is", NS).itertext())
            cells[address] = (kind, value, node.find("s:f", NS) is not None)
        return cells


def plain(cells, address, *, numeric=False):
    kind, value, formula = cells.get(address, ("n", None, False))
    if formula:
        raise ValueError(f"{address}: editable inputs must contain values, not formulas")
    if value is None or value == "":
        return None
    if numeric:
        if kind != "n":
            raise ValueError(f"{address}: enter a numeric cell, not text or a boolean")
        try:
            number = Decimal(value)
        except InvalidOperation as error:
            raise ValueError(f"{address}: invalid decimal") from error
        if not number.is_finite():
            raise ValueError(f"{address}: expected a finite decimal")
        return format(number, "f")
    if kind not in {"s", "str", "inlineStr"}:
        raise ValueError(f"{address}: expected text")
    return value


def export_document(workbook: Path, core):
    cells = read_input_cells(workbook)
    months = plain(cells, "B5", numeric=True)
    if months is None or Decimal(months) != Decimal(months).to_integral_value():
        raise ValueError("B5: horizon must be a whole number of months")
    doc = {"schema_version": core.VERSION, "input_basis": plain(cells, "B7"),
           "currency": plain(cells, "B6"), "horizon_months": int(Decimal(months)), "scenarios": []}
    fields = list(core.FIELDS)
    for index in range(4):
        meta_row = 4 + index
        scenario = {"id": plain(cells, f"E{meta_row}"), "group": plain(cells, f"F{meta_row}"),
                    "label": plain(cells, f"G{meta_row}"), "notes": plain(cells, f"H{meta_row}"), "inputs": {}}
        for field_index, field in enumerate(fields):
            active_row = 12 + field_index * 6
            row = active_row + index + 1
            if plain(cells, f"A{active_row}") != field or plain(cells, f"A{row}") != scenario["id"]:
                raise ValueError(f"Row {row}: input map changed; retain the template row order and identifiers")
            numbers = [plain(cells, f"{column}{row}", numeric=True) for column in "CDE"]
            if any(number is None for number in numbers) and not all(number is None for number in numbers):
                raise ValueError(f"Row {row}: enter all low/base/high values or leave all three blank")
            scenario["inputs"][field] = {
                "range": None if numbers[0] is None else dict(zip(("low", "base", "high"), numbers)),
                "unit": plain(cells, f"B{row}"), "basis": plain(cells, f"F{row}"),
                "source": plain(cells, f"G{row}")}
        doc["scenarios"].append(scenario)
    core.validate_document(doc)
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--core-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_ai_economics")
    args = parser.parse_args()
    try:
        core = load_core(args.core_dir)
        document = export_document(args.workbook, core)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, IndexError, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"export_failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "scenarios": len(document["scenarios"]),
                      "input_sha256": core.canonical_hash(document)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
