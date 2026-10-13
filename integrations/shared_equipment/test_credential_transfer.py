"""Real encryption/transport contracts; dedicated CI installs the optional crypto dependency."""
import base64
import ctypes
import io
import json
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from integrations.shared_equipment import credential_transfer as ct
from integrations.shared_equipment.credential_client import CredentialRequest, retrieve_http
from integrations.shared_equipment.services import CombinedCatalog, ServiceEquipment, build_capability_manifest
from integrations.shared_equipment.slack_carrier import SlackEquipmentCarrier
from integrations.gemini_slack.peer_tool_gateway import EventStore, ToolCallStore, ToolGateway, ToolLoop

SENTINEL = "synthetic unpatterned value / snowman \u2603 / deliberately no token prefix"


class EmptyCatalog:
    def tools(self, **kwargs):
        return []


class CredentialTransferTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sources = ct.CredentialSources(
            config_path=self.root / "sources.json", claude_path=self.root / "claude.json",
            slack_reader=lambda: {"bot_token": SENTINEL, "app_token": "synthetic-app"}, box_paths=())
        self.equipment = ServiceEquipment(credential_sources=self.sources)

    def test_roundtrip_generic_sender_newcomer_and_no_cleartext_outputs(self):
        first, second = CredentialRequest("remote/example"), CredentialRequest("remote/example")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            sealed = ct.seal_credential(first.arguments(), {"token": SENTINEL})
            self.assertEqual(first.open(sealed), {"token": SENTINEL})
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(SENTINEL, json.dumps(sealed))
        self.assertNotIn(SENTINEL, first.slack_request())
        self.assertNotIn("private", first.slack_request())
        self.assertNotIn("private", repr(first))
        with self.assertRaisesRegex(ct.CredentialTransferError, "credential_delivery_invalid"):
            second.open(sealed)

    def test_tampering_wrong_key_and_every_context_field_fail(self):
        pending = CredentialRequest("slack/bot")
        sealed = self.sources.retrieve_sealed(pending.arguments())
        for field in ct.HEADER_FIELDS + ("ciphertext",):
            bad = dict(sealed)
            bad[field] = ("0" if bad[field][0] != "0" else "1") + bad[field][1:]
            with self.subTest(field=field), self.assertRaises(ct.CredentialTransferError):
                pending.open(bad)
        for field in ct.CONTEXT_FIELDS:
            expected = pending.arguments()
            expected[field] = "0" * 64 if field == "recipient_public_key" else "different"
            with self.subTest(expected=field), self.assertRaises(ct.CredentialTransferError):
                ct.open_credential(sealed, pending._private_key, expected)

    def test_http_wrapper_ids_must_match_retained_request(self):
        pending = CredentialRequest("slack/bot")
        result = self.equipment.call("credential_retrieve_sealed", pending.arguments())
        for field in ("request_id", "call_id"):
            wrapped = {"ok": True, "request_id": pending.arguments()["request_id"],
                       "call_id": pending.arguments()["call_id"], "result": result}
            wrapped[field] = "different"
            with self.assertRaises(ct.CredentialTransferError):
                pending.open(wrapped)

    def test_replay_same_ciphertext_no_reread_and_rotation_new_ids(self):
        effects = []
        self.sources.slack_reader = lambda: effects.append(1) or {"bot_token": SENTINEL + str(len(effects))}
        pending = CredentialRequest("slack/bot")
        calls = ToolCallStore(self.root / "calls.db")
        self.addCleanup(calls.close)
        args = pending.arguments()
        def run(a):
            return calls.execute_journaled("equipment:r", "c", "credential_retrieve_sealed", a, self.equipment.call)
        first, second = run(args), run(args)
        self.assertEqual(first, second)
        self.assertEqual(len(effects), 1)
        self.assertEqual(pending.open(first), SENTINEL + "1")
        changed = CredentialRequest("slack/bot").arguments()
        self.assertEqual(run(changed)["error"], "call_id_reused_with_different_arguments")
        fresh = CredentialRequest("slack/bot")
        third = calls.execute_journaled("equipment:new", "c", "credential_retrieve_sealed", fresh.arguments(), self.equipment.call)
        self.assertEqual(fresh.open(third), SENTINEL + "2")
        self.assertNotIn(SENTINEL.encode(), (self.root / "calls.db").read_bytes())

    def test_secret_bearing_loader_and_timeout_errors_never_reach_journal(self):
        calls = ToolCallStore(self.root / "calls.db")
        self.addCleanup(calls.close)
        failures = [RuntimeError(SENTINEL), subprocess.TimeoutExpired([SENTINEL], 1, output=SENTINEL, stderr=SENTINEL)]
        for index, failure in enumerate(failures):
            def bad():
                raise failure
            self.sources.slack_reader = bad
            pending = CredentialRequest("slack/bot")
            result = calls.execute_journaled(str(index), "c", "credential_retrieve_sealed", pending.arguments(), self.equipment.call)
            self.assertTrue(result["isError"])
            self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL.encode(), (self.root / "calls.db").read_bytes())

    def test_missing_crypto_or_invalid_key_does_not_read_custody(self):
        pending = CredentialRequest("slack/bot")
        with patch.object(self.sources, "read", side_effect=AssertionError("must not read")):
            with patch.object(ct, "crypto", side_effect=ct.CredentialTransferError(ct.CRYPTO_HELP)):
                result = self.equipment.call("credential_retrieve_sealed", pending.arguments())
                self.assertIn("credential_crypto_unavailable", result["message"])
                refs = self.equipment.call("credential_references", {})
                self.assertFalse(refs["isError"])
                self.assertIn("slack_read_channel", {t["name"] for t in self.equipment.tools()})
            for key in ("", "not hex", "00" * 32):
                args = pending.arguments()
                args["recipient_public_key"] = key
                self.assertTrue(self.equipment.call("credential_retrieve_sealed", args)["isError"])

    def test_local_read_needs_no_crypto_or_gateway(self):
        with patch.object(ct, "crypto", side_effect=AssertionError("no dependency")):
            self.assertEqual(self.sources.read("slack/bot"), SENTINEL)

    def test_gh_existing_store_capture_no_shell_no_window_and_generic_failure(self):
        seen = []
        def runner(command, **kwargs):
            seen.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, SENTINEL + "\n", "")
        self.sources.gh_runner = runner
        self.assertEqual(self.sources.read("github/token"), SENTINEL)
        command, kwargs = seen[0]
        self.assertEqual(command, ["gh", "auth", "token", "--hostname", "github.com"])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertNotIn("shell", kwargs)
        def failing(*args, **kwargs):
            raise subprocess.TimeoutExpired([SENTINEL], 1, output=SENTINEL)
        self.sources.gh_runner = failing
        with self.assertRaises(ct.CredentialTransferError) as caught:
            self.sources.read("github/token")
        self.assertNotIn(SENTINEL, str(caught.exception))

    def test_configured_sources_and_runtime_registration_expand_catalog(self):
        source = self.root / "existing.json"
        source.write_text(json.dumps({"nested": {"field/with/slash": SENTINEL}}), encoding="utf-8")
        self.sources.config_path.write_text(json.dumps({"sources": {"future/provider": {
            "type": "json_file", "path": str(source), "pointer": "/nested/field~1with~1slash"}}}), encoding="utf-8")
        self.sources.register("runtime/remote", lambda: SENTINEL)
        refs = self.sources.describe()
        self.assertNotIn(SENTINEL, json.dumps(refs))
        names = {row["credential_ref"] for row in refs["references"]}
        self.assertTrue({"future/provider", "runtime/remote"}.issubset(names))
        for ref in ("future/provider", "runtime/remote"):
            pending = CredentialRequest(ref)
            self.assertEqual(pending.open(self.sources.retrieve_sealed(pending.arguments())), SENTINEL)

    def test_windows_binary_roundtrip_and_legacy_text_reader(self):
        class Credential(ctypes.Structure):
            _fields_ = [("CredentialBlobSize", ctypes.c_uint32),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte))]
        payloads = {
            "binary": b"\x00\xff\x80A\x00B\x00",
            "text": b'{"token":"synthetic-text"}\x00\x00',
        }
        retained, freed = [], []
        def read(target, kind, flags, out):
            raw = payloads[target]
            buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
            record = Credential(len(raw), buffer)
            retained.append((buffer, record))
            ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(
                ctypes.pointer(record), ctypes.c_void_p)
            return True
        module = SimpleNamespace(CREDENTIAL=Credential, advapi32=SimpleNamespace(
            CredReadW=read, CredFree=lambda pointer: freed.append(pointer.value)))
        self.sources.config_path.write_text(json.dumps({"sources": {
            "windows/binary": {"type": "windows_credential", "target": "binary", "encoding": "base64"},
            "windows/text": {"type": "windows_credential", "target": "text", "format": "json", "pointer": "/token"},
        }}), encoding="utf-8")
        with patch.object(ct.CredentialSources, "_gemini_module", return_value=module):
            encoded = self.sources.read("windows/binary")
            self.assertEqual(base64.b64decode(encoded, validate=True), payloads["binary"])
            pending = CredentialRequest("windows/binary")
            sealed = self.sources.retrieve_sealed(pending.arguments())
            self.assertEqual(base64.b64decode(pending.open(sealed), validate=True), payloads["binary"])
            self.assertNotIn(encoded, json.dumps(sealed))
            self.assertEqual(self.sources.read("windows/text"), "synthetic-text")
        self.assertEqual(len(freed), 3)

    def test_claude_index_reports_empty_without_inventing_stripe_and_reads_populated(self):
        self.sources.claude_path.write_text(json.dumps({"mcpOAuth": {
            "plugin:example|entry": {"accessToken": SENTINEL, "refreshToken": ""},
            "plugin:small-business:stripe|example": {"accessToken": "", "refreshToken": ""}}}), encoding="utf-8")
        described = self.sources.describe()
        self.assertNotIn(SENTINEL, json.dumps(described))
        rows = {row["credential_ref"]: row for row in described["references"]}
        self.assertEqual(rows["claude/mcp/plugin%3Aexample%7Centry/access"]["availability"], "present")
        self.assertEqual(rows["claude/mcp/plugin%3Asmall-business%3Astripe%7Cexample/access"]["availability"], "empty")
        self.assertEqual(self.sources.read("claude/mcp/plugin%3Aexample%7Centry/access"), SENTINEL)
        with self.assertRaises(ct.CredentialTransferError):
            self.sources.read("claude/mcp/plugin%3Asmall-business%3Astripe%7Cexample/access")

    def test_broken_optional_config_keeps_existing_direct_sources_working(self):
        self.sources.config_path.write_text('{"sources": []}', encoding="utf-8")
        self.assertIn("credential_source_config_unavailable", self.sources.describe()["errors"])
        self.assertEqual(self.sources.read("slack/bot"), SENTINEL)
        self.sources.gh_runner = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, SENTINEL, "")
        self.assertEqual(self.sources.read("github/token"), SENTINEL)

    def test_manifest_keeps_same_newcomer_inventory_without_reading_values(self):
        catalog = CombinedCatalog(EmptyCatalog(), self.equipment)
        first = build_capability_manifest(catalog=catalog, peer="NEW")
        second = build_capability_manifest(catalog=catalog, peer="ESTABLISHED")
        self.assertEqual(first, second)
        self.assertIn("credential_retrieve_sealed", [row["name"] for row in first["operations"]])

    def test_real_http_gateway_returns_actual_value_only_to_client(self):
        catalog = CombinedCatalog(EmptyCatalog(), self.equipment)
        calls = ToolCallStore(self.root / "http.db")
        events = EventStore(self.root / "events.jsonl")
        gateway = ToolGateway(("127.0.0.1", 0), ToolLoop(None, catalog, calls), events, None, catalog)
        worker = threading.Thread(target=gateway.serve_forever, daemon=True)
        worker.start()
        try:
            base = "http://%s:%s" % gateway.server_address
            self.assertEqual(retrieve_http("slack/bot", base_url=base), SENTINEL)
            self.assertNotIn(SENTINEL.encode(), (self.root / "http.db").read_bytes())
            self.assertFalse((self.root / "events.jsonl").exists())
        finally:
            gateway.shutdown()
            gateway.server_close()
            worker.join(2)
            calls.close()

    def test_real_slack_carrier_and_model_loop_keep_only_sealed_results(self):
        pending = CredentialRequest("slack/bot")
        calls = ToolCallStore(self.root / "carrier.db")
        self.addCleanup(calls.close)
        sent = []
        class Delivery:
            def _slack_write_route_verified(self, channel):
                return channel == "C-SYNTHETIC"
            def call(self, name, args):
                sent.append(args["text"])
                return {"result": {"ok": True, "ts": "2.1"}}
        catalog = CombinedCatalog(EmptyCatalog(), self.equipment)
        carrier_catalog = type("CarrierCatalog", (), {"services": Delivery(), "call": catalog.call})()
        carrier = SlackEquipmentCarrier(carrier_catalog, calls, {"channel_id": "C-SYNTHETIC"}, self.root / "cursor.json")
        message = {"ts": "1.1", "text": pending.slack_request()}
        carrier.process(message)
        carrier.process(message)
        self.assertEqual(len(sent), 1)
        body = sent[0].split(">", 1)[1].rsplit("</", 1)[0].strip()
        self.assertEqual(pending.open(json.loads(body)), SENTINEL)
        self.assertNotIn(SENTINEL, sent[0])
        prompts = []
        class Model:
            def turn(self, peer, prompt, *, cancelled=None, on_submitted=None):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return '<commons_tool_call>' + json.dumps({"call_id": "loop", "name": "credential_retrieve_sealed", "arguments": pending.arguments()}) + '</commons_tool_call>'
                return prompt  # worst case: the model repeats its entire tool result
        reply = ToolLoop(Model(), catalog, calls).run("model", "newcomer", "retrieve")
        events = EventStore(self.root / "events.jsonl")
        events.append(status="completed", reply=reply)
        for path in (self.root / "carrier.db", self.root / "events.jsonl"):
            self.assertNotIn(SENTINEL.encode(), path.read_bytes())
        self.assertNotIn(SENTINEL, "".join(prompts))


class BoxCredentialSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.primary = self.root / "box-secrets.json"
        self.alias = self.root / "alias-secrets.json"
        self.sources = ct.CredentialSources(
            config_path=self.root / "sources.json", claude_path=self.root / "claude.json",
            box_paths=(self.primary, self.alias),
            gh_runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "synthetic-legacy", ""))
        self.records = {
            "sample/text": {"encoding": "native_json", "value": SENTINEL},
            "sample/object": {"encoding": "native_json", "value": {"nested": [True, None, 0]}},
            "sample/json-text": {"encoding": "native_json", "value": '{"still":"text"}'},
            "sample/binary": {"encoding": "base64", "value": base64.b64encode(b"\x00\xff\x80binary\x00").decode()},
            "github/token": {"encoding": "native_json", "value": "synthetic-box"},
        }
        self.records.update({"sample/additional-" + str(i): {"encoding": "native_json", "value": "synthetic-" + str(i)}
                             for i in range(61)})

    def write_bundle(self, records=None, path=None):
        records = self.records if records is None else records
        payload = json.dumps({"schema_version": 1, "operation_id": "synthetic-transfer", "sources": records})
        parts = [payload[i:i + 31] for i in range(0, len(payload), 31)]
        names = ["COMMONS_SHARED_VAULT_PART_" + str(i).zfill(3) for i in range(len(parts))]
        mapping = dict(zip(names, parts))
        mapping[ct.BOX_MANIFEST_KEY] = json.dumps({
            "schema_version": 1, "operation_id": "synthetic-transfer",
            "format": "concatenated-json", "parts": names, "source_count": len(records)})
        (path or self.primary).write_text(json.dumps({"version": 1, "secrets": mapping}), encoding="utf-8")
        return mapping

    def test_newcomer_discovers_all_sources_and_actual_sealed_types(self):
        self.write_bundle()
        rows = ct.credential_references(self.sources)
        self.assertFalse(rows["errors"])
        self.assertNotIn(SENTINEL, json.dumps(rows))
        discovered = {row["credential_ref"]: row for row in rows["references"]}
        self.assertTrue(set(self.records).issubset(discovered))
        self.assertEqual(discovered["github/token"]["source_type"], "existing_grokbot_box_bundle")
        for ref, record in self.records.items():
            self.assertEqual(self.sources.read(ref), record["value"])
        for ref in ("sample/text", "sample/object", "sample/json-text", "sample/binary"):
            pending = CredentialRequest(ref)
            sealed = self.sources.retrieve_sealed(pending.arguments())
            actual = pending.open(sealed)
            self.assertEqual(actual, self.records[ref]["value"])
            self.assertIs(type(actual), type(self.records[ref]["value"]))
            self.assertNotIn(SENTINEL, json.dumps(sealed))

    def test_fresh_process_existing_client_discovers_default_store_without_config(self):
        self.write_bundle()
        code = """
import json, sys
from pathlib import Path
from unittest.mock import patch
from integrations.shared_equipment import credential_transfer as ct
from integrations.shared_equipment.credential_client import retrieve_local
with patch.object(Path, "home", return_value=Path(sys.argv[1])), patch.object(ct, "BOX_SECRET_PATHS", (sys.argv[2],)):
    discovered = {row["credential_ref"] for row in ct.credential_references()["references"]}
    expected = {"sample/text", "sample/object", "sample/json-text", "sample/binary", "github/token"}
    expected.update(f"sample/additional-{i}" for i in range(61))
    assert expected.issubset(discovered)
    assert retrieve_local("github/token") == "synthetic-box"
    assert retrieve_local("sample/object") == {"nested": [True, None, 0]}
    assert not (Path.home() / ".commons/credential_sources.json").exists()
    print(json.dumps({"discovered_bundle_sources": len(expected & discovered), "direct_read": True}))
"""
        completed = subprocess.run([__import__("sys").executable, "-c", code, str(self.root), str(self.primary)],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"discovered_bundle_sources": 66, "direct_read": True})
        self.assertNotIn(SENTINEL, completed.stdout + completed.stderr)

    def test_registered_and_configured_sources_keep_precedence(self):
        self.write_bundle()
        local = self.root / "local.json"
        local.write_text(json.dumps({"value": "synthetic-configured"}), encoding="utf-8")
        self.sources.config_path.write_text(json.dumps({"sources": {"github/token": {
            "type": "json_file", "path": str(local), "pointer": "/value"}}}), encoding="utf-8")
        self.assertEqual(self.sources.read("github/token"), "synthetic-configured")
        self.sources.register("github/token", lambda: "synthetic-registered")
        self.assertEqual(self.sources.read("github/token"), "synthetic-registered")
        rows = {row["credential_ref"]: row for row in self.sources.describe()["references"]}
        self.assertEqual(rows["github/token"]["source_type"], "registered_runtime_reader")

    def test_absence_unrelated_store_and_alias_preserve_existing_roads(self):
        self.assertEqual(self.sources.read("github/token"), "synthetic-legacy")
        self.assertFalse(self.sources.describe()["errors"])
        self.primary.write_text(json.dumps({"version": 1, "secrets": {"UNRELATED": SENTINEL}}), encoding="utf-8")
        self.assertEqual(self.sources.read("github/token"), "synthetic-legacy")
        self.assertFalse(self.sources.describe()["errors"])
        self.primary.unlink()
        self.write_bundle(path=self.alias)
        self.assertEqual(self.sources.read("github/token"), "synthetic-box")

    def test_missing_part_corrupt_json_and_bad_types_are_redacted(self):
        variants = []
        mapping = self.write_bundle()
        manifest = json.loads(mapping[ct.BOX_MANIFEST_KEY])
        missing = dict(mapping)
        del missing[manifest["parts"][1]]
        variants.append({"secrets": missing})
        duplicate = dict(mapping)
        manifest["parts"].append(manifest["parts"][0])
        duplicate[ct.BOX_MANIFEST_KEY] = json.dumps(manifest)
        variants.append({"secrets": duplicate})
        nonstring = dict(mapping)
        nonstring[json.loads(mapping[ct.BOX_MANIFEST_KEY])["parts"][0]] = {"secret": SENTINEL}
        variants.append({"secrets": nonstring})
        variants.append({"secrets": {ct.BOX_MANIFEST_KEY: SENTINEL}})
        for stored in variants:
            self.primary.write_text(json.dumps(stored), encoding="utf-8")
            described = self.sources.describe()
            self.assertIn("credential_box_bundle_unavailable", described["errors"])
            self.assertNotIn(SENTINEL, json.dumps(described))
            with self.assertRaises(ct.CredentialTransferError) as caught:
                self.sources.read("sample/text")
            self.assertNotIn(SENTINEL, str(caught.exception))
            self.assertEqual(self.sources.read("github/token"), "synthetic-legacy")
        self.primary.write_text(SENTINEL, encoding="utf-8")
        self.assertIn("credential_box_bundle_unavailable", self.sources.describe()["errors"])
        self.sources.register("sample/text", lambda: "synthetic-local")
        self.assertEqual(self.sources.read("sample/text"), "synthetic-local")

    def test_manifest_count_identity_encoding_and_nonfinite_values_are_checked(self):
        for field, value in (("source_count", 1), ("source_count", True), ("operation_id", "other"),
                             ("schema_version", True), ("parts", ["missing"])):
            mapping = self.write_bundle()
            manifest = json.loads(mapping[ct.BOX_MANIFEST_KEY])
            manifest[field] = value
            mapping[ct.BOX_MANIFEST_KEY] = json.dumps(manifest)
            self.primary.write_text(json.dumps({"secrets": mapping}), encoding="utf-8")
            self.assertIn("credential_box_bundle_unavailable", self.sources.describe()["errors"])
        for record in ({"encoding": "base64", "value": "AP8"},
                       {"encoding": "unknown", "value": SENTINEL},
                       {"encoding": "native_json", "value": float("nan")}):
            self.write_bundle({"sample/invalid": record})
            self.assertIn("credential_box_bundle_unavailable", self.sources.describe()["errors"])

        mapping = self.write_bundle({"sample/overflow": {"encoding": "native_json", "value": "OVERFLOW"}})
        names = json.loads(mapping[ct.BOX_MANIFEST_KEY])["parts"]
        payload = "".join(mapping[name] for name in names).replace('"OVERFLOW"', "1e999")
        mapping[names[0]] = payload
        for name in names[1:]:
            mapping[name] = ""
        self.primary.write_text(json.dumps({"secrets": mapping}), encoding="utf-8")
        self.assertIn("credential_box_bundle_unavailable", self.sources.describe()["errors"])

    def test_snapshot_updates_are_visible_and_empty_values_keep_existing_contract(self):
        self.write_bundle({"sample/value": {"encoding": "native_json", "value": "first"}})
        self.assertEqual(self.sources.read("sample/value"), "first")
        self.write_bundle({"sample/value": {"encoding": "native_json", "value": "second"}})
        self.assertEqual(self.sources.read("sample/value"), "second")
        for value in ("", None, {}):
            self.write_bundle({"sample/empty": {"encoding": "native_json", "value": value}})
            row = next(row for row in self.sources.describe()["references"] if row["credential_ref"] == "sample/empty")
            self.assertEqual(row["availability"], "empty")
            with self.assertRaises(ct.CredentialTransferError):
                self.sources.read("sample/empty")
        for value in (False, 0, [], "false"):
            self.write_bundle({"sample/value": {"encoding": "native_json", "value": value}})
            self.assertEqual(self.sources.read("sample/value"), value)
            self.assertIs(type(self.sources.read("sample/value")), type(value))


if __name__ == "__main__":
    unittest.main()
