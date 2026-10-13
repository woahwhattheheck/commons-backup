#!/usr/bin/env python3
"""Build a source-bound validation probe, not a replacement solver runner."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from apply_route_flow import apply_bytes


def assemble(original: str, candidate: str, probe: str) -> str:
    includes = original[:original.index('using Sparse')]
    bodies = []
    for label, source in (('baseline', original), ('inplace', candidate)):
        body = source[source.index('using Sparse'):source.index('\nint main(')]
        if body.count('class Solver {') != 1:
            raise ValueError('cannot expose solver internals in probe')
        body = body.replace('class Solver {', 'class Solver {\npublic:', 1)
        bodies.append('namespace ' + label + ' {\n' + body + '\n}\n')
    return includes + '#include <cstring>\n#include <iomanip>\n' + ''.join(bodies) + '\n\n' + probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('vendor', type=Path, help='directory containing rapidjson/')
    parser.add_argument('output', type=Path, help='new build directory')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    source = args.source.read_bytes()
    candidate = apply_bytes(source)
    args.output.mkdir(parents=True, exist_ok=False)
    probe = Path(__file__).with_name('native_probe.inc').read_text()
    assembled = assemble(source.decode(), candidate.decode(), probe)
    (args.output / 'probe.cpp').write_text(assembled)
    (args.output / 'original.cpp').write_bytes(source)
    (args.output / 'candidate.cpp').write_bytes(candidate)
    flags = (['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
             if args.sanitize else ['-O3', '-DNDEBUG'])
    command = [args.cxx, *flags, '-std=c++20', '-I' + str(args.vendor.resolve()),
               str(args.output / 'probe.cpp'), '-o', str(args.output / 'probe')]
    run = subprocess.run(command, capture_output=True, timeout=240)
    (args.output / 'build.stdout').write_bytes(run.stdout)
    (args.output / 'build.stderr').write_bytes(run.stderr)
    manifest = {'source_sha256': hashlib.sha256(source).hexdigest(),
                'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
                'probe_sha256': hashlib.sha256(assembled.encode()).hexdigest(),
                'command': command, 'returncode': run.returncode}
    (args.output / 'BUILD.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, sort_keys=True))
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
