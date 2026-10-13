"""Retain real-process proof that parent compiler/verify launches keep -O.

These tests exercise the subprocess helper, not a substitute parent compiler.
The separate integration test still requires the real upstream source closure.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_parent_integration as integration


class ParentExecutionModeTests(unittest.TestCase):
    def check_mode(self, level):
        # Deliberately choose each fresh parent's mode independently of the
        # unittest process. Do not let a runner's PYTHONOPTIMIZE mask the bug.
        environment = os.environ.copy()
        environment.pop('PYTHONOPTIMIZE', None)
        program = (
            'import json,sys; '
            'from test_parent_integration import _run_python; '
            "child=_run_python('-c','import sys; print(sys.flags.optimize)'); "
            "print(json.dumps({'parent':sys.flags.optimize,'child':int(child.stdout)}))"
        )
        result = subprocess.run(
            [sys.executable, *(['-O'] * level), '-c', program],
            cwd=HERE, env=environment, check=True, text=True,
            capture_output=True, timeout=30,
        )
        self.assertEqual(json.loads(result.stdout), {'parent': level, 'child': level})

    def test_normal_child(self):
        self.check_mode(0)

    def test_optimized_child(self):
        self.check_mode(1)

    def test_double_optimized_child(self):
        self.check_mode(2)

    def test_child_error_is_not_a_pass(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            integration._run_python('-c', 'raise SystemExit(7)')
        self.assertEqual(error.exception.returncode, 7)

    def test_arguments_remain_literal(self):
        literal = 'SYNTHETIC path with spaces / café / "quote" ; =1+1'
        result = integration._run_python(
            '-c', 'import json,sys; print(json.dumps(sys.argv[1]))', literal,
        )
        self.assertEqual(json.loads(result.stdout), literal)


if __name__ == '__main__':
    unittest.main()
