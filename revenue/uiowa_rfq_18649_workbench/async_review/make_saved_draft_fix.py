"""Derive the pinned saved-draft repair; importing this module changes no files."""
from __future__ import annotations
import argparse
import difflib
import hashlib
from pathlib import Path

BASE_BLOB = '808a89401a7978c4897feb351aee231adcba8dd6'
FIXED_BLOB = 'e570dcac8dd6bb6d35d5f8fede6c84b2220e8bb4'

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()

def derive(raw: bytes) -> tuple[bytes, str]:
    if git_blob(raw) != BASE_BLOB:
        raise ValueError('Wrong patch base; reconcile current source instead of guessing')
    before = raw.decode('utf-8')
    read = '    const contents = await file.text();\n'
    validation = '    const restored = HandoffImport.parseDraft(contents, report);'
    if before.count(read) != 1 or before.count(validation) != 1:
        raise ValueError('Missing or ambiguous saved-draft seam')
    after = before.replace(read, '    const bytes = await file.arrayBuffer();\n')
    after = after.replace(validation, '''    // File.text() substitutes malformed UTF-8. Decode bytes strictly before
    // replacing any notes so corrupt input cannot become a successful restore.
    let contents;
    try { contents = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
    catch { throw new Error("Saved draft is not valid UTF-8. Existing notes were not changed."); }
    const restored = HandoffImport.parseDraft(contents, report);''')
    encoded = after.encode('utf-8')
    if git_blob(encoded) != FIXED_BLOB:
        raise ValueError('Reference repair no longer matches the independently tested app')
    patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/revenue/uiowa_rfq_18649_workbench/app.js',
        tofile='b/revenue/uiowa_rfq_18649_workbench/app.js'))
    return encoded, patch

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent,
                        help='Both output files must be absent; no overwrite or directory deletion')
    args = parser.parse_args()
    try:
        fixed, patch = derive(Path(__file__).with_name('composed_app.js').read_bytes())
        paths = [args.output_dir/'fixed_app.js', args.output_dir/'saved_draft_utf8.patch']
        if any(path.exists() or path.is_symlink() for path in paths):
            raise ValueError('Reference output exists; choose a fresh output directory')
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for path, data in zip(paths, [fixed, patch.encode('utf-8')]):
            with path.open('xb') as stream:
                stream.write(data)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f'REFUSED: {exc}\n')
    print(f'REFERENCE_REPAIR {FIXED_BLOB}; no production file changed')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
