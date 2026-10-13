"""Extract a previously hash-verified Astral runtime, without its build objects."""
from __future__ import annotations
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('archive', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
proc = subprocess.Popen(['zstd', '-dc', str(args.archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
count = total = 0
try:
    with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'python':
                raise ValueError('Unexpected archive path')
            allowed = member.name == 'python/PYTHON.json' or member.name.startswith(('python/install/', 'python/licenses/'))
            if not allowed:
                continue
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError('Unexpected member type')
            count += 1
            total += member.size
            if count > 20000 or total > 2 * 1024**3:
                raise ValueError('Runtime archive exceeds extraction bounds')
            archive.extract(member, path=args.output, filter='data')
    proc.stdout.close()
    stderr = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError('zstd decompression failed')
except BaseException:
    proc.kill()
    proc.wait()
    raise
print(json.dumps({'selected_members': count, 'uncompressed_regular_bytes': total, 'root': str(args.output)}, indent=2))
