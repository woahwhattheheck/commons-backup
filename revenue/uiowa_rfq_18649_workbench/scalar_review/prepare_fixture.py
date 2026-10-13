#!/usr/bin/env python3
"""Create an exact-source before/after replay without changing the supplied workbench."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

BASE_COMMIT = "a89a5bc91f0f9a3dae736bee4a015caaf8d52567"
EXPECTED = {
    "app.js": "87110be97624cdb4442263060374ac8c4181dfad",
    "index.html": "b8b5e568b0bcf04095263c70e792643c6276bf05",
    "handoff_import.js": "20703283260781e87ef88c7ca0af17b380541f74",
    "handoff.js": "114e6c0bf9041a5dd178ed5b646e6b2069848d7e",
}
OLD = '''      throw new Error(`Analyst notes must be strings of at most ${MAX_NOTE_LENGTH} characters.`);
    }
    return value;
'''
NEW = '''      throw new Error(`Analyst notes must be strings of at most ${MAX_NOTE_LENGTH} characters.`);
    }
    // JSON permits escaped lone UTF-16 surrogates. Blob's UTF-8 conversion
    // replaces them with U+FFFD, so accepting them would make the JSON and
    // Markdown handoffs disagree. Iterate code points to keep valid pairs,
    // literal U+FFFD, combining sequences and all other scalar values intact.
    for (const character of value) {
      const codePoint = character.codePointAt(0);
      if (codePoint >= 0xD800 && codePoint <= 0xDFFF) {
        throw new Error("Analyst notes must contain valid Unicode scalar values; an unpaired surrogate cannot be exported without changing the text.");
      }
    }
    return value;
'''


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def prepare(source: Path, output: Path) -> dict:
    """Validate all four source identities before creating a new output directory."""
    data = {name: (source / name).read_bytes() for name in EXPECTED}
    for name, expected in EXPECTED.items():
        actual = git_blob(data[name])
        if actual != expected:
            raise ValueError(f"{name}: expected {expected}, got {actual}; source changed, review before rebinding")
    text = data["handoff.js"].decode("utf-8")
    if text.count(OLD) != 1:
        raise ValueError("shared note-validation seam is not unique")
    repaired = text.replace(OLD, NEW).encode("utf-8")
    output.mkdir(parents=False, exist_ok=False)
    for variant in ("before", "after"):
        directory = output / variant
        directory.mkdir()
        for name, raw in data.items():
            with (directory / name).open("xb") as handle:
                handle.write(repaired if variant == "after" and name == "handoff.js" else raw)
    manifest = {
        "base_commit": BASE_COMMIT,
        "before": EXPECTED,
        "after": {**EXPECTED, "handoff.js": git_blob(repaired)},
        "limits": "Synthetic UI replay; no HTTP, parent compiler, hosted CI, layout or live evidence acceptance.",
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Workbench directory from the exact published base")
    parser.add_argument("--out", type=Path, required=True, help="New directory; parent must exist")
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.out)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
