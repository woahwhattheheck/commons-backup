#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the current-source custody gate; historical dynamic evidence is separate."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main() -> int:
    runs=[]
    for optimized in (False, True):
        cmd=[sys.executable]
        if optimized: cmd.append("-O")
        cmd += [str(HERE/'test_integrated_action_prefix.py'), '-q']
        p=subprocess.run(cmd, cwd=HERE, text=True, capture_output=True)
        runs.append({'optimized':optimized,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    print(json.dumps({'schema':'titan-v4-integrated-prefix-current-source-gate/v1','runs':runs}, indent=2))
    return 0 if all(r['returncode']==0 for r in runs) else 1

if __name__ == '__main__':
    raise SystemExit(main())
