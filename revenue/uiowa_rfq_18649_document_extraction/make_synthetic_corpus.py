#!/usr/bin/env python3
"""Generate the checked-in synthetic TXT/DOCX/PDF corpus without external packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures"


def _write_minimal_pdf(path: Path, pages: list[str]) -> None:
    objects: list[bytes] = []
    # 1 Catalog, 2 Pages, 3.. pages, font after pages, content after font.
    page_obj_ids = list(range(3, 3 + len(pages)))
    font_id = 3 + len(pages)
    content_ids = list(range(font_id + 1, font_id + 1 + len(pages)))

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{i} 0 R" for i in page_obj_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for page_id, content_id in zip(page_obj_ids, content_ids):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{obj_id} 0 obj\n".encode())
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(data))


def _write_minimal_docx(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Deployment Evidence</w:t></w:r></w:p>
  <w:p><w:r><w:t>Release review requires a named owner and a reversible deployment plan.</w:t></w:r></w:p>
  <w:tbl>
    <w:tr><w:tc><w:p><w:r><w:t>Artifact</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Locator</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>Runbook</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>RB-17</w:t></w:r></w:p></w:tc></w:tr>
  </w:tbl>
  <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Incident Learning</w:t></w:r></w:p>
  <w:p><w:r><w:t>Post-incident actions are tracked to closure in this synthetic example.</w:t></w:r></w:p>
  <w:sectPr/>
</w:body></w:document>"""
    # Fixed metadata and STORE avoid clock/platform/zlib-dependent fixture bytes.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, text in (("[Content_Types].xml", content_types),
                           ("_rels/.rels", rels), ("word/document.xml", document)):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_STORED
            zf.writestr(entry, text.encode("utf-8"))


FIXTURE_NAMES = ("blank.pdf", "sample.docx", "sample.pdf", "sample.txt")


def build_corpus(output_dir: Path) -> dict:
    """Generate only the named synthetic fixtures; never enumerate unrelated files.

    This is an explicit fixture-authoring command, not a verifier. Tests call it
    inside temporary directories and compare against independently pinned hashes.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "sample.txt").write_bytes(
        ("# Software Development\n"
         "Pull requests require an independent review before merge.\n\n"
         "## Deployment\n"
         "Rollback evidence is attached to each synthetic release record.\n").encode("utf-8")
    )
    _write_minimal_docx(output_dir / "sample.docx")
    _write_minimal_pdf(
        output_dir / "sample.pdf",
        ["Synthetic PDF page one: release checklist.", "Synthetic PDF page two: monitoring evidence."],
    )
    _write_minimal_pdf(output_dir / "blank.pdf", [""])
    manifest = {}
    for name in FIXTURE_NAMES:
        raw = (output_dir / name).read_bytes()
        manifest[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "synthetic": True,
        }
    (output_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return manifest


def main(output_dir: Path | None = None) -> None:
    build_corpus(OUT if output_dir is None else output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT,
                        help="Fixture destination; tests always use temporary directories")
    main(parser.parse_args().output_dir)
