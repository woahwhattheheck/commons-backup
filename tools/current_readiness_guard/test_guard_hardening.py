from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from .cli import _changed
from .guard import PolicyError, analyze_source, apply_policy, load_policy, scan_paths


class GuardTests(unittest.TestCase):
    def rules(self, source: str):
        return [finding.rule for finding in analyze_source(source, path="revenue/x.py")]

    def test_caller_clock_vs_deadline_is_flagged(self):
        source = '''
DEADLINE = "2026-09-21T21:30:00Z"
def evaluate(packet):
    current = parse(packet["as_of"])
    if current > DEADLINE:
        return {"state": "HOLD"}
    return {"state": "PRIME_READY"}
'''
        rules = self.rules(source)
        self.assertIn("CRG001", rules)
        self.assertIn("CRG003", rules)

    def test_arbitrary_caller_time_key_is_tainted(self):
        source = '''
DEADLINE = object()
def run(packet):
    current = parse(packet["when"])
    if current < DEADLINE:
        return "CURRENT_VERIFIED"
    return "HOLD"
'''
        rules = self.rules(source)
        self.assertIn("CRG001", rules)
        self.assertIn("CRG003", rules)

    def test_nested_alias_does_not_evade_taint(self):
        source = '''
CLOSE_AT = object()
def qualify(packet, authority_root):
    stamp = packet.get("as_of")
    parsed = normalize(stamp)
    current = parsed
    if current >= CLOSE_AT:
        return "HOLD"
    if authority_root:
        return "TEAMING_READY"
    return "HOLD"
'''
        self.assertIn("CRG001", self.rules(source))

    def test_cross_helper_time_taint_reaches_public_wrapper(self):
        source = '''
DEADLINE = object()
def _project(packet):
    current = parse(packet["as_of"])
    if current > DEADLINE:
        return "HOLD"
    return "PRIME_READY"
def evaluate(packet):
    return _project(packet)
'''
        rules = self.rules(source)
        self.assertIn("CRG001", rules)
        self.assertIn("CRG003", rules)

    def test_public_current_positive_time_override_is_flagged(self):
        source = '''
def qualify(packet, authority_root, trusted_as_of):
    if trusted_as_of and authority_root:
        return "TEAMING_READY"
    return "HOLD"
'''
        self.assertIn("CRG002", self.rules(source))

    def test_single_packet_ready_is_flagged(self):
        source = '''
def evaluate(packet):
    if packet.get("verified"):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertEqual(self.rules(source), ["CRG003"])

    def test_function_name_does_not_hide_positive_surface(self):
        source = '''
def run(packet):
    return "PRIME_READY"
'''
        self.assertIn("CRG003", self.rules(source))

    def test_global_positive_constant_is_resolved(self):
        source = '''
POSITIVE = "PRIME_READY"
def evaluate(packet):
    return POSITIVE
'''
        self.assertIn("CRG003", self.rules(source))

    def test_enum_attribute_positive_is_resolved(self):
        source = '''
def evaluate(packet):
    return State.CURRENT_VERIFIED
'''
        self.assertIn("CRG003", self.rules(source))

    def test_independent_authority_must_actually_control_positive_path(self):
        source = '''
def evaluate(packet, authority_root):
    return "PRIME_READY"
'''
        self.assertIn("CRG003", self.rules(source))

    def test_authority_in_dead_branch_does_not_control_positive_path(self):
        source = '''
def evaluate(packet, authority_root):
    if False and authority_root:
        return "HOLD"
    return "PRIME_READY"
'''
        self.assertIn("CRG003", self.rules(source))

    def test_authority_guard_controls_positive_path(self):
        source = '''
def evaluate(packet, authority_root):
    if authority_root and packet.get("verified"):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_early_authority_rejection_controls_positive_path(self):
        source = '''
def evaluate(packet, authority_root):
    if not authority_root:
        return "HOLD"
    return "PRIME_READY"
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_authority_validator_controls_positive_path(self):
        source = '''
def evaluate(packet, authority_root):
    if validate_authority(authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_safe_private_helper_authority_maps_to_public_wrapper(self):
        source = '''
def _project(packet, authority_root):
    if authority_root:
        return "PRIME_READY"
    return "HOLD"
def evaluate(packet, authority_root):
    return _project(packet, authority_root)
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_candidate_cannot_be_passed_as_helper_authority(self):
        source = '''
def _project(packet, authority_root):
    if authority_root:
        return "PRIME_READY"
    return "HOLD"
def evaluate(packet):
    return _project(packet, packet)
'''
        self.assertIn("CRG003", self.rules(source))

    def test_public_wrapper_private_unsafe_helper_is_flagged(self):
        source = '''
def _project(packet):
    return "PRIME_READY"
def evaluate(packet):
    return _project(packet)
'''
        self.assertIn("CRG003", self.rules(source))

    def test_process_owned_clock_is_not_caller_clock(self):
        source = '''
from datetime import datetime, timezone
DEADLINE = object()
def evaluate(packet, authority_root):
    current = datetime.now(timezone.utc)
    if current > DEADLINE:
        return "HOLD"
    if authority_root:
        return "PRIME_READY"
    return "HOLD"
'''
        rules = self.rules(source)
        self.assertNotIn("CRG001", rules)
        self.assertNotIn("CRG002", rules)
        self.assertNotIn("CRG003", rules)

    def test_retained_time_current_verifier_is_flagged(self):
        source = '''
def verify_report(packet, report):
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
'''
        self.assertIn("CRG004", self.rules(source))

    def test_decoy_process_clock_does_not_suppress_retained_replay(self):
        source = '''
from datetime import datetime, timezone
def verify_report(packet, report):
    decoy = datetime.now(timezone.utc)
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
'''
        self.assertIn("CRG004", self.rules(source))

    def test_caller_owned_timer_now_is_not_process_clock(self):
        source = '''
def verify_report(packet, report, timer):
    current = timer.now()
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
'''
        self.assertIn("CRG004", self.rules(source))

    def test_trusted_looking_caller_clock_method_is_not_process_clock(self):
        source = """
def verify_report(packet, report, timer):
    current = timer.current_utc()
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
"""
        self.assertIn("CRG004", self.rules(source))

    def test_parameter_named_datetime_cannot_mint_process_clock(self):
        source = """
def verify_report(packet, report, datetime):
    current = datetime.now()
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt["state"] == "READY"
"""
        self.assertIn("CRG004", self.rules(source))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_revenue_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "revenue").mkdir()
            safe = root / "safe.py"
            safe.write_text('def evaluate(packet):\n return "HOLD"\n', encoding="utf-8")
            link = root / "revenue" / "escape.py"
            try:
                os.symlink(safe, link)
            except OSError:
                self.skipTest("symlink unavailable")
            findings = scan_paths(["revenue/escape.py"], root=root)
            self.assertEqual([finding.rule for finding in findings], ["CRG000"])

    def test_verifier_process_projection_used_in_result_is_safe(self):
        source = '''
def verify_report(packet, report):
    current = _process_now()
    retained = compile_state(packet, as_of=report["evaluated_at"])
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh["state"] == report["state"]
'''
        self.assertNotIn("CRG004", self.rules(source))

    def test_private_replay_helper_reaches_public_verifier(self):
        source = '''
def _check(packet, report):
    rebuilt = compile_state(packet, as_of=report["evaluated_at"])
    return rebuilt == report
def verify_report(packet, report):
    return _check(packet, report)
'''
        self.assertIn("CRG004", self.rules(source))

    def test_historical_hold_surface_is_safe(self):
        source = '''
def compile_historical(packet, trusted_as_of):
    projection = project(packet, trusted_as_of)
    projection["state"] = "HOLD"
    return projection
'''
        self.assertEqual(self.rules(source), [])

    def test_positive_token_mentioned_only_in_validator_is_not_emission(self):
        source = '''
def evaluate(packet, authority_root):
    if packet.get("state") == "PRIME_READY":
        return "HOLD"
    return "HOLD"
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_positive_state_assignment_is_treated_as_emission(self):
        source = '''
def evaluate(packet):
    status = "PRIME_READY"
    return {"status": status}
'''
        self.assertIn("CRG003", self.rules(source))

    def test_malformed_python_is_finding_not_skip(self):
        findings = analyze_source("def broken(:\n", path="revenue/broken.py")
        self.assertEqual([finding.rule for finding in findings], ["CRG000"])

    def test_inline_comment_cannot_suppress(self):
        source = '''
def evaluate(packet):  # readiness-guard: ignore CRG003
    return "PRIME_READY"
'''
        self.assertEqual(self.rules(source), ["CRG003"])

    def test_active_central_exemption_is_exact_path_and_rule(self):
        raw = json.dumps({
            "schema": "commons-current-readiness-guard-policy/v1",
            "exemptions": [{
                "path": "revenue/x.py",
                "rule": "CRG003",
                "rationale": "legacy migration tracked until authority adapter lands",
                "owner": "Z-Owner",
                "issue": "#123",
                "expires": "2026-10-01",
            }],
        })
        exemptions = load_policy(raw, today=date(2026, 9, 14))
        findings = analyze_source('def evaluate(packet):\n return "PRIME_READY"\n', path="revenue/x.py")
        self.assertEqual(apply_policy(findings, exemptions), [])
        other = analyze_source('def evaluate(packet):\n return "PRIME_READY"\n', path="revenue/y.py")
        self.assertEqual([finding.rule for finding in apply_policy(other, exemptions)], ["CRG003"])

    def test_expired_exemption_fails_closed(self):
        raw = json.dumps({
            "schema": "commons-current-readiness-guard-policy/v1",
            "exemptions": [{
                "path": "revenue/x.py",
                "rule": "CRG003",
                "rationale": "temporary exception",
                "owner": "Z-Owner",
                "issue": "#123",
                "expires": "2026-09-13",
            }],
        })
        with self.assertRaisesRegex(PolicyError, "expired"):
            load_policy(raw, today=date(2026, 9, 14))

    def test_duplicate_policy_key_fails_closed(self):
        raw = '{"schema":"commons-current-readiness-guard-policy/v1","schema":"x","exemptions":[]}'
        with self.assertRaisesRegex(PolicyError, "duplicate JSON key"):
            load_policy(raw, today=date(2026, 9, 14))

    def test_scan_paths_never_imports_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "revenue" / "danger.py"
            path.parent.mkdir(parents=True)
            path.write_text('raise RuntimeError("must not execute")\ndef evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8")
            findings = scan_paths(["revenue/danger.py"], root=root)
            self.assertEqual([finding.rule for finding in findings], ["CRG003"])

    def test_non_revenue_python_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "misc.py"
            path.write_text('def evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8")
            self.assertEqual(scan_paths(["misc.py"], root=root), [])

    def test_scan_path_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            findings = scan_paths(["../escape.py"], root=directory)
            self.assertEqual([finding.rule for finding in findings], ["CRG000"])

    def test_changed_file_merge_base_selects_only_changed_revenue_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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

    def test_results_are_deterministically_sorted(self):
        source = '''
DEADLINE = object()
def z(packet):
    current = packet["as_of"]
    if current > DEADLINE:
        return "HOLD"
def evaluate(packet):
    return "PRIME_READY"
'''
        findings = analyze_source(source, path="revenue/x.py")
        self.assertEqual(findings, sorted(findings))


if __name__ == "__main__":
    unittest.main()
