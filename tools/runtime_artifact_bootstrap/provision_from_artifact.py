"""Provision one pinned, connector-downloaded Linux x86_64 Python runtime.

Requires a bootstrap Python with tarfile.data_filter and a local zstd executable.
This performs no network requests and never overwrites an existing destination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def provision(key: str, archive_zip: Path, output: Path) -> dict[str, Any]:
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'Only Linux x86_64 is supported by these pinned artifacts')
    require(hasattr(tarfile, 'data_filter'), 'Bootstrap Python needs tarfile.data_filter')
    require(shutil.which('zstd') is not None, 'A local zstd executable is required')
    pins = json.loads((ROOT / 'runtime_receipts.json').read_text(encoding='utf-8'))['artifacts']
    require(key in pins, 'Unknown pinned runtime')
    spec = pins[key]
    require(not output.exists() and not output.is_symlink(), 'Destination must not exist')
    parent = output.parent.resolve(strict=True)
    require(parent.is_dir(), 'Destination parent must be an existing trusted directory')
    archive_zip = archive_zip.resolve(strict=True)
    require(archive_zip.is_file(), 'Artifact must be a regular file')
    require(archive_zip.stat().st_size == spec['zip_bytes'], 'Artifact byte count mismatch')
    require(sha256(archive_zip) == spec['zip_sha256'], 'Artifact SHA-256 mismatch')

    with tempfile.TemporaryDirectory(prefix='pinned-runtime-', dir=parent) as scratch:
        archive = Path(scratch) / 'runtime.tar.zst'
        with zipfile.ZipFile(archive_zip) as zf:
            require(zf.namelist() == [spec['archive_member']], 'Unexpected ZIP member set')
            member = zf.getinfo(spec['archive_member'])
            require(0 < member.file_size <= 512 * 1024**2, 'Archive exceeds size bound')
            with zf.open(member) as src, archive.open('xb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        require(sha256(archive) == spec['archive_sha256'], 'Inner archive SHA-256 mismatch')
        extracted = subprocess.run(
            [sys.executable, str(ROOT / 'extract_runtime.py'), str(archive), str(output)],
            capture_output=True, text=True, timeout=300, check=False,
        )
        require(extracted.returncode == 0, 'Extraction failed; destination is incomplete; inspect it before reuse')
        extraction_receipt = json.loads(extracted.stdout)

    metadata_path = output / 'python' / 'PYTHON.json'
    require(sha256(metadata_path) == spec['metadata_sha256'], 'Runtime metadata SHA-256 mismatch')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    require(metadata['python_version'] == spec['version'], 'Runtime metadata version mismatch')
    require(metadata['target_triple'] == 'x86_64-unknown-linux-gnu', 'Runtime target mismatch')
    executable = output / 'python' / 'install' / 'bin' / ('python' + spec['minor'])
    require(sha256(executable) == spec['executable_sha256'], 'Interpreter SHA-256 mismatch')
    # -I ignores ambient Python configuration; only standard-library imports run.
    smoke_code = (
        'import sys,json,ssl,sqlite3,hashlib,zlib,bz2,lzma,ctypes,unittest;'
        'print(json.dumps({"version":sys.version,"version_short":".".join(map(str,sys.version_info[:3])), '
        '"executable":sys.executable,"openssl":ssl.OPENSSL_VERSION,"sqlite":sqlite3.sqlite_version}))'
    )
    observed = json.loads(subprocess.check_output(
        [str(executable.resolve()), '-I', '-c', smoke_code],
        text=True, timeout=30, env={'PATH': os.environ.get('PATH', os.defpath)},
    ))
    require(observed['version_short'] == spec['version'], 'Actual interpreter version mismatch')
    receipt = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'runtime_key': key, 'artifact_id': spec['artifact_id'],
        'workflow_run_id': spec['workflow_run_id'],
        'workflow_source_head': spec['workflow_source_head'],
        'zip_sha256': spec['zip_sha256'], 'archive_sha256': spec['archive_sha256'],
        'executable_sha256': spec['executable_sha256'],
        'extraction': extraction_receipt, 'smoke': observed,
        'network_calls': False, 'hosted_ci_or_merge_authority': False,
    }
    with (output / 'provision_receipt.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('python310', 'python312'), required=True)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = provision(args.runtime, args.zip, args.output.absolute())
    except (ValueError, OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile,
            subprocess.SubprocessError) as exc:
        print('Runtime provisioning refused: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
