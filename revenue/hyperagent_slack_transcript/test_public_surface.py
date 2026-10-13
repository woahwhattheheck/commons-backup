from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from revenue.hyperagent_slack_transcript import (
    TranscriptProjector as PackageProjector,
    project_fixture as package_project_fixture,
)
from revenue.hyperagent_slack_transcript.adapter import (
    TranscriptProjector as AdapterProjector,
    ValidationError,
    load_strict_json,
    project_fixture as adapter_project_fixture,
)
from revenue.hyperagent_slack_transcript.stateful import (
    TranscriptProjector as StatefulProjector,
    project_fixture as stateful_project_fixture,
)


class PublicSurfaceTests(unittest.TestCase):
    def test_all_public_surfaces_share_canonical_projector(self):
        self.assertIs(AdapterProjector, PackageProjector)
        self.assertIs(StatefulProjector, PackageProjector)
        self.assertIs(adapter_project_fixture, package_project_fixture)
        self.assertIs(stateful_project_fixture, package_project_fixture)

    def test_recursive_json_is_controlled_in_real_cli_normal_and_optimized(self):
        # A valid JSON value deep enough to exceed CPython's decoder recursion
        # limit must be a contract error, never a raw interpreter traceback.
        nested = "[" * 2500 + "0" + "]" * 2500
        with self.assertRaises(ValidationError):
            load_strict_json(nested)

        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "nested.json"
            src.write_text(nested, encoding="utf-8")
            for optimized in (False, True):
                out = td / ("out-opt.json" if optimized else "out.json")
                argv = [sys.executable]
                if optimized:
                    argv.append("-O")
                argv.extend([
                    "-m",
                    "revenue.hyperagent_slack_transcript.cli",
                    str(src),
                    str(out),
                ])
                completed = subprocess.run(
                    argv,
                    cwd=root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
