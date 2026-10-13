# SPDX-License-Identifier: Apache-2.0
"""Package existing receipts and source without running or fitting policies."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent


def archive(paths, root):
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode='w:xz', preset=6) as tar:
        for path in sorted(paths):
            data = path.read_bytes()
            info = tarfile.TarInfo(str(path.relative_to(root)))
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    return target.getvalue()


def package(trace_archive):
    destination = HERE / 'artifacts'
    source = [p for p in HERE.rglob('*') if p.is_file() and
              not set(p.relative_to(HERE).parts) & {'results', 'artifacts', '__pycache__'}]
    receipts = [p for p in (HERE / 'results').rglob('*.json')]
    archives = {'receipts.tar.xz': archive(receipts, HERE),
                'runtime.tar.xz': archive(source, HERE),
                'full-traces.xz': trace_archive.read_bytes()}
    manifest = {'schema_version': 1, 'encoding': 'concatenated base64 text parts', 'archives': []}
    for name, raw in archives.items():
        entry = {'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'parts': []}
        data = base64.b64encode(raw)
        for index, start in enumerate(range(0, len(data), 160000)):
            chunk = data[start:start + 160000]
            part_name = name + f'.part{index:03d}.b64'
            (destination / part_name).write_bytes(chunk)
            entry['parts'].append({'name': part_name, 'bytes': len(chunk),
                                   'sha256': hashlib.sha256(chunk).hexdigest()})
        manifest['archives'].append(entry)
    (destination / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace-archive', type=Path, required=True)
    print(json.dumps(package(p.parse_args().trace_archive), indent=2))
