from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from .cli import _changed
from .guard import analyze_source, scan_paths


class ReviewClosureTests(unittest.TestCase):
    def rules(self, source: str) -> list[str]:
        return [finding.rule for finding in analyze_source(source, path="revenue/x.py")]

    def test_public_class_method_and_self_helper_are_visible(self):
        source = '''
DEADLINE = object()
class Gate:
    def _project(self, packet):
        current = packet["as_of"]
        if current > DEADLINE:
            return "HOLD"
        return "PRIME_READY"
    def evaluate(self, packet):
        return self._project(packet)
'''
        rules = self.rules(source)
        self.assertIn("CRG001", rules)
        self.assertIn("CRG003", rules)

    def test_class_helper_authority_maps_to_public_method(self):
        source = '''
class Gate:
    def _project(self, packet, authority_root):
        return "PRIME_READY" if authority_root else "HOLD"
    def evaluate(self, packet, authority_root):
        return self._project(packet, authority_root)
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_branch_assignment_positive_is_not_erased(self):
        source = '''
def evaluate(packet):
    if packet.get("verified"):
        state = "PRIME_READY"
    else:
        state = "HOLD"
    return state
'''
        self.assertIn("CRG003", self.rules(source))

    def test_branch_assignment_authority_is_preserved(self):
        source = '''
def evaluate(packet, authority_root):
    if authority_root:
        state = "PRIME_READY"
    else:
        state = "HOLD"
    return state
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_sequential_hold_overwrite_is_not_positive(self):
        source = '''
def evaluate(packet):
    state = "PRIME_READY"
    state = "HOLD"
    return state
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_constructor_string_and_boolean_readiness_are_visible(self):
        self.assertIn("CRG003", self.rules('def evaluate(packet):\n return Decision(state="PRIME_READY")\n'))
        self.assertIn("CRG003", self.rules('def evaluate(packet):\n return Decision(ready=True)\n'))
        self.assertIn("CRG003", self.rules('def evaluate(packet):\n return {"submission_ready": packet.get("verified")}\n'))

    def test_boolean_authority_and_false_are_not_positive_bypasses(self):
        self.assertNotIn(
            "CRG003",
            self.rules('def evaluate(packet, authority_root):\n return {"submission_ready": authority_root}\n'),
        )
        self.assertNotIn(
            "CRG003",
            self.rules('def evaluate(packet):\n return {"submission_ready": False}\n'),
        )

    def test_nested_helper_and_callable_aliases_are_reachable(self):
        nested = '''
def evaluate(packet):
    def project():
        return "PRIME_READY"
    return project()
'''
        alias = '''
def _project(packet):
    return "PRIME_READY"
def evaluate(packet):
    project = _project
    return project(packet)
'''
        lam = '''
def evaluate(packet):
    project = lambda: "PRIME_READY"
    return project()
'''
        for source in (nested, alias, lam):
            self.assertIn("CRG003", self.rules(source))

    def test_aliases_preserve_deadline_and_replay_flow(self):
        deadline = '''
DEADLINE = object()
def _project(value):
    if value > DEADLINE:
        return "HOLD"
    return "PRIME_READY"
def evaluate(packet):
    project = _project
    return project(packet["as_of"])
'''
        replay = '''
def _replay(packet, report):
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt == report
def verify_report(packet, report):
    replay = _replay
    return replay(packet, report)
'''
        self.assertIn("CRG001", self.rules(deadline))
        self.assertIn("CRG004", self.rules(replay))

    def test_trusted_clock_is_bound_to_real_stdlib_imports(self):
        safe = '''
from datetime import datetime, timezone
def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh["state"] == report["state"]
'''
        shadowed = '''
from datetime import datetime
datetime = FakeClock()
def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now()
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh["state"] == report["state"]
'''
        caller = '''
def verify_report(packet, report, timer):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = timer.current_utc()
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh["state"] == report["state"]
'''
        self.assertNotIn("CRG004", self.rules(safe))
        self.assertIn("CRG004", self.rules(shadowed))
        self.assertIn("CRG004", self.rules(caller))

    def test_fresh_projection_must_be_unavoidable_on_acceptance(self):
        overwritten = '''
from datetime import datetime, timezone
def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    fresh = compile_state(packet, as_of=report["evaluated_at"])
    return retained == report and fresh["state"] == report["state"]
'''
        disjunction = '''
from datetime import datetime, timezone
def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    return retained == report or fresh["state"] == report["state"]
'''
        failure_then_fresh = '''
from datetime import datetime, timezone
def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    if retained != report:
        return False
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    return fresh["state"] == report["state"]
'''
        self.assertIn("CRG004", self.rules(overwritten))
        self.assertIn("CRG004", self.rules(disjunction))
        self.assertNotIn("CRG004", self.rules(failure_then_fresh))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_leaf_and_intermediate_directory_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            target = outside / "gate.py"
            target.write_text('def evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8")
            (root / "revenue").mkdir()
            os.symlink(target, root / "revenue" / "leaf.py")
            os.symlink(outside, root / "revenue" / "linked")
            self.assertEqual(
                [finding.rule for finding in scan_paths(["revenue/leaf.py"], root=root)],
                ["CRG000"],
            )
            self.assertEqual(
                [finding.rule for finding in scan_paths(["revenue/linked/gate.py"], root=root)],
                ["CRG000"],
            )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "fifo unavailable")
    def test_fifo_fails_closed_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "revenue").mkdir()
            os.mkfifo(root / "revenue" / "gate.py")
            self.assertEqual(
                [finding.rule for finding in scan_paths(["revenue/gate.py"], root=root)],
                ["CRG000"],
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_git_type_change_to_symlink_remains_in_changed_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "guard@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Guard Test"], cwd=root, check=True)
            (root / "revenue").mkdir()
            gate = root / "revenue" / "gate.py"
            gate.write_text("x = 1\n", encoding="utf-8")
            (root / "outside.py").write_text("x = 2\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            gate.unlink()
            os.symlink(root / "outside.py", gate)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "head"], cwd=root, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            old = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(_changed(base, head), ["revenue/gate.py"])
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
