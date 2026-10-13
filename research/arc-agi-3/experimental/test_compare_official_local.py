from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "compare_official_local.py"

FAKE_PLAY = r'''
from pathlib import Path
import argparse
p=argparse.ArgumentParser(); p.add_argument('--list',action='store_true'); p.add_argument('--game'); p.add_argument('--max-steps'); a=p.parse_args()
if a.list:
    print('1 environments:')
    print('  ls20-deadbeef: Fake LS20')
    raise SystemExit(0)
text=(Path(__file__).resolve().parents[1]/'agent'/'my_agent.py').read_text()
if 'ObjectTransferExplorer' in text and '_BaseMyAgent' in text:
    levels,actions,score=3,21,42.5
else:
    levels,actions,score=2,63,20.0
print('========= SUMMARY =========')
print(f'  ls20     levels={levels:3}  actions={actions:5}  state=GameState.NOT_FINISHED')
print(f'Aggregate scorecard score: {score}')
'''


class CompareOfficialLocalTests(unittest.TestCase):
    def make_starter(self, root: Path) -> tuple[Path, bytes]:
        (root / 'scripts').mkdir(parents=True)
        (root / 'agent').mkdir(parents=True)
        (root / 'scripts' / 'play_local.py').write_text(textwrap.dedent(FAKE_PLAY))
        original=b'# original starter agent\n'
        (root / 'agent' / 'my_agent.py').write_bytes(original)
        return root, original

    def run_compare(self, starter: Path, output: Path):
        return subprocess.run(
            [
                sys.executable, str(RUNNER),
                '--starter-root', str(starter),
                '--python', sys.executable,
                '--game', 'ls20',
                '--max-steps', '400',
                '--stable', str(HERE / 'kaggle_my_agent.py'),
                '--builder', str(HERE / 'build_kaggle_v3.py'),
                '--output-dir', str(output),
            ],
            cwd=HERE,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_ab_receipt_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); starter,original=self.make_starter(root/'starter'); out=root/'out'
            proc=self.run_compare(starter,out)
            self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
            self.assertEqual((starter/'agent'/'my_agent.py').read_bytes(),original)
            receipt=json.loads((out/'ab-receipt.json').read_text())
            self.assertTrue(receipt['comparable'])
            self.assertFalse(receipt['competition_submission_performed'])
            self.assertEqual(receipt['game_exact_id_before'],'ls20-deadbeef')
            self.assertEqual(receipt['game_exact_id_after'],'ls20-deadbeef')
            arms={arm['label']:arm for arm in receipt['arms']}
            self.assertEqual(arms['stable_v2']['parsed']['summary']['actions'],63)
            self.assertEqual(arms['experimental_v3']['parsed']['summary']['actions'],21)
            self.assertEqual(arms['stable_v2']['parsed']['score'],20.0)
            self.assertEqual(arms['experimental_v3']['parsed']['score'],42.5)
            for arm in arms.values():
                self.assertEqual(len(arm['stdout_sha256']),64)
                self.assertEqual(len(arm['stderr_sha256']),64)

    def test_source_contains_no_submit_invocation(self):
        text=RUNNER.read_text()
        self.assertNotIn('make submit', text.lower().replace('`',''))
        self.assertNotIn('kaggle kernels', text.lower())

    def test_parse_requires_single_game_row(self):
        sys.path.insert(0,str(HERE))
        import compare_official_local as mod
        with self.assertRaises(ValueError):
            mod.parse_run('Aggregate scorecard score: 1.0\n','ls20')

    def test_positive_max_steps_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); starter,_=self.make_starter(root/'starter'); out=root/'out'
            proc=subprocess.run(
                [sys.executable,str(RUNNER),'--starter-root',str(starter),'--python',sys.executable,
                 '--game','ls20','--max-steps','0','--stable',str(HERE/'kaggle_my_agent.py'),
                 '--builder',str(HERE/'build_kaggle_v3.py'),'--output-dir',str(out)],
                cwd=HERE,text=True,capture_output=True,check=False,
            )
            self.assertNotEqual(proc.returncode,0)
            self.assertIn('--max-steps must be positive',proc.stderr+proc.stdout)


if __name__=='__main__': unittest.main(verbosity=2)
