# SPDX-License-Identifier: Apache-2.0
"""Source-bound observation-copy optimization; no production writes on import."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PARENT_BLOB = 'f810d53193d3035655a36c21021e18ba1d415916'
# This literal is replaced by the package generator with the tested byte hash.
CANDIDATE_SHA256 = '20e92f999b8794a91ca80914bba08032623c543a16541f3fbde38a4560760409'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def compose(source: bytes) -> bytes:
    """Replace only an authenticated helper, idempotently; reject source drift."""
    candidate = (HERE / 'observed_clone_candidate.py').read_bytes()
    if hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA256:
        raise ValueError('Candidate source authentication failed')
    if source == candidate:
        return source
    if git_blob(source) != PARENT_BLOB:
        raise ValueError('Native observed_clone.py changed; explicit rebase required')
    return candidate


def compose_tree(source: Path, destination: Path) -> None:
    """Create a separate testing tree; never update a source tree in place."""
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and output must be disjoint trees')
    if destination.exists():
        raise ValueError('Output tree already exists; refusing overwrite')
    replacement = compose((source / 'observed_clone.py').read_bytes())
    # Symlinks would make identity and output custody ambiguous.
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Runtime symlinks are not accepted')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (destination / 'observed_clone.py').write_bytes(replacement)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    compose_tree(args.source_root, args.output_root)
    print(git_blob((args.output_root / 'observed_clone.py').read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
