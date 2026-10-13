from __future__ import annotations

from ._test_source_bound_support import *


class RuntimeSourceBoundTests(SourceBoundTestCase):
    def test_requirement_order_invariant(self):
        first = facts(commitment=True, all_satisfied=True)
        second = copy.deepcopy(first)
        second["requirements"] = list(reversed(second["requirements"]))
        self.assertEqual(
            s._compile_at(first, self.before_intent()),
            s._compile_at(second, self.before_intent()),
        )

    def test_verify_survives_clock_advance_when_operational_truth_is_unchanged(self):
        payload = facts()
        bound = self.before_intent()
        packet = s._compile_at(payload, bound)
        original = s._now_utc
        s._now_utc = lambda: bound + dt.timedelta(seconds=1)
        try:
            self.assertTrue(s.verify_current(packet, payload))
        finally:
            s._now_utc = original

    def test_verify_stales_packet_when_deadline_crossing_changes_operational_truth(self):
        payload = facts()
        just_before = dt.datetime(2026, 9, 16, 23, 59, 59, tzinfo=dt.timezone.utc)
        packet = s._compile_at(payload, just_before)
        original = s._now_utc
        s._now_utc = lambda: self.at_intent()
        try:
            with self.assertRaisesRegex(s.ContractError, "operational state is stale"):
                s.verify_current(packet, payload)
        finally:
            s._now_utc = original

    def test_cli_compile_then_verify_does_not_self_stale_on_timestamp_only(self):
        payload = facts()
        compile_input = json.dumps({"schema": s.SCHEMA_INPUT, "facts": payload}).encode()
        compiled = subprocess.run(
            [
                sys.executable,
                "-m",
                "revenue.ohsu_erp_rfp_2027_0005.source_bound",
                "compile",
            ],
            input=compile_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT.parents[1],
            check=False,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
        packet = json.loads(compiled.stdout)
        verify_input = json.dumps(
            {"schema": s.SCHEMA_VERIFY_INPUT, "facts": payload, "packet": packet}
        ).encode()
        verified = subprocess.run(
            [
                sys.executable,
                "-m",
                "revenue.ohsu_erp_rfp_2027_0005.source_bound",
                "verify",
            ],
            input=verify_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT.parents[1],
            check=False,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr.decode())
        self.assertTrue(json.loads(verified.stdout)["valid"])

    def test_bool_int_alias_rejected(self):
        payload = facts()
        payload["owner_reviewed"] = 1
        with self.assertRaisesRegex(s.ContractError, "must be bool"):
            s._compile_at(payload, self.before_intent())

    def test_cli_duplicate_key_controlled_refusal(self):
        raw = (
            '{"schema":"%s","schema":"%s","facts":{}}'
            % (s.SCHEMA_INPUT, s.SCHEMA_INPUT)
        ).encode()
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "revenue.ohsu_erp_rfp_2027_0005.source_bound",
                "compile",
            ],
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT.parents[1],
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn(b"duplicate JSON key", proc.stderr)
