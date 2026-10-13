#!/usr/bin/env python3
"""Package the published UIOWA-138 handover with its unchanged UIOWA-091 sources."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

REVISION = "bcf765be4d537a513bf1d7ac54a210b25b053d07"
CORPUS = "revenue/uiowa_rfq_18649_synthetic_collection/"
SCHEMA = "uiowa138-portable-handover-v1"
DOCUMENTS = ("README.md", "HANDOVER.md", "SYNTHESIS.md", "SOURCE_REGISTER.md", "EXERCISE.md")
# Existing published SOURCE_REGISTER.md identities; source bytes are never rewritten.
SOURCE_PINS = {
    "facts.json": "d715a392b92b4738070552f7cecb8f32a4ddc765",
    "evidence_manifest.json": "551e407700fc16daffdef84d9a65722eda37c017",
    "coverage_matrix.csv": "eaa12d5491d16fd6417ff2c8059e58546f7fef85",
    "validate_collection.py": "ac9c634bbcf2e0a92eab3c2c0127aaf8f35f383f",
    "ai/ai_readiness.md": "43c8380cf052f1c501bdf39527547a58480a44f1",
    "incidents/postmortems.md": "636584d77b482bd2f4e61a2a2ec51e1617146bf3",
    "interviews/interview_excerpts.md": "5e6cd42f9a8d273522ee05a461865ebd5fca1172",
    "operations/runbooks.md": "6fbada5090a9c6faa95b668bc40b048516068927",
    "processes/security_practices.md": "110ee10ea5bfe161fc6bb75de289bfeea4925fb4",
    "processes/software_delivery.md": "abee696251ec299172a1feeb03848f98761a34b4",
    "releases/release_examples.md": "b8c091ab5fd1ccf1f025ac78274647d840df655f",
    "services/ess_profile.md": "e4d5206ed2510b654ed3d39611cb5453397b8c13",
    "services/ris_profile.md": "19f2cc0f3106b8d3768b2c88eab3ccca3494baef",
    "services/iam_profile.md": "704d23cfcc0ff6990b354d16dbd519d7f1157030",
}
STYLE = """body{margin:0;background:#f4f2ed;color:#172f36;font:17px/1.65 system-ui,sans-serif}
main{max-width:1050px;margin:auto;padding:40px 24px}a{color:#075976}
h1{font:700 36px/1.2 Georgia,serif;margin:16px 0}h2{font-size:23px;margin-top:32px}
.tag{font-size:12px;letter-spacing:.12em;font-weight:750;color:#6b4925}
.notice{background:#e6eae4;border-left:4px solid #385d59;padding:16px 20px}
.document{white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.7 system-ui,sans-serif;
background:white;padding:28px;border:1px solid #deddd6;border-radius:8px}
table{border-collapse:collapse;width:100%;background:white}th,td{padding:10px 14px;
border-bottom:1px solid #deddd6;text-align:left;vertical-align:top}code{font-size:.87em}
ol.lines{padding-left:4em;background:white;border:1px solid #deddd6}
ol.lines li{padding:3px 14px;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 monospace}
ol.lines li:target{background:#fff0b8}nav{display:flex;flex-wrap:wrap;gap:8px 24px}
@media(max-width:600px){main{padding:24px 16px}.document{padding:18px}h1{font-size:30px}}
"""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def describe(data: bytes) -> dict:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "git_blob": git_blob(data)}


def read_file(root: Path, relative: str) -> bytes:
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError(f"invalid bundle file path: {relative!r}")
    full = root.joinpath(*path.parts)
    if any(part.is_symlink() for part in (full, *full.parents) if part != root.parent):
        raise ValueError(f"symlink cannot retain file identity: {relative}")
    return full.read_bytes()


def check_sources(files: dict[str, bytes]) -> None:
    for name, expected in SOURCE_PINS.items():
        actual = git_blob(files[name])
        if actual != expected:
            raise ValueError(f"source changed: {name}: expected {expected}, got {actual}; select the registered revision")


def native_validate(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(root / "validate_collection.py"), str(root)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError(f"native collection validator failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    print(result.stdout, end="")


def page(title: str, body: str, home: str = "index.html") -> bytes:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main>'
            f'<div class="tag">UIOWA-138 · SYNTHETIC PREPARATION</div>'
            f'<p><a href="{html.escape(home, quote=True)}">Handover index</a></p>'
            f'<h1>{html.escape(title)}</h1>{body}</main></body></html>\n').encode()


def document_view(data: bytes) -> str:
    """Retain authored Markdown visibly; make its known local evidence links usable offline."""
    text = data.decode("utf-8")
    pattern = r"\[([^\]\n]+)\]\(([^\s)]+)\)"
    parts, position = [], 0
    prefix = f"https://github.com/woahwhattheheck/commons/blob/{REVISION}/{CORPUS}"
    for match in re.finditer(pattern, text):
        parts.append(html.escape(text[position:match.start()]))
        label, target = match.groups()
        if target in DOCUMENTS:
            target += ".html"
        elif target.startswith(prefix):
            relative, separator, anchor = target[len(prefix):].partition("#")
            if relative in SOURCE_PINS:
                target = "sources/" + relative + ".html" + (separator + anchor if separator else "")
        if target.startswith(("https://", "http://", "sources/")) or target in {n + ".html" for n in DOCUMENTS}:
            parts.append(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')
        else:
            parts.append(html.escape(match.group()))
        position = match.end()
    parts.append(html.escape(text[position:]))
    return '<pre class="document">' + "".join(parts) + "</pre>"


def rendered_files(documents: dict[str, bytes], sources: dict[str, bytes]) -> dict[str, bytes]:
    facts = json.loads(sources["facts.json"])["facts"]
    unknowns = sorted((f for f in facts if f["status"] == "unknown"), key=lambda f: f["fact_id"])
    output = {name + ".html": page(name, document_view(data)) for name, data in documents.items()}
    for name, data in sources.items():
        home = "../" * (len(PurePosixPath(name).parts)) + "index.html"
        lines = "".join(f'<li id="L{i}">{html.escape(line)}</li>'
                        for i, line in enumerate(data.decode("utf-8").splitlines(), 1))
        body = (f'<p>Unchanged retained source · Git blob <code>{SOURCE_PINS[name]}</code><br>'
                f'<a href="{html.escape(PurePosixPath(name).name, quote=True)}">Raw file</a></p>'
                f'<ol class="lines">{lines}</ol>')
        output["sources/" + name + ".html"] = page(name, body, home)
    doc_links = "".join(f'<a href="{name}.html">{name.removesuffix(".md").replace("_", " ").title()}</a>'
                        for name in ("HANDOVER.md", "SYNTHESIS.md", "SOURCE_REGISTER.md", "EXERCISE.md", "README.md"))
    unknown_rows = "".join(f'<tr><td><code>{html.escape(f["fact_id"])}</code></td>'
                           f'<td>{html.escape(f["statement"])}</td></tr>' for f in unknowns)
    source_rows = "".join(f'<tr><td><a href="sources/{name}.html">{name}</a></td>'
                          f'<td><code>{SOURCE_PINS[name]}</code></td></tr>' for name in sorted(sources))
    body = (f'<p class="notice">Start with the handover, then the completed synthesis. '
            f'This offline copy retains {len(facts)} original facts and {len(sources)} source files. '
            'The authored findings are a fictional rehearsal, not University conclusions or client acceptance.</p>'
            f'<nav>{doc_links}</nav><h2>Open inputs stay open</h2>'
            f'<table><thead><tr><th>Original fact</th><th>Unchanged UNKNOWN statement</th></tr></thead>'
            f'<tbody>{unknown_rows}</tbody></table><h2>Continue from the retained packet</h2>'
            '<p>Read scope, ownership roles, review responses and next deliverable in the handover. '
            'Synthesis citations open the exact local source line. Raw Markdown and original source bytes '
            'remain beside these browser views.</p><p>To check this copy with Python 3.10 or later: '
            '<code>python bundle.py verify .</code>. The manifest checks byte continuity, not truth or authenticity.</p>'
            f'<h2>Selected source snapshot</h2><p><code>{REVISION}</code></p>'
            f'<table><thead><tr><th>Retained source</th><th>Git blob</th></tr></thead><tbody>{source_rows}</tbody></table>'
            '<h2>Historical companion</h2><p>EXERCISE.md preserves the original author’s reported continuation run. '
            'This bundle packages the published documents and original corpus; it does not contain or rerun '
            'the separately described historical continuation.py or its tests.</p>')
    output["index.html"] = page("Analyst handover", body)
    return output


def assemble(collection: Path, out: Path) -> None:
    collection, out = collection.resolve(), out.absolute()
    if out.exists() or out.is_symlink():
        raise ValueError(f"output already exists; choose a new directory: {out}")
    here = Path(__file__).resolve().parent
    documents = {name: read_file(here, name) for name in DOCUMENTS}
    sources = {name: read_file(collection, name) for name in SOURCE_PINS}
    check_sources(sources)
    register = documents["SOURCE_REGISTER.md"].decode()
    if REVISION not in register or any(f"| {name} | `{sha}` |" not in register for name, sha in SOURCE_PINS.items()):
        raise ValueError("SOURCE_REGISTER.md differs from the selected snapshot; update the handover deliberately")
    files = {**documents, **{"sources/" + name: data for name, data in sources.items()},
             "bundle.py": Path(__file__).read_bytes(), **rendered_files(documents, sources)}
    manifest = {"schema": SCHEMA, "synthetic": True, "source_revision": REVISION,
                "files": {name: describe(data) for name, data in sorted(files.items())}}
    files["bundle-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Validate a complete staged snapshot before reserving the final directory.
    with tempfile.TemporaryDirectory(prefix="uiowa138-", dir=out.parent) as temporary:
        stage = Path(temporary)
        for name, data in files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        native_validate(stage / "sources")
        out.mkdir()  # Exclusive: never overwrite an existing handover.
        for name in sorted(files):
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (stage / name).rename(target)
    print(f"HANDOVER_BUNDLED sources={len(sources)} hashed_files={len(files) - 1} index={out / 'index.html'}")


def verify(root: Path) -> None:
    root = root.resolve()
    manifest = json.loads(read_file(root, "bundle-manifest.json"))
    if manifest.get("schema") != SCHEMA or manifest.get("source_revision") != REVISION or manifest.get("synthetic") is not True:
        raise ValueError("bundle metadata does not match this handover snapshot")
    recorded = manifest.get("files")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("bundle manifest has no files")
    required = {*DOCUMENTS, "bundle.py", "index.html", *("sources/" + n for n in SOURCE_PINS)}
    if required - recorded.keys():
        raise ValueError("manifest omits required files: " + ", ".join(sorted(required - recorded.keys())))
    for name, expected in recorded.items():
        if describe(read_file(root, name)) != expected:
            raise ValueError(f"bundle file changed: {name}")
    sources = {name: read_file(root, "sources/" + name) for name in SOURCE_PINS}
    check_sources(sources)
    native_validate(root / "sources")
    print(f"HANDOVER_VERIFIED sources={len(sources)} hashed_files={len(recorded)} source_revision={REVISION}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("assemble", help="copy the registered source snapshot into a new offline bundle")
    build.add_argument("--collection", type=Path, required=True, help="directory containing the fourteen registered source files")
    build.add_argument("--out", type=Path, required=True, help="new output directory; existing output is preserved")
    check = sub.add_parser("verify", help="check retained bytes and run the original collection validator")
    check.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "assemble":
            assemble(args.collection, args.out)
        else:
            verify(args.bundle)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
