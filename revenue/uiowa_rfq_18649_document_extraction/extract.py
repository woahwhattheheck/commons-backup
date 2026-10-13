#!/usr/bin/env python3
"""Locator-preserving document extraction for RFQ assessment evidence.

Supported formats:
- PDF: page locators via pypdf
- DOCX: section-heading + paragraph/table locators via OOXML
- TXT/MD: section-heading + line-range locators

The adapter intentionally does not invent page numbers for DOCX/TXT documents.
When text extraction is unavailable or incomplete, it reports explicit warnings.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA = "uiowa.document-extraction.v1"
MAX_BYTES = 50 * 1024 * 1024
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"


class ExtractionError(Exception):
    pass


@dataclass
class Segment:
    segment_id: str
    kind: str
    locator: str
    text: str
    heading_path: list[str]
    warnings: list[str]


def _read_snapshot(path: Path) -> bytes:
    """Bind parser input, length and digest to one bounded byte snapshot.

    Metadata checks catch ordinary edits during the read; they are not a claim
    of adversarial filesystem isolation. The digest always describes these bytes.
    """
    try:
        if not Path(path).is_file():
            raise ExtractionError("INPUT_NOT_A_REGULAR_FILE")
        with Path(path).open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ExtractionError("INPUT_NOT_A_REGULAR_FILE")
            if before.st_size > MAX_BYTES:
                raise ExtractionError(f"INPUT_TOO_LARGE:{before.st_size}>{MAX_BYTES}")
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ExtractionError(f"INPUT_READ_FAILED:{type(exc).__name__}") from exc
    if len(raw) > MAX_BYTES:
        raise ExtractionError(f"INPUT_TOO_LARGE:{len(raw)}>{MAX_BYTES}")
    attributes = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key) for key in attributes):
        raise ExtractionError("INPUT_CHANGED_DURING_READ")
    if len(raw) != after.st_size:
        raise ExtractionError("INPUT_SIZE_CHANGED_DURING_READ")
    return raw


def sha256_file(path: Path) -> str:
    return hashlib.sha256(_read_snapshot(path)).hexdigest()


def _markdown_heading(line: str) -> tuple[int, str] | None:
    # ATX headings permit up to three leading spaces and an optional closing run.
    match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)", line)
    if not match:
        return None
    title = match.group(2) or ""
    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
    # An all-hash closing run can follow the required opening whitespace.
    if title and re.fullmatch(r"#+", title):
        title = ""
    return len(match.group(1)), title


def _heading_level_from_markdown(line: str) -> int | None:
    heading = _markdown_heading(line)
    return heading[0] if heading is not None else None


def _heading_path_update(stack: list[str], level: int, title: str) -> list[str]:
    level = max(1, min(level, 9))
    if len(stack) >= level:
        stack = stack[: level - 1]
    while len(stack) < level - 1:
        stack.append("(untitled)")
    stack.append(title.strip())
    return stack


def _extract_text_bytes(raw: bytes) -> tuple[list[Segment], list[str]]:
    warnings: list[str] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        warnings.append("TEXT_DECODE_REPLACEMENTS_USED")

    lines = text.splitlines()
    segments: list[Segment] = []
    stack: list[str] = []
    buffer: list[str] = []
    start_line = 1
    fence: tuple[str, int] | None = None

    def flush() -> None:
        nonlocal buffer, start_line
        # Trim only blank edge lines, adjusting the locator; keep prose/code spaces.
        first, last = 0, len(buffer)
        while first < last and not buffer[first].strip():
            first += 1
        while last > first and not buffer[last - 1].strip():
            last -= 1
        if first < last:
            segments.append(Segment(
                segment_id=f"text-{len(segments)+1:04d}", kind="text",
                locator=f"lines {start_line+first}-{start_line+last-1}",
                text="\n".join(buffer[first:last]), heading_path=list(stack), warnings=[],
            ))
        buffer = []

    for idx, line in enumerate(lines, start=1):
        if fence is not None:
            if not buffer:
                start_line = idx
            buffer.append(line)
            char, length = fence
            if re.fullmatch(r" {0,3}" + re.escape(char) + "{" + str(length) + r",}[ \t]*", line):
                fence = None
            continue
        opener = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if opener and not (opener.group(1)[0] == "`" and "`" in opener.group(2)):
            fence = opener.group(1)[0], len(opener.group(1))
            if not buffer:
                start_line = idx
            buffer.append(line)
            continue
        heading = _markdown_heading(line)
        if heading is not None:
            flush()
            level, title = heading
            stack = _heading_path_update(stack, level, title)
            segments.append(Segment(
                segment_id=f"heading-{len(segments)+1:04d}", kind="heading",
                locator=f"line {idx}", text=title, heading_path=list(stack), warnings=[],
            ))
            start_line = idx + 1
        else:
            if not buffer:
                start_line = idx
            buffer.append(line)
    flush()
    if fence is not None:
        warnings.append("TEXT_UNCLOSED_FENCE; remaining lines retained as literal text")
    return segments, warnings


def extract_text(path: Path) -> tuple[list[Segment], list[str]]:
    return _extract_text_bytes(_read_snapshot(path))


def _docx_has_alternate_content(element: ET.Element) -> bool:
    """Detect unresolved alternatives only in the accepted body-text view.

    Do not guess which application-specific Choice a renderer would select.
    Deleted/moved-from text and omitted drawings cannot contaminate current prose.
    """
    if element.tag in {f"{{{W_NS}}}{name}" for name in ("del", "moveFrom", "drawing", "pict", "object")}:
        return False
    if element.tag == f"{{{MC_NS}}}AlternateContent":
        return True
    return any(_docx_has_alternate_content(child) for child in element)


def _docx_paragraph_text(p: ET.Element) -> str:
    # Extract an explicitly declared accepted-text view, without modifying OOXML.
    # Withhold the entire affected paragraph: deleting just the ambiguous span
    # could manufacture a different quotation from the text surrounding the gap.
    if _docx_has_alternate_content(p):
        return ""
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        if node.tag in {f"{{{W_NS}}}{name}" for name in ("del", "moveFrom", "drawing", "pict", "object")}:
            return
        if node.tag == f"{{{W_NS}}}t":
            parts.append(node.text or "")
        elif node.tag == f"{{{W_NS}}}noBreakHyphen":
            parts.append("\u2011")
        elif node.tag == f"{{{W_NS}}}tab":
            parts.append("\t")
        elif node.tag in {f"{{{W_NS}}}br", f"{{{W_NS}}}cr"}:
            parts.append("\n")
        for child in node:
            visit(child)

    visit(p)
    return "".join(parts).strip()


def _docx_style_id(p: ET.Element) -> str | None:
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        return None
    style = ppr.find("w:pStyle", NS)
    if style is None:
        return None
    return style.get(f"{{{W_NS}}}val")


def _docx_heading_level(style_id: str | None) -> int | None:
    match = re.fullmatch(r"heading\s*([1-9])", style_id or "", flags=re.I)
    return int(match.group(1)) if match else None


def _docx_outline_level(p: ET.Element, styles: dict[str, ET.Element], warnings: list[str]) -> int | None:
    def parse(element: ET.Element) -> int | None:
        try:
            level = int(element.get(f"{{{W_NS}}}val", ""))
        except ValueError:
            warnings.append("DOCX_INVALID_OUTLINE_LEVEL; heading context unresolved")
            return None
        if 0 <= level < 9:
            return level + 1
        if level != 9:
            warnings.append("DOCX_INVALID_OUTLINE_LEVEL; heading context unresolved")
        return None  # outlineLvl=9 explicitly denotes body text.

    direct = p.find("w:pPr/w:outlineLvl", NS)
    if direct is not None:
        return parse(direct)
    style_id = _docx_style_id(p)
    current = style_id
    seen: set[str] = set()
    while current in styles:
        if current in seen:
            warnings.append(f"DOCX_STYLE_INHERITANCE_CYCLE:{style_id}")
            return None
        seen.add(current)
        style = styles[current]
        outline = style.find("w:pPr/w:outlineLvl", NS)
        if outline is not None:
            return parse(outline)
        base = style.find("w:basedOn", NS)
        if base is None:
            break
        current = base.get(f"{{{W_NS}}}val")
    return _docx_heading_level(current) or _docx_heading_level(style_id)


def _docx_blocks(parent: ET.Element, warnings: list[str], prefix: str = ""):
    """Traverse supported body wrappers without renumbering direct-body locators."""
    counts: dict[str, int] = {}
    for child in parent:
        name = child.tag.removeprefix(f"{{{W_NS}}}")
        counts[name] = counts.get(name, 0) + 1
        index = counts[name]
        if name in {"p", "tbl"}:
            label = "paragraph" if name == "p" else "table"
            yield child, f"{prefix}{label} {index}"
        elif name == "sdt":
            content = child.find("w:sdtContent", NS)
            if content is None:
                warnings.append(f"DOCX_EMPTY_CONTENT_CONTROL:{prefix}sdt {index}")
            else:
                yield from _docx_blocks(content, warnings, f"{prefix}sdt {index}/sdtContent/")
        elif name in {"customXml", "ins", "moveTo"}:
            yield from _docx_blocks(child, warnings, f"{prefix}{name} {index}/")
        elif name in {"del", "moveFrom", "sectPr", "sdtPr", "customXmlPr", "tcPr"}:
            continue
        elif name not in {"bookmarkStart", "bookmarkEnd", "proofErr", "commentRangeStart", "commentRangeEnd", "permStart", "permEnd"}:
            warnings.append(f"DOCX_UNSUPPORTED_BODY_ELEMENT:{prefix}{name} {index}")


def _docx_part(zf: zipfile.ZipFile, name: str) -> bytes:
    info = zf.getinfo(name)
    if info.file_size > MAX_BYTES:
        raise ExtractionError(f"DOCX_PART_TOO_LARGE:{name}")
    with zf.open(info) as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ExtractionError(f"DOCX_PART_TOO_LARGE:{name}")
    return content


def _docx_table_text(table: ET.Element, warnings: list[str], locator: str) -> str:
    # A blanked cell must not look like a genuinely empty value; withhold the
    # affected table rather than retain a misleading partial row-major quotation.
    if _docx_has_alternate_content(table):
        warnings.append(f"DOCX_ALTERNATE_CONTENT_NOT_EXTRACTED:{locator}; entire table withheld; inspect original")
        return ""
    # Row/cell revision markers need grid reconstruction, not just text filtering.
    # Withhold the affected table rather than label ambiguous stored text as current.
    structural_revisions = (
        ".//w:trPr/w:ins", ".//w:trPr/w:del", ".//w:tcPr/w:cellIns",
        ".//w:tcPr/w:cellDel", ".//w:tcPr/w:cellMerge",
    )
    if any(table.find(selector, NS) is not None for selector in structural_revisions):
        warnings.append(f"DOCX_TABLE_STRUCTURAL_REVISIONS_NOT_EXTRACTED:{locator}; inspect original table")
        return ""
    rows: list[str] = []
    nonempty = False
    for tr in table.findall("w:tr", NS):
        cells: list[str] = []
        for tc in tr.findall("w:tc", NS):
            parts: list[str] = []
            for block, inner_locator in _docx_blocks(tc, warnings):
                if block.tag == f"{{{W_NS}}}p":
                    parts.append(_docx_paragraph_text(block))
                else:
                    warnings.append(f"DOCX_NESTED_TABLE_LINEARIZED:{locator}/{inner_locator}")
                    parts.append(_docx_table_text(block, warnings, f"{locator}/{inner_locator}"))
            value = " ".join(part for part in parts if part).strip()
            nonempty = nonempty or bool(value)
            cells.append(value)
        rows.append(" | ".join(cells))
    # Separators alone cannot turn an empty table into evidence.
    return "\n".join(rows).strip() if nonempty else ""


def _extract_docx_bytes(raw: bytes) -> tuple[list[Segment], list[str]]:
    warnings = [
        "DOCX_PAGE_NUMBERS_NOT_RELIABLE_IN_PACKAGE; using section/paragraph/table locators"
    ]
    styles: dict[str, ET.Element] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            try:
                xml_bytes = _docx_part(zf, "word/document.xml")
            except KeyError as exc:
                raise ExtractionError("DOCX_MISSING_word/document.xml") from exc
            names = zf.namelist()
            omitted = sorted(name for name in names if re.fullmatch(
                r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name
            ))
            if omitted:
                warnings.append("DOCX_NON_BODY_PARTS_NOT_EXTRACTED:" + ",".join(omitted))
            if "word/styles.xml" in names:
                try:
                    style_root = ET.fromstring(_docx_part(zf, "word/styles.xml"))
                    for style in style_root.findall("w:style", NS):
                        style_id = style.get(f"{{{W_NS}}}styleId")
                        if style_id:
                            styles[style_id] = style
                except ET.ParseError:
                    warnings.append("DOCX_STYLES_XML_PARSE_ERROR; heading context may be incomplete")
    except zipfile.BadZipFile as exc:
        raise ExtractionError("DOCX_INVALID_ZIP_CONTAINER") from exc
    except (OSError, RuntimeError, NotImplementedError) as exc:
        raise ExtractionError(f"DOCX_PACKAGE_READ_FAILED:{type(exc).__name__}") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ExtractionError("DOCX_DOCUMENT_XML_PARSE_ERROR") from exc
    body = root.find("w:body", NS)
    if body is None:
        raise ExtractionError("DOCX_MISSING_BODY")
    tags = {element.tag for element in body.iter()}
    if tags & {f"{{{W_NS}}}{name}" for name in ("ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel", "cellMerge")}:
        warnings.append(
            "DOCX_TRACKED_CHANGES_ACCEPTED_TEXT_VIEW; supported text insertions/moveTo included, "
            "text deletions/moveFrom omitted; table structural revisions withheld; source package unchanged"
        )
    if tags & {f"{{{W_NS}}}{name}" for name in ("drawing", "pict", "object")}:
        warnings.append("DOCX_DRAWING_OR_EMBEDDED_CONTENT_NOT_EXTRACTED; inspect original artifact")
    if tags & {f"{{{W_NS}}}{name}" for name in ("instrText", "fldSimple", "fldChar")}:
        warnings.append("DOCX_FIELD_RESULTS_NOT_RECALCULATED; only cached display text is available")
    if tags & {f"{{{W_NS}}}{name}" for name in ("gridSpan", "vMerge", "hMerge")}:
        warnings.append("DOCX_MERGED_TABLE_CELLS; pipe output does not reconstruct visual spans")
    if any(body.findall(f".//w:{parent}/w:{wrapper}", NS)
           for parent in ("tbl", "tr")
           for wrapper in ("sdt", "customXml", "ins", "moveTo")):
        warnings.append("DOCX_WRAPPED_TABLE_ROWS_OR_CELLS_NOT_EXTRACTED; inspect original table")

    segments: list[Segment] = []
    stack: list[str] = []
    for child, locator in _docx_blocks(body, warnings):
        if child.tag == f"{{{W_NS}}}p":
            if _docx_has_alternate_content(child):
                warning = f"DOCX_ALTERNATE_CONTENT_NOT_EXTRACTED:{locator}; entire paragraph withheld; inspect original"
                warnings.append(warning)
                level = _docx_outline_level(child, styles, warnings)
                if level is not None:
                    stack = _heading_path_update(stack, level, "(unresolved heading)")
                segments.append(Segment(
                    segment_id=f"docx-{len(segments)+1:04d}", kind="unreadable",
                    locator=locator, text="", heading_path=list(stack), warnings=[warning],
                ))
                continue
            value = _docx_paragraph_text(child)
            if not value:
                continue
            level = _docx_outline_level(child, styles, warnings)
            if level is not None:
                stack = _heading_path_update(stack, level, value)
            segments.append(Segment(
                segment_id=f"docx-{len(segments)+1:04d}",
                kind="heading" if level is not None else "paragraph",
                locator=locator, text=value, heading_path=list(stack), warnings=[],
            ))
        else:
            value = _docx_table_text(child, warnings, locator)
            table_warnings = ["TABLE_LINEARIZED_ROW_MAJOR_WITH_PIPE_SEPARATORS"]
            if not value:
                table_warnings.append("TABLE_NO_EXTRACTABLE_TEXT")
            segments.append(Segment(
                segment_id=f"docx-{len(segments)+1:04d}", kind="table", locator=locator,
                text=value, heading_path=list(stack), warnings=table_warnings,
            ))
    if not any(segment.text.strip() for segment in segments):
        warnings.append("DOCX_NO_EXTRACTABLE_TEXT")
    return segments, list(dict.fromkeys(warnings))


def extract_docx(path: Path) -> tuple[list[Segment], list[str]]:
    return _extract_docx_bytes(_read_snapshot(path))


def _split_pdf_page_text(text: str) -> list[str]:
    """Keep a page as a citation unit, but preserve logical blocks when possible."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    if not blocks and (text or "").strip():
        blocks = [(text or "").strip()]
    return blocks


def _extract_pdf_bytes(raw: bytes) -> tuple[list[Segment], list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError(
            "PDF_BACKEND_UNAVAILABLE: install pypdf>=6,<7"
        ) from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
    except Exception as exc:
        raise ExtractionError(f"PDF_OPEN_FAILED: {type(exc).__name__}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            status = reader.decrypt("")
        except Exception:
            status = 0
        if not status:
            raise ExtractionError("PDF_ENCRYPTED_PASSWORD_REQUIRED")

    # Page-tree flattening is lazy in pypdf. Opening the container successfully
    # does not establish that its page sequence can be enumerated. Validate the
    # complete sequence before emitting locators or extracting partial content.
    try:
        pages = list(reader.pages)
    except Exception as exc:
        raise ExtractionError(f"PDF_PAGE_TREE_FAILED:{type(exc).__name__}") from exc
    if not pages:
        warnings.append("PDF_NO_PAGES")

    segments: list[Segment] = []
    empty_pages = 0
    for page_no, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            empty_pages += 1
            segments.append(
                Segment(
                    segment_id=f"pdf-{len(segments)+1:04d}",
                    kind="unreadable",
                    locator=f"page {page_no}",
                    text="",
                    heading_path=[],
                    warnings=[f"PAGE_TEXT_EXTRACTION_FAILED:{type(exc).__name__}"],
                )
            )
            continue
        blocks = _split_pdf_page_text(text)
        if not blocks:
            empty_pages += 1
            segments.append(
                Segment(
                    segment_id=f"pdf-{len(segments)+1:04d}",
                    kind="unreadable",
                    locator=f"page {page_no}",
                    text="",
                    heading_path=[],
                    warnings=[
                        "PAGE_NO_EXTRACTABLE_TEXT; possible image-only, scanned, or unsupported layout"
                    ],
                )
            )
            continue
        for block_index, block in enumerate(blocks, start=1):
            segments.append(
                Segment(
                    segment_id=f"pdf-{len(segments)+1:04d}",
                    kind="page_text",
                    locator=f"page {page_no}, block {block_index}",
                    text=block,
                    heading_path=[],
                    warnings=[],
                )
            )

    if empty_pages:
        warnings.append(f"PDF_PAGES_WITHOUT_EXTRACTABLE_TEXT={empty_pages}/{len(pages)}")
    if pages and empty_pages == len(pages):
        warnings.append("PDF_TEXT_EXTRACTION_EMPTY_FOR_ALL_PAGES; OCR_REQUIRED_FOR_IMAGE_ONLY_CONTENT")
    return segments, warnings


def extract_pdf(path: Path) -> tuple[list[Segment], list[str]]:
    return _extract_pdf_bytes(_read_snapshot(path))


def extract(path: Path) -> dict:
    try:
        path = Path(path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ExtractionError(f"INPUT_PATH_FAILED:{type(exc).__name__}") from exc
    suffix = path.suffix.lower()
    backends = {
        ".txt": ("plain_text", _extract_text_bytes),
        ".md": ("plain_text", _extract_text_bytes),
        ".docx": ("docx", _extract_docx_bytes),
        ".pdf": ("pdf", _extract_pdf_bytes),
    }
    if suffix not in backends:
        raise ExtractionError(f"UNSUPPORTED_EXTENSION:{suffix or '(none)'}")
    raw = _read_snapshot(path)
    document_type, backend = backends[suffix]
    segments, warnings = backend(raw)
    extracted_nonempty = sum(1 for segment in segments if segment.text.strip())
    status = "ok"
    if warnings or any(segment.warnings for segment in segments) or extracted_nonempty < len(segments):
        status = "partial"
    if not extracted_nonempty:
        status = "unreadable"
    return {
        "schema": SCHEMA,
        "document": {
            "name": path.name, "type": document_type,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "status": status, "warnings": warnings,
        "segments": [asdict(segment) for segment in segments],
    }


def _write_output(path: Path, source: Path, payload: str) -> None:
    """Never replace source evidence or a previously produced report."""
    try:
        if path.resolve() == source.resolve():
            raise ExtractionError("OUTPUT_EQUALS_INPUT; choose a new output path")
        # Exclusive creation also preserves existing hard links and symlink targets.
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise ExtractionError("OUTPUT_ALREADY_EXISTS; choose a new output path") from exc
    except (OSError, RuntimeError) as exc:
        raise ExtractionError(f"OUTPUT_WRITE_FAILED:{type(exc).__name__}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = extract(args.input)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            _write_output(args.output, args.input, payload)
        else:
            sys.stdout.write(payload)
        return 0 if result["status"] in {"ok", "partial"} else 2
    except ExtractionError as exc:
        payload = {
            "schema": SCHEMA,
            "document": {"name": args.input.name},
            "status": "error",
            "error": str(exc),
            "warnings": [],
            "segments": [],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
