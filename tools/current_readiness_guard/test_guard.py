from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from .guard import PolicyError, analyze_source, apply_policy, load_policy, scan_paths
from .cli import _changed


class GuardTests(unittest.TestCase):
    def rules(self, source: str):
        return [f.rule for f in analyze_source(source, path="revenue/x.py")]

    def test_caller_clock_vs_deadline_is_flagged(self):
        src = '''
DEADLINE = "2026-09-21T21:30:00Z"
def evaluate(packet):
    now = parse(packet["as_of"])
    if now > DEADLINE:
        return {"state": "HOLD"}
    return {"state": "PRIME_READY"}
'''
        rules = self.rules(src)
        self.assertIn("CRG001", rules)
        self.assertIn("CRG003", rules)

    def test_nested_time_alias_does_not_evade_taint(self):
        src = '''
CLOSE_AT = object()
def qualify(packet, authority_root):
    stamp = packet.get("as_of")
    parsed = normalize(stamp)
    current = parsed
    if current >= CLOSE_AT:
        return "HOLD"
    return "TEAMING_READY"
'''
        self.assertIn("CRG001", self.rules(src))

    def test_public_current_positive_time_override_is_flagged(self):
        src = '''
def qualify(packet, authority_root, trusted_as_of):
    if trusted_as_of:
        return "TEAMING_READY"
    return "HOLD"
'''
        self.assertIn("CRG002", self.rules(src))

    def test_single_packet_ready_is_flagged(self):
        src = '''
def evaluate(packet):
    if packet.get("verified"):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertEqual(self.rules(src), ["CRG003"])

    def test_independent_authority_parameter_avoids_single_packet_rule(self):
        src = '''
def evaluate(packet, authority_root):
    if authority_root and packet.get("verified"):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertNotIn("CRG003", self.rules(src))

    def test_process_owned_clock_is_not_caller_clock(self):
        src = '''
from datetime import datetime, timezone
DEADLINE = object()
def evaluate(packet, authority_root):
    now = datetime.now(timezone.utc)
    if now > DEADLINE:
        return "HOLD"
    if authority_root:
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertNotIn("CRG001", self.rules(src))
        self.assertNotIn("CRG002", self.rules(src))
        self.assertNotIn("CRG003", self.rules(src))

    def test_historical_hold_surface_is_safe(self):
        src = '''
def compile_historical(packet, trusted_as_of):
    projection = project(packet, trusted_as_of)
    projection["state"] = "HOLD"
    return projection
'''
        self.assertEqual(self.rules(src), [])

    def test_retained_time_current_verifier_is_flagged(self):
        src = '''
def verify_report(packet, report):
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
'''
        self.assertIn("CRG004", self.rules(src))

    def test_verifier_reacquiring_process_clock_avoids_retained_time_rule(self):
        src = '''
def verify_report(packet, report):
    current = _process_now()
    retained = compile_state(packet, as_of=report["evaluated_at"])
    now = compile_state(packet, as_of=current)
    return retained == report and now["state"] == report["state"]
'''
        self.assertNotIn("CRG004", self.rules(src))

    def test_malformed_python_is_finding_not_skip(self):
        findings = analyze_source("def broken(:\n", path="revenue/broken.py")
        self.assertEqual([f.rule for f in findings], ["CRG000"])

    def test_inline_comment_cannot_suppress(self):
        src = '''
def evaluate(packet):  # readiness-guard: ignore CRG003
    return "PRIME_READY"
'''
        self.assertEqual(self.rules(src), ["CRG003"])

    def test_active_central_exemption_is_exact_path_and_rule(self):
        raw = json.dumps({
            "schema": "commons-current-readiness-guard-policy/v1",
            "exemptions": [{
                "path": "revenue/x.py", "rule": "CRG003",
                "rationale": "legacy migration tracked until authority adapter lands",
                "owner": "Z-Owner", "issue": "#123", "expires": "2026-10-01",
            }],
        })
        exemptions = load_policy(raw, today=date(2026, 9, 14))
        findings = analyze_source('def evaluate(packet):\n return "PRIME_READY"\n', path="revenue/x.py")
        self.assertEqual(apply_policy(findings, exemptions), [])
        other = analyze_source('def evaluate(packet):\n return "PRIME_READY"\n', path="revenue/y.py")
        self.assertEqual([f.rule for f in apply_policy(other, exemptions)], ["CRG003"])

    def test_expired_exemption_fails_closed(self):
        raw = json.dumps({
            "schema": "commons-current-readiness-guard-policy/v1",
            "exemptions": [{
                "path": "revenue/x.py", "rule": "CRG003",
                "rationale": "temporary exception", "owner": "Z-Owner",
                "issue": "#123", "expires": "2026-09-13",
            }],
        })
        with self.assertRaisesRegex(PolicyError, "expired"):
            load_policy(raw, today=date(2026, 9, 14))

    def test_duplicate_policy_key_fails_closed(self):
        raw = '{"schema":"commons-current-readiness-guard-policy/v1","schema":"x","exemptions":[]}'
        with self.assertRaisesRegex(PolicyError, "duplicate JSON key"):
            load_policy(raw, today=date(2026, 9, 14))

    def test_scan_paths_never_imports_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "revenue" / "danger.py"
            path.parent.mkdir(parents=True)
            path.write_text('raise RuntimeError("must not execute")\ndef evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8")
            findings = scan_paths(["revenue/danger.py"], root=root)
            self.assertEqual([f.rule for f in findings], ["CRG003"])

    def test_non_revenue_python_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "misc.py"
            path.write_text('def evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8")
            self.assertEqual(scan_paths(["misc.py"], root=root), [])

    def test_scan_path_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            findings = scan_paths(["../escape.py"], root=td)
            self.assertEqual([f.rule for f in findings], ["CRG000"])

    def test_private_time_projection_is_not_current_surface(self):
        src = """
DEADLINE = object()
def _project(packet):
    t = packet["as_of"]
    if t > DEADLINE:
        return "HOLD"
    return "PRIME_READY"
"""
        self.assertNotIn("CRG001", self.rules(src))

    def test_public_verifier_time_override_is_flagged(self):
        src = """
def verify_current(report, verifier_now):
    if verifier_now:
        return "VALID"
    return "HOLD"
"""
        self.assertIn("CRG002", self.rules(src))

    def test_extra_caller_knob_does_not_evade_single_packet_authority(self):
        src = """
def evaluate(packet, mode):
    if packet.get("verified") and mode == "prime":
        return "PRIME_READY"
    return "HOLD"
"""
        self.assertIn("CRG003", self.rules(src))

    def test_changed_file_merge_base_selects_only_changed_revenue_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "guard@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Guard Test"], cwd=root, check=True)
            (root / "revenue").mkdir()
            (root / "revenue" / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "notes.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (root / "revenue" / "a.py").write_text("x = 2\n", encoding="utf-8")
            (root / "revenue" / "b.py").write_text("y = 3\n", encoding="utf-8")
            (root / "notes.txt").write_text("changed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "head"], cwd=root, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            old = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(_changed(base, head), ["revenue/a.py", "revenue/b.py"])
            finally:
                os.chdir(old)

    def test_positive_token_mentioned_only_in_validator_is_not_emission(self):
        src = """
def evaluate(packet, authority_root):
    if packet.get("state") == "PRIME_READY":
        return "HOLD"
    return "HOLD"
"""
        self.assertNotIn("CRG003", self.rules(src))

    def test_positive_state_assignment_is_treated_as_emission(self):
        src = """
def evaluate(packet):
    status = "PRIME_READY"
    return {"status": status}
"""
        self.assertIn("CRG003", self.rules(src))

    def test_subscript_clock_assignment_does_not_taint_entire_container(self):
        src = """
DEADLINE = object()
def evaluate(packet, authority_root):
    ctx = {}
    ctx["now"] = packet["as_of"]
    if ctx.get("unrelated") > DEADLINE:
        return "HOLD"
    return "PRIME_READY"
"""
        self.assertNotIn("CRG001", self.rules(src))

    def test_results_are_deterministically_sorted(self):
        src = '''
DEADLINE = object()
def z(packet):
    t = packet["as_of"]
    if t > DEADLINE: return "HOLD"
def evaluate(packet):
    return "PRIME_READY"
'''
        findings = analyze_source(src, path="revenue/x.py")
        self.assertEqual(findings, sorted(findings))


if __name__ == "__main__":
    unittest.main()
