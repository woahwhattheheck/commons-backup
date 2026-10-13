from __future__ import annotations

from .test_support import *  # noqa: F401,F403


class InputsTests(GateTestCase):
    def test_bool_is_not_integer_in_policy(self):
        policy = dict(self.fx.policy)
        policy["contact_cooldown_seconds"] = True
        self.fx.write_authority(policy=policy)
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIsNone(receipt["authority_sha256"])


    def test_duplicate_json_key_rejected(self):
        duplicate = (
            b'{"schema":"organization-contact-pressure-request/v1",'
            b'"schema":"organization-contact-pressure-request/v1"}'
        )
        with self.assertRaisesRegex(gate.InputError, "duplicate JSON key"):
            gate._normalize_request(duplicate)


    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(gate.InputError, "non-finite"):
            gate.strict_json_loads(b'{"x":NaN}')


    def test_unknown_request_field_rejected(self):
        request = json.loads(self.fx.request())
        request["recipient_email"] = "private@example.test"
        with self.assertRaisesRegex(gate.InputError, "fields mismatch"):
            self.fx.compile(gate._canonical_bytes(request))


    def test_private_key_permissions_enforced(self):
        key_path = self.root / "keys" / f"{self.fx.key_id}.key"
        key_path.chmod(0o644)
        with self.assertRaises(gate.AuthorityUnavailable):
            self.fx.compile()


    def test_request_symlink_rejected(self):
        target = self.root / "request.json"
        target.write_bytes(self.fx.request())
        link = self.root / "request-link.json"
        link.symlink_to(target)
        with self.assertRaises(gate.InputError):
            gate._read_request_file(link)


    def test_request_parent_symlink_rejected(self):
        real_dir = self.root / "real-input"
        real_dir.mkdir()
        request = real_dir / "request.json"
        request.write_bytes(self.fx.request())
        linked_dir = self.root / "linked-input"
        linked_dir.symlink_to(real_dir, target_is_directory=True)
        with self.assertRaises(gate.InputError):
            gate._read_request_file(linked_dir / "request.json")


    def test_output_parent_symlink_rejected(self):
        real_dir = self.root / "real-output"
        real_dir.mkdir()
        linked_dir = self.root / "linked-output"
        linked_dir.symlink_to(real_dir, target_is_directory=True)
        with self.assertRaises(gate.InputError):
            gate._write_exclusive(linked_dir / "receipt.json", b"nope")
        self.assertFalse((real_dir / "receipt.json").exists())


    def test_retained_root_symlink_rejected(self):
        linked_root = self.root.parent / f"{self.root.name}-link"
        linked_root.symlink_to(self.root, target_is_directory=True)
        try:
            with self.assertRaises(gate.AuthorityUnavailable):
                gate._compile_at(self.fx.request(), root=linked_root, now=self.fx.now)
        finally:
            linked_root.unlink(missing_ok=True)


    def test_create_exclusive_output_refuses_overwrite(self):
        output = self.root / "receipt.json"
        gate._write_exclusive(output, b"first")
        with self.assertRaises(gate.InputError):
            gate._write_exclusive(output, b"second")
        self.assertEqual(b"first", output.read_bytes())


    def test_cli_parser_refuses_caller_clock_key_and_root(self):
        parser = gate._build_parser()
        for forbidden in ("--now", "--key", "--authority-root"):
            with self.assertRaises(SystemExit):
                parser.parse_args(["compile", "request.json", "out.json", forbidden, "attacker"])


    def test_public_compile_owns_root_and_clock(self):
        fixed_now = self.fx.now

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)

        with mock.patch.object(gate, "_authority_root", return_value=self.root), mock.patch.object(
            gate, "datetime", FixedDateTime
        ):
            receipt = gate.compile_current(self.fx.request())
        self.assert_decision(gate.READY, receipt)
        self.assertEqual(ts(self.fx.now), receipt["evaluated_at"])


    def test_normal_and_optimized_process_semantics_match(self):
        script = r'''
import json
from pathlib import Path
from datetime import datetime, timezone
from revenue.organization_contact_pressure import gate
root = Path(__import__("sys").argv[1])
req = Path(__import__("sys").argv[2]).read_bytes()
now = datetime(2026, 9, 14, 2, 55, 0, tzinfo=timezone.utc)
print(gate._canonical_bytes(gate._compile_at(req, root=root, now=now)).decode())
'''
        request_path = self.root / "request.json"
        request_path.write_bytes(self.fx.request())
        env = dict(os.environ)
        project_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = project_root
        normal = subprocess.run(
            [sys.executable, "-c", script, str(self.root), str(request_path)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout
        optimized = subprocess.run(
            [sys.executable, "-O", "-c", script, str(self.root), str(request_path)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout
        self.assertEqual(normal, optimized)
