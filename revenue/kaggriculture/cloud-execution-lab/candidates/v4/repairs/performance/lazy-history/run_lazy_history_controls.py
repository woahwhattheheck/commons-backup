# SPDX-License-Identifier: Apache-2.0
"""Reject semantically broken lazy-history implementations in normal/-O Python."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from build_lazy_history import compose


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    source=(args.runtime/'terminal_history_join.py').read_text()
    candidate=compose(source)
    variants={
        'eager-unchanged':source,
        'eager-nonterminal':candidate.replace('if terminal_enabled:self._initialize_terminal()',
            'self._ensure_history()\n        if terminal_enabled:self._initialize_terminal()'),
        'lose-pending-on-first-use-cut':candidate.replace(
            '        bridge=self.bridge\n        self.pending=None',
            '        self.pending=None\n        bridge=self.bridge'),
        'wrong-history-period':candidate.replace('period=self._history_period','period=24'),
        'rebuild-every-access':candidate.replace('if self._history_components is None:', 'if True:'),
        'shared-agent-state':candidate.replace('        self._history_components=None',
            "        self._history_components=getattr(type(self),'_shared_history',None)").replace(
            '            self._history_components=(mechanics,completed)',
            '            self._history_components=(mechanics,completed)\n            type(self)._shared_history=self._history_components'),
    }
    results=[]
    with tempfile.TemporaryDirectory(prefix='lazy-history-controls-') as temporary:
        temporary=Path(temporary)
        for mode in ([],['-O']):
            for name,text in variants.items():
                path=temporary/(name+'.py');path.write_text(text)
                receipt=temporary/(name+str(bool(mode))+'.json')
                command=[sys.executable,*mode,str(Path(__file__).with_name('check_lazy_history.py')),
                    '--runtime',str(args.runtime.resolve()),'--candidate',str(path),'--receipt',str(receipt)]
                process=subprocess.run(command,capture_output=True,text=True,timeout=20)
                if not receipt.exists():
                    raise RuntimeError(f'{name}: harness failed before reporting test evidence')
                report=json.loads(receipt.read_text())
                rejected=process.returncode!=0 and report['failures']>0
                results.append({'variant':name,'optimized_python':bool(mode),'rejected':rejected,
                    'behavioral_assertion_failures':report['failures'],'errors':report['errors']})
                if not rejected:
                    raise RuntimeError(f'{name}: control escaped behavioral assertions')
    args.receipt.write_text(json.dumps({'controls':results,'all_rejected':True},indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
