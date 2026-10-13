# SPDX-License-Identifier: Apache-2.0
"""Verify included dependency pins and build Apex using its original command."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
COMMAND = ['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic', '-shared', '-fPIC',
           '-Isource/include', '-o', 'agent.so', 'source/policy.cpp', 'submission_bridge.cpp']


def main():
    for name, row in json.loads((HERE / 'SOURCE-PINS.json').read_text())['files'].items():
        data = (HERE / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Dependency bytes differ: ' + name)
    subprocess.run(COMMAND, cwd=HERE / 'vendor/apex', check=True)


if __name__ == '__main__':
    main()
