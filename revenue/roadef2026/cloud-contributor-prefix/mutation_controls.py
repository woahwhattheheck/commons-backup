#!/usr/bin/env python3
"""Compile the actual prepared methods with deliberately wrong prefix variants.

The unmodified candidate must pass the native comparison. Each mutation must
compile and then fail that comparison, not merely fail compilation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

MUTATIONS = {
    'reversed_id_tie': ('a.second < b.second', 'a.second > b.second'),
    'ignore_exclusion': ('d == excluded || ', ''),
    'wrong_prefix_size': ('std::min(limit, result.size())',
                          'std::min(limit == 0 ? limit : limit - 1, result.size())'),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--cc', default='g++')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAIL', 'cases': []}
    try:
        compiler = shutil.which(args.cc)
        if compiler is None:
            raise ValueError('compiler unavailable')
        prepared = out / 'prepared'
        subprocess.run([sys.executable, str(Path(__file__).with_name('prepare_native.py')),
                        str(args.source.resolve()), str(prepared)], check=True, timeout=10)
        original = (prepared / 'candidate.hpp').read_text()
        variants = {'unmodified': original}
        for name, (old, new) in MUTATIONS.items():
            if original.count(old) != 1:
                raise ValueError('mutation source anchor changed: ' + name)
            variants[name] = original.replace(old, new)
        report['source_sha256'] = hashlib.sha256(args.source.read_bytes()).hexdigest()
        for name, content in variants.items():
            root = out / name
            root.mkdir()
            for path in prepared.iterdir():
                if path.is_file():
                    shutil.copy2(path, root / path.name)
            (root / 'candidate.hpp').write_text(content)
            binary = root / 'control'
            command = [compiler, '-std=c++20', '-O2', '-Wall', '-Wextra',
                       str(root / 'native_prefix.cpp'), '-o', str(binary)]
            build = subprocess.run(command, capture_output=True, timeout=45)
            (root / 'build.stdout').write_bytes(build.stdout)
            (root / 'build.stderr').write_bytes(build.stderr)
            if build.returncode != 0:
                raise ValueError(name + ' did not compile')
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            (root / 'run.stdout').write_bytes(result.stdout)
            (root / 'run.stderr').write_bytes(result.stderr)
            if name == 'unmodified':
                matched = (result.returncode == 0 and
                           json.loads(result.stdout) == {'status': 'PASS', 'comparisons': 21600})
            else:
                matched = result.returncode == 1 and b'mismatch' in result.stderr
            report['cases'].append({'name': name, 'compile_exit': build.returncode,
                                    'exit': result.returncode, 'matched': matched,
                                    'build_command': command})
            if not matched:
                raise ValueError(name + ' did not produce the required outcome')
        report['status'] = 'PASS'
        print('PASS: original comparison plus three compiled defect controls')
    finally:
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
