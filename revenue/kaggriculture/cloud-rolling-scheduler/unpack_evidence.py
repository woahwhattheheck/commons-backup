"""Verify and unpack the retained T03 evidence without network or overwrites."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import tarfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and str(p) == name


def unpack(source: Path, output: Path) -> dict:
    """Validate every byte and member before creating a new output directory."""
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing to overwrite: {output}')
    index = json.loads((source / 'INDEX.json').read_text())
    parts = []
    for item in index['parts']:
        name = item['name']
        if not safe_name(name) or '/' in name:
            raise ValueError('Unsafe evidence part name')
        data = (source / name).read_bytes()
        if digest(data) != item['sha256']:
            raise ValueError(f'Part hash mismatch: {name}')
        parts.append(data.strip())
    compressed = base64.b64decode(b''.join(parts), validate=True)
    if len(compressed) != index['archive_bytes'] or digest(compressed) != index['archive_sha256']:
        raise ValueError('Evidence archive hash/length mismatch')
    expected = index['uncompressed_tar_bytes']
    if not isinstance(expected, int) or not 0 < expected <= 16_000_000:
        raise ValueError('Invalid evidence expansion limit')
    decoder = lzma.LZMADecompressor()
    raw = decoder.decompress(compressed, max_length=expected + 1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError('Evidence expansion length mismatch')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive.getmembers():
            if not member.isfile() or not safe_name(member.name) or member.name in files:
                raise ValueError('Unsafe, duplicate or non-file archive member')
            data = archive.extractfile(member).read()
            if len(data) != member.size:
                raise ValueError('Truncated archive member')
            files[member.name] = data
    if len(files) != index['member_count']:
        raise ValueError('Evidence member count mismatch')
    manifest = json.loads(files['MANIFEST.json'])['files']
    if set(files) != set(manifest) | {'MANIFEST.json'}:
        raise ValueError('Evidence manifest membership mismatch')
    for name, record in manifest.items():
        if len(files[name]) != record['bytes'] or digest(files[name]) != record['sha256']:
            raise ValueError(f'Evidence member hash mismatch: {name}')
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    return {'output': str(output.resolve()), 'files': len(files),
            'archive_sha256': index['archive_sha256']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', type=Path, default=Path(__file__).resolve().parent / 'evidence')
    a = p.parse_args()
    print(json.dumps(unpack(a.source, a.output), indent=2))
