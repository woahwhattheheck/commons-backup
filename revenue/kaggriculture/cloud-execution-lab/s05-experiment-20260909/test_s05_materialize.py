# SPDX-License-Identifier: Apache-2.0
"""S05 hosted materialize pins the published archive; it does not re-render."""
import os
import unittest
from pathlib import Path

DISPATCH = "741d76f345921ded3cd436dab02fe5b8555f2d25"
ARCHIVE_SHA = "0215384841e2eec7f919f82ea900f343f1dc75665747a45e8df8f6b33316c1e5"
SOURCE_SHA = "374ebfbed35ee9102fe75db855de03e848a3dbca487f13d66bca29248c71bb54"
WORKFLOW = ".github/workflows/titan-s05-experiment.yml"


def workflow_path():
    here = Path(__file__).resolve()
    candidates = [here.parents[4] / WORKFLOW]
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        candidates.append(Path(workspace) / WORKFLOW)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(WORKFLOW)


def materialize_script(text):
    marker = "name: Materialize pinned current runtime"
    start = text.index(marker)
    rest = text[start:]
    run_at = rest.index("run: |")
    body = rest[run_at + len("run: |"):]
    next_step = body.find("\n      - name:")
    if next_step < 0:
        next_step = body.find("\n      - uses:")
    return body[:next_step]


def executable_script(script):
    lines = []
    for line in script.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


class MaterializePin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = workflow_path()
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.script = materialize_script(cls.text)
        cls.exec_script = executable_script(cls.script)

    def test_workflow_file_is_the_hosted_s05_screen(self):
        self.assertIn("name: TITAN S05 exact event-macro screen", self.text)
        self.assertTrue(self.path.as_posix().endswith(WORKFLOW))

    def test_materialize_checks_out_frozen_dispatch_commit(self):
        self.assertIn(f"DISPATCH={DISPATCH}", self.exec_script)
        self.assertIn('git worktree add --detach /tmp/s05-dispatch "$DISPATCH"', self.exec_script)

    def test_materialize_does_not_rerender_via_build_integrated_check(self):
        self.assertNotIn("build_integrated.py", self.exec_script)
        self.assertNotIn("verify_current", self.exec_script)

    def test_materialize_pins_committed_pointer_and_archive_bytes(self):
        self.assertIn("CURRENT-ARCHIVE.json", self.exec_script)
        self.assertIn(ARCHIVE_SHA, self.exec_script)
        self.assertIn("sha256sum exports/titan-current.tar.gz", self.exec_script)
        self.assertIn(
            "json.load(open('runtime/integrated-selected/CURRENT-ARCHIVE.json'))['sha256']",
            self.exec_script,
        )

    def test_materialize_extracts_and_pins_source_manifest(self):
        self.assertIn("tar -xzf exports/titan-current.tar.gz -C /tmp/s05-runtime", self.exec_script)
        self.assertIn("sha256sum /tmp/s05-runtime/SOURCE.json", self.exec_script)
        self.assertIn(SOURCE_SHA, self.exec_script)

    def test_contract_step_runs_on_the_pr_checkout(self):
        self.assertIn("name: Pinned archive materialize contract", self.text)
        self.assertIn("test_s05_materialize.py", self.text)


if __name__ == "__main__":
    unittest.main()
