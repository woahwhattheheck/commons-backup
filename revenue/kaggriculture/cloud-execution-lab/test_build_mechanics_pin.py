# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class MechanicsPinTests(unittest.TestCase):
    def test_tampered_engine_is_rejected_with_and_without_optimization(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'kaggriculture.py'
            source.write_text('CROPS = {}\n')
            program = (
                'from pathlib import Path; import build_mechanics as builder; '
                'builder.SOURCE = Path(__import__("sys").argv[1]); '
                'builder._pinned_source()'
            )
            for optimized in (False, True):
                command = [sys.executable]
                if optimized:
                    command.append('-O')
                command.extend(['-c', program, str(source)])
                result = subprocess.run(
                    command,
                    cwd=HERE,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('engine source hash mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
