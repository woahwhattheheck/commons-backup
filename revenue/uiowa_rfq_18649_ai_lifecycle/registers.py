#!/usr/bin/env python3
"""Editable CSV registers for the existing offline AI lifecycle analyzer."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

if __package__:
    from . import lifecycle, review_html
else:
    import lifecycle
    import review_html

MAX_BYTES = review_html.MAX_INPUT_BYTES
MAX_ROWS = 100_000
MAX_CELL_CHARS = 131_072
NULL = "\\N"
COLLECTIONS = ("artifacts", "cases", "evaluation_sets", "versions", "runs",
               "comparisons", "replays", "events")
TABLES = ("workflow", "artifacts", "cases", "evaluation_sets", "versions",
          "runs", "observations", "comparisons", "replays", "events")


class RegisterError(ValueError):
    """A register cannot be imported without changing or guessing its meaning."""


def columns(table: str) -> dict[str, dict[str, Any]]:
    """Derive columns from the canonical schema rather than copy its rules."""
    root = lifecycle.SCHEMA["properties"]
    if table == "workflow":
        properties = {k: v for k, v in root.items() if k not in COLLECTIONS}
    elif table == "observations":
        run = root["runs"]["items"]["properties"]
        properties = {"run_id": run["id"],
                      **run["observations"]["items"]["properties"]}
    else:
        properties = root[table]["items"]["properties"]
    result = {}
    for name, spec in properties.items():
        if table == "runs" and name == "observations":
            continue
        if spec["type"] == "object":
            for child, child_spec in spec["properties"].items():
                result[f"{name}.{child}"] = child_spec
        else:
            result[name] = spec
    return result


def decode(cell: str, spec: dict[str, Any], where: str) -> Any:
    types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
    if len(cell) > MAX_CELL_CHARS:
        raise RegisterError(f"{where}: cell exceeds {MAX_CELL_CHARS} characters")
    if cell == NULL:
        value = None
    elif "string" in types:
        # A leading apostrophe quotes text for spreadsheet-oriented export.
        # Double a literal leading apostrophe or backslash on manual input.
        if cell.startswith("'"):
            value = cell[1:]
        elif cell.startswith("\\\\"):
            value = cell[1:]
        elif cell.startswith("\\"):
            raise RegisterError(f"{where}: use {NULL} for null; double a literal leading backslash")
        else:
            value = cell
    elif "array" in types:
        value = cell.split(";") if cell else []
    elif "boolean" in types:
        if cell not in ("true", "false"):
            raise RegisterError(f"{where}: expected true, false, or {NULL} when nullable")
        value = cell == "true"
    else:
        try:
            value = json.loads(cell)
        except (ValueError, RecursionError) as exc:
            raise RegisterError(f"{where}: expected a number or {NULL} when nullable") from exc
    lifecycle.check_schema(value, spec, where)
    return value


def encode(value: Any, spec: dict[str, Any]) -> str:
    if value is None:
        cell = NULL
    elif isinstance(value, str):
        cell = value
        if cell.startswith("\\"):
            cell = "\\" + cell
        elif cell.startswith("'") or cell.lstrip().startswith(("=", "+", "-", "@")) or cell[:1] in ("\t", "\r", "\n"):
            cell = "'" + cell
    elif type(value) is bool:
        cell = "true" if value else "false"
    elif isinstance(value, list):
        cell = ";".join(value)
    else:
        cell = json.dumps(value, allow_nan=False)
    if len(cell) > MAX_CELL_CHARS:
        raise RegisterError(f"exported cell exceeds {MAX_CELL_CHARS} characters")
    return cell


def read_regular(path: Path, limit: int = MAX_BYTES) -> bytes:
    """Read a bounded regular file; never follow a final-component symlink."""
    if path.is_symlink():
        raise RegisterError(f"{path.name}: symbolic links are not register inputs")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RegisterError(f"{path.name}: expected a regular file")
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise RegisterError(f"{path.name}: input exceeds remaining byte limit ({limit})")
    return body


def parse_table(table: str, body: bytes, remaining_rows: int) -> tuple[list[dict[str, Any]], list[int]]:
    specs = columns(table)
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    filename = table + ".csv"
    try:
        header = next(reader, None)
        if header is None:
            raise RegisterError(f"{filename}: missing header")
        if len(header) != len(set(header)):
            raise RegisterError(f"{filename}: duplicate column names")
        if set(header) != set(specs):
            missing, extra = sorted(set(specs) - set(header)), sorted(set(header) - set(specs))
            raise RegisterError(f"{filename}: missing columns={missing}; unexpected columns={extra}")
        rows, lines = [], []
        for cells in reader:
            line = reader.line_num
            if len(rows) >= remaining_rows:
                raise RegisterError(f"{filename}:{line}: total register row limit exceeded ({MAX_ROWS})")
            if len(cells) != len(header):
                raise RegisterError(f"{filename}:{line}: expected {len(header)} cells, got {len(cells)}")
            row: dict[str, Any] = {}
            for name, cell in zip(header, cells):
                value = decode(cell, specs[name], f"{filename}:{line}:{name}")
                if "." in name:
                    parent, child = name.split(".", 1)
                    row.setdefault(parent, {})[child] = value
                else:
                    row[name] = value
            rows.append(row)
            lines.append(line)
        return rows, lines
    except (csv.Error, UnicodeError) as exc:
        raise RegisterError(f"{filename}:{reader.line_num}: invalid CSV/UTF-8: {exc}") from exc


def read_registers(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise RegisterError("register input must be a real directory")
    expected = {name + ".csv" for name in TABLES}
    extra = sorted(p.name for p in directory.iterdir()
                   if p.suffix.lower() == ".csv" and p.name not in expected)
    if extra:
        raise RegisterError(f"unexpected CSV tables: {extra}; no table is silently ignored")
    tables, locations = {}, {}
    byte_count = row_count = 0
    for name in TABLES:
        path = directory / (name + ".csv")
        try:
            body = read_regular(path, MAX_BYTES - byte_count)
            byte_count += len(body)
            rows, lines = parse_table(name, body, MAX_ROWS - row_count)
        except (OSError, UnicodeError) as exc:
            raise RegisterError(f"{path.name}: {exc}") from exc
        row_count += len(rows)
        tables[name], locations[name] = rows, lines
        if name in COLLECTIONS:
            key = "artifact_ref" if name == "evaluation_sets" else "id"
            seen = {}
            for row, line in zip(rows, lines):
                ident = row[key]
                if ident in seen:
                    raise RegisterError(f"{path.name}:{line}:{key}: duplicate {ident}; first at line {seen[ident]}")
                seen[ident] = line
    if len(tables["workflow"]) != 1:
        raise RegisterError("workflow.csv: exactly one data row is required")
    data = {**tables["workflow"][0], **{k: tables[k] for k in COLLECTIONS}}
    runs = {row["id"]: row for row in data["runs"]}
    for run in runs.values():
        run["observations"] = []
    seen_observations = set()
    for row, line in zip(tables["observations"], locations["observations"]):
        run_id = row["run_id"]
        if run_id not in runs:
            raise RegisterError(f"observations.csv:{line}:run_id: unknown run {run_id}")
        key = (run_id, row["case_id"])
        if key in seen_observations:
            raise RegisterError(f"observations.csv:{line}: duplicate run/case {key}")
        seen_observations.add(key)
        runs[run_id]["observations"].append({k: v for k, v in row.items() if k != "run_id"})
    try:
        lifecycle.validate(data)
    except lifecycle.ContractError as exc:
        raise RegisterError(f"assembled lifecycle contract: {exc}") from exc
    return data


def table_csv(table: str, rows: list[dict[str, Any]]) -> bytes:
    specs = columns(table)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(specs)
    for index, row in enumerate(rows, 2):
        cells = []
        for name, spec in specs.items():
            value = row
            for part in name.split("."):
                value = value[part]
            try:
                cells.append(encode(value, spec))
            except (TypeError, ValueError) as exc:
                raise RegisterError(f"{table}.csv:record {index}:{name}: {exc}") from exc
        writer.writerow(cells)
    return output.getvalue().encode("utf-8")


def export_registers(data: dict[str, Any]) -> dict[str, bytes]:
    lifecycle.validate(data)
    tables = {"workflow": [{k: v for k, v in data.items() if k not in COLLECTIONS}],
              **{k: data[k] for k in COLLECTIONS}}
    tables["observations"] = [{"run_id": run["id"], **observation}
                              for run in data["runs"] for observation in run["observations"]]
    if sum(len(tables[k]) for k in TABLES) > MAX_ROWS:
        raise RegisterError(f"export exceeds {MAX_ROWS} register rows")
    files = {name + ".csv": table_csv(name, tables[name]) for name in TABLES}
    if sum(map(len, files.values())) > MAX_BYTES:
        raise RegisterError(f"CSV export exceeds {MAX_BYTES} bytes")
    return files


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def build_reports(data: dict[str, Any], include_artifact_text: bool = False) -> dict[str, bytes]:
    history = json_bytes(data)
    if len(history) > MAX_BYTES:
        raise RegisterError(f"assembled history exceeds {MAX_BYTES} bytes")
    report = lifecycle.analyze(data)
    return {
        "history.json": history,
        "report.json": json_bytes(report),
        "report.md": lifecycle.markdown(report).encode("utf-8"),
        "comparisons.csv": lifecycle.comparison_csv(report).encode("utf-8"),
        "review.html": review_html.render(history, include_artifact_text=include_artifact_text).encode("utf-8"),
    }


def write_new(directory: Path, files: dict[str, bytes]) -> None:
    """Publish only pre-rendered outputs into a new operator-selected directory.

    Parent directories must exist and be trusted by the operator. This is not
    isolation from a hostile process able to replace the output directory.
    Partial files are retained on an I/O failure, never mistaken for success.
    """
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, body in files.items():
            fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
    except OSError as exc:
        raise RegisterError(f"output incomplete at {directory}; partial files retained: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="write ten empty CSV tables; invent no evidence")
    export = commands.add_parser("export", help="export a valid lifecycle JSON history to editable CSVs")
    build = commands.add_parser("build", help="assemble CSV registers and render existing lifecycle reports")
    export.add_argument("input", type=Path, help="original lifecycle JSON, not an analysis report")
    build.add_argument("input", type=Path, help="directory containing all ten CSV tables")
    build.add_argument("--include-artifact-text", action="store_true",
                       help="include retained text in HTML too; history.json always contains original data")
    for subparser in (template, export, build):
        subparser.add_argument("--output", type=Path, required=True,
                               help="new directory under an existing trusted parent; never overwrite")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            files = {name + ".csv": table_csv(name, []) for name in TABLES}
        elif args.command == "export":
            data = lifecycle.load(read_regular(args.input).decode("utf-8-sig"))
            files = export_registers(data)
        else:
            files = build_reports(read_registers(args.input), args.include_artifact_text)
        # Parsing, validation and rendering finish before creating any output.
        write_new(args.output, files)
        print(f"WROTE {len(files)} files to {args.output}; no model execution or network access")
        if args.command == "template":
            print("Header-only templates: fill workflow.csv and required records; use \\N for unknown nullable fields.")
        else:
            print("PRIVATE INPUT DERIVATIVES: output contains supplied metadata; exported registers/history.json include retained artifact text.")
        return 0
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        print(f"REGISTERS_NOT_WRITTEN_OR_INCOMPLETE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
