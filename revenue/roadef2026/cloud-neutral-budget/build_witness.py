#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile a test-only DATE consumer with the exact existing fleet source.

Two symbol/access edits expose private members for a witness; no function body,
search neighborhood, numerical rule, or production source file is changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

BASE = '322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1'
HEADER_BLOB = '5ce70d722c6d4e2f7c053990697387d9f46514fc'
HERE = Path(__file__).resolve().parent

def blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def build(fleet: Path, header: Path, output: Path, compiler: str='g++', sanitize: bool=False):
    raw, dep = (fleet/'main.cpp').read_bytes(), header.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE or blob(dep) != HEADER_BLOB:
        raise ValueError('Use the documented exact fleet and DATE source identities')
    source = raw.decode()
    for old,new in [('class Solver {', 'class Solver {\npublic:'),
                    ('int main(int argc, char** argv) {', 'int fleet_solver_main(int argc, char** argv) {')]:
        if source.count(old) != 1: raise ValueError('Unexpected source anchor')
        source = source.replace(old,new,1)
    output.mkdir(parents=True,exist_ok=False)
    (output/'fleet_visible.cpp').write_text(source)
    shutil.copyfile(header,output/'budget_release.hpp')
    shutil.copyfile(HERE/'witness.cpp',output/'witness.cpp')
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitize else ['-O2']
    cmd=[compiler,'-std=c++17',*flags,'-Wall','-Wextra','-pedantic',
         '-I',str((fleet/'vendor').resolve()),str(output/'witness.cpp'),'-o',str(output/'witness')]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    (output/'build.log').write_text(proc.stdout+proc.stderr)
    proc.check_returncode()
    report={'base_sha256':BASE,'date_header_blob':HEADER_BLOB,'command':cmd,
            'compiler':subprocess.run([compiler,'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],
            'harness_sha256':hashlib.sha256((output/'witness.cpp').read_bytes()).hexdigest(),
            'exposed_source_sha256':hashlib.sha256((output/'fleet_visible.cpp').read_bytes()).hexdigest(),
            'binary_sha256':hashlib.sha256((output/'witness').read_bytes()).hexdigest(),
            'meaning':'Compiled test harness, not a submission agent or score result'}
    (output/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fleet',type=Path,required=True);p.add_argument('--header',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',default='g++')
    p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.fleet.resolve(),a.header.resolve(),a.output.resolve(),a.compiler,a.sanitize),indent=2))
