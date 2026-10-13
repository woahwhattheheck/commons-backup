from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_DIR = ROOT / "integrations" / "commons_publication_hooks"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(ROOT))
import hook

class PublicationHookSlackTests(unittest.TestCase):
    def _event(self, tool, args):
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args}

    def test_connector_and_gateway_exact_mappings_are_allowed(self):
        connector = self._event("mcp__codex_apps__slack_slack_send_message", {
            "channel_id": "C0BRGMDQB6G", "message": "patch handoff", "thread_ts": "1788567066.179399"
        })
        gateway = self._event("mcp__commons_gateway__slack_post_message", {
            "channel_id": "C0BRGMDQB6G", "text": "patch handoff"
        })
        self.assertIsNone(hook.publication_verdict(connector))
        self.assertIsNone(hook.publication_verdict(gateway))
        claude_cloud = self._event("mcp__slack__slack_send_message", {
            "channel_id": "C0BU51F1PL3", "message": "patch handoff", "thread_ts": "1790851459.659859"
        })
        verdict = hook.publication_verdict(claude_cloud)
        self.assertEqual(verdict["code"], "outbound_sender_identity_unverified")

    def test_file_upload_stage_is_private_but_unverified_direct_share_stays_held(self):
        start = self._event("mcp__codex_apps__slack_slack_get_file_upload_url", {
            "filename": "handoff-op-20261001.patch", "content_length": 29, "snippet_type": "diff"
        })
        finish = self._event("mcp__codex_apps__slack_slack_complete_file_upload", {
            "file_id": "F0ABC12345", "channel_id": "C0BRGMDQB6G",
            "initial_comment": "Work handoff op-20261001", "title": "handoff-op-20261001.patch"
        })
        self.assertIsNone(hook.publication_verdict(start))
        verdict = hook.publication_verdict(finish)
        self.assertEqual(verdict["code"], "outbound_sender_identity_unverified")

    def test_unknown_fields_overrides_and_unregistered_writes_keep_current_hold(self):
        base = {"channel_id": "C0BRGMDQB6G", "message": "handoff"}
        for args in (
            {**base, "username": "other"},
            {**base, "unexpected": "field"},
            {"channel_id": 4, "message": "handoff"},
        ):
            verdict = hook.publication_verdict(self._event("mcp__codex_apps__slack_slack_send_message", args))
            self.assertEqual(verdict["code"], "outbound_sender_identity_unverified")
        custom = hook.publication_verdict(self._event("mcp__codex_apps__slack_slack_schedule_message", {
            **base, "post_at": "1788568000"
        }))
        self.assertEqual(custom["code"], "outbound_sender_identity_unverified")
        wrong_namespace = hook.publication_verdict(self._event("untrusted__slack_slack_send_message", base))
        self.assertEqual(wrong_namespace["code"], "outbound_sender_identity_unverified")

    def test_read_route_remains_allowed(self):
        self.assertIsNone(hook.publication_verdict(self._event("mcp__codex_apps__slack_slack_read_channel", {
            "channel_id": "C0BRGMDQB6G", "limit": 1
        })))

    def test_installer_copies_mapping_and_preserves_existing_hooks(self):
        spec = importlib.util.spec_from_file_location("commons_install", ROOT / "integrations" / "commons_publication_hooks" / "install.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            config_dir = Path(temp)
            existing = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "keep-me"}]}]}}
            (config_dir / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")
            result = module.install(config_dir)
            destination = Path(result["hook"]).parent
            self.assertTrue((destination / "slack_route_mapping.py").is_file())
            config = json.loads((config_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [h["command"] for group in config["hooks"]["PreToolUse"] for h in group["hooks"]]
            self.assertIn("keep-me", commands)
            self.assertTrue(any("commons-publication-hooks" in command for command in commands))

if __name__ == "__main__":
    unittest.main(verbosity=2)
