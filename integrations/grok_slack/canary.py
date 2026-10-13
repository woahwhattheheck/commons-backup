#!/usr/bin/env python3
"""Offline end-to-end canary for the grok.com Slack connector host pack.

No Slack Socket Mode, no grok.com spend, no live tokens. Values are never printed.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import test_grok_slack_bridge as harness
from integrations.grokcom_revenue.orchestrator import orchestrate

bridge = harness.bridge

EXACT_TEXT = "  keep leading\n\ttabs and ☃ and trailing  "
TOKEN_LOOKALIKE = "xoxb" + "-canary-scan-not-a-real-token"


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blob_parts: list[str] = []

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        args = type("Args", (), {
            "state_db": root / "state.sqlite3",
            "mcp_url": "https://commons-spark-mcp.vercel.app/mcp",
            "health_bind": "127.0.0.1:0",
            "probe": "",
        })()

        github = harness.FakeGitHub()
        github.put("carriers/catalog.json", {"carriers": []})
        mcp = harness.FakeMcp(github)
        code, doctor_report = bridge.doctor(args, env={}, mcp=mcp, github=github, root=bridge.integration_root())
        encoded_doctor = json.dumps(doctor_report)
        blob_parts.append(encoded_doctor)
        checks.append(_check(
            "doctor_unconfigured",
            code == 2 and doctor_report["state"] == "RUNTIME_UNCONFIGURED" and not doctor_report["ready"],
            doctor_report["state"],
        ))
        checks.append(_check(
            "doctor_omits_secret_values",
            "xoxb" not in encoded_doctor.casefold() and "xapp" not in encoded_doctor.casefold(),
        ))
        checks.append(_check(
            "one_delivery_owner_in_doctor",
            doctor_report.get("final_delivery_owner") == bridge.FINAL_DELIVERY_OWNER,
        ))

        bot_value = "xoxb" + "-injected-not-printed"
        app_value = "xapp" + "-injected-not-printed"
        env_file = root / ".env.local"
        env_file.write_text(
            "SLACK_BOT_TOKEN=" + bot_value + "\n"
            "SLACK_APP_TOKEN=" + app_value + "\n"
            "EXISTING=keep\n",
            encoding="utf-8",
        )
        env_map = {"EXISTING": "keep"}
        loaded = bridge.load_runtime_env(env_map, files=[env_file])
        checks.append(_check(
            "secret_injection_setdefault",
            env_map.get("SLACK_BOT_TOKEN") == bot_value and env_map.get("EXISTING") == "keep",
            ",".join(loaded["keys_set"]),
        ))
        loaded_blob = json.dumps(loaded)
        checks.append(_check(
            "secret_injection_omits_values",
            bot_value not in loaded_blob and app_value not in loaded_blob,
        ))
        process_wins = {"SLACK_BOT_TOKEN": "already"}
        bridge.load_runtime_env(process_wins, files=[env_file])
        checks.append(_check("process_env_wins", process_wins["SLACK_BOT_TOKEN"] == "already"))

        leak_root = root / "pack"
        leak_root.mkdir()
        (leak_root / "README.md").write_text("token " + TOKEN_LOOKALIKE + "\n", encoding="utf-8")
        scan = bridge.scan_secrets_in_config(leak_root)
        checks.append(_check(
            "secret_scan_detects_prefix",
            scan["secrets_in_config"] is True and "README.md" in scan["files"],
        ))
        scan_clean = bridge.scan_secrets_in_config(bridge.integration_root())
        checks.append(_check(
            "committed_host_pack_has_no_tokens",
            scan_clean["secrets_in_config"] is False,
            ",".join(scan_clean["files"]),
        ))

        pack = bridge.host_pack_presence()
        checks.append(_check("host_pack_complete", all(pack.values()), json.dumps(pack, sort_keys=True)))
        handoff_root = bridge.integration_root()
        checks.append(_check("handoff_py_present", (handoff_root / "handoff.py").is_file()))
        checks.append(_check("handoff_ps1_present", (handoff_root / "run-handoff.ps1").is_file()))
        from integrations.grok_slack import handoff as grok_handoff
        checks.append(_check("slack_app_id_pinned", grok_handoff.SLACK_APP_ID == "A0BTJMFPTT6"))
        checks.append(_check(
            "grok_handoff_not_gemini_port",
            grok_handoff.DEFAULT_HANDOFF_BIND == "127.0.0.1:8789" and grok_handoff.GEMINI_HANDOFF_BIND == "127.0.0.1:8780",
        ))
        gemini_refused = False
        try:
            grok_handoff.parse_loopback_bind("127.0.0.1:8780")
        except grok_handoff.VaultError:
            gemini_refused = True
        checks.append(_check("refuses_gemini_port_8780", gemini_refused))
        with tempfile.TemporaryDirectory() as vault_dir:
            vault_path = Path(vault_dir) / "grok_slack.vault"
            protector = grok_handoff.PosixUserProtector(material=b"canary-user")
            bot_value = "xoxb" + "-injected-not-printed"
            app_value = "xapp" + "-injected-not-printed"
            grok_handoff.write_vault(vault_path, bot_value, app_value, protector=protector)
            raw_vault = vault_path.read_bytes()
            checks.append(_check(
                "vault_is_not_plaintext",
                bot_value.encode() not in raw_vault and app_value.encode() not in raw_vault,
            ))
            reloaded = grok_handoff.read_vault(vault_path, protector=protector)
            checks.append(_check("vault_survives_reread", reloaded["slack_app_id"] == "A0BTJMFPTT6"))
            status = grok_handoff.redacted_status(env={}, vault_path=vault_path, protector=protector, live=False)
            status_blob = json.dumps(status)
            checks.append(_check(
                "handoff_status_omits_values",
                bot_value not in status_blob and app_value not in status_blob and status["live"] is False,
            ))
            blob_parts.append(status_blob)

        handoff_src = (handoff_root / "handoff.py").read_text(encoding="utf-8")
        checks.append(_check(
            "dpapi_from_buffer_copy",
            "from_buffer_copy" in handoff_src and "WinDLL" in handoff_src,
        ))
        checks.append(_check(
            "dpapi_not_cstring_buffer",
            "create_string_buffer(blob" not in handoff_src
            and "create_string_buffer(plaintext" not in handoff_src,
        ))
        checks.append(_check(
            "write_vault_verifies_tmp_before_replace",
            "read_vault(tmp, protector=worker)" in handoff_src
            and "Existing ciphertext at `path` is left untouched" in handoff_src,
        ))
        bridge_src = (handoff_root / "bridge.py").read_text(encoding="utf-8")
        checks.append(_check(
            "table_proof_command",
            "table-proof" in bridge_src and "TABLE_PROOF_CITE" in bridge_src,
        ))
        with tempfile.TemporaryDirectory() as keep_dir:
            keep_path = Path(keep_dir) / "grok_slack.vault"
            existing = grok_handoff.MAGIC + grok_handoff.KIND_WIN + b"\x01\x00keep-me\x00blob"
            keep_path.write_bytes(existing)

            class BoomProtector(grok_handoff.Protector):
                name = "boom"

                def protect(self, plaintext: bytes) -> bytes:
                    del plaintext
                    return b"\x00new-ciphertext"

                def unprotect(self, blob: bytes) -> bytes:
                    del blob
                    raise grok_handoff.VaultError("vault unreadable")

            boom_failed = False
            try:
                grok_handoff.write_vault(
                    keep_path,
                    "xoxb" + "-injected-not-printed",
                    "xapp" + "-injected-not-printed",
                    protector=BoomProtector(),
                )
            except grok_handoff.VaultError:
                boom_failed = True
            checks.append(_check(
                "failed_write_preserves_existing_vault",
                boom_failed and keep_path.read_bytes() == existing,
            ))

        health_code, health_report = bridge.health(args, env={}, root=bridge.integration_root())
        encoded_health = json.dumps(health_report)
        blob_parts.append(encoded_health)
        checks.append(_check(
            "health_unconfigured",
            health_code == 2 and health_report["state"] == "RUNTIME_UNCONFIGURED",
            health_report["state"],
        ))
        checks.append(_check(
            "health_omits_secret_values",
            TOKEN_LOOKALIKE not in encoded_health and bot_value not in encoded_health,
        ))
        checks.append(_check("github_token_optional", health_report.get("github_token_required") is False))

        snapshot = {
            "live": True,
            "state": "SERVING",
            "final_delivery_owner": bridge.FINAL_DELIVERY_OWNER,
            "slack_bot_token": "present",
        }
        server = bridge.HealthServer("127.0.0.1:0", lambda: snapshot)
        server.start()
        try:
            probed = bridge.probe_health_url(server.url)
            checks.append(_check("health_http_live", probed.get("live") is True and probed.get("state") == "SERVING"))
            checks.append(_check(
                "health_http_omits_token_prefixes",
                not bridge.TOKEN_VALUE_RE.search(json.dumps(probed)),
            ))
        finally:
            server.stop()

        service, slack, github, mcp, store = harness.build_bridge(directory)
        result = service.handle_event("Ev-canary-text", harness.event_payload(EXACT_TEXT))
        intake = [call for call in mcp.calls if call[0] == "route_grokcom_revenue_work"]
        packet = orchestrate({"stage": "INTAKE", "mode": "AUTO", "event": {
            "event_id": "Ev-canary-text",
            "channel": "C0BRGMDQB6G",
            "message_ts": "1787871538.126989",
            "thread_ts": "1787871538.126989",
            "author": "UBRYCE",
            "text": EXACT_TEXT,
        }, "grokcom_capacity": harness.CAPACITY})
        checks.append(_check(
            "exact_event_text_to_intake",
            bool(intake) and intake[0][1]["event"]["text"] == EXACT_TEXT,
        ))
        checks.append(_check(
            "exact_event_text_through_orchestrator",
            EXACT_TEXT in str(packet.get("grokcom", {}).get("prompt") or ""),
        ))
        fires = [call for call in mcp.calls if call[0] == "fire_action"]
        checks.append(_check("one_fire_action", len(fires) == 1, str(len(fires))))
        checks.append(_check(
            "one_final_delivery_owner",
            result.get("delivery_owner") == bridge.FINAL_DELIVERY_OWNER,
        ))
        store.close()

        stale_github = harness.FakeGitHub()
        stale_github.put("carriers/catalog.json", {"carriers": []})
        stale_mcp = harness.StaleMcp(stale_github)
        stale_dir = Path(directory) / "stale"
        stale_dir.mkdir()
        stale_service, _stale_slack, _stale_gh, stale_mcp, stale_store = harness.build_bridge(
            str(stale_dir), github=stale_github, mcp=stale_mcp
        )
        stale_result = stale_service.handle_event(
            "Ev-canary-stale",
            harness.event_payload(EXACT_TEXT, ts="1787871538.226989"),
        )
        stale_intake = [
            call for call in stale_mcp.calls
            if call[0] == "route_grokcom_revenue_work" and call[1].get("stage") == "INTAKE"
        ]
        stale_fires = [call for call in stale_mcp.calls if call[0] == "fire_action"]
        checks.append(_check(
            "stale_mcp_intake_uses_orchestrator",
            stale_service.intake_road == "current_main_orchestrator" and stale_result.get("state") == "DELIVERED",
            "%s:%s" % (stale_service.intake_road, stale_result.get("state")),
        ))
        checks.append(_check(
            "stale_mcp_preserves_exact_text",
            bool(stale_intake) and stale_intake[0][1]["event"]["text"] == EXACT_TEXT,
        ))
        checks.append(_check("stale_mcp_one_fire_action", len(stale_fires) == 1, str(len(stale_fires))))
        stale_store.close()

        def _rate_limited(_request: Any, timeout: float | None = None) -> Any:
            del timeout
            raise bridge.BridgeError("github HTTP 403")

        limited = bridge.GitHubReadback(
            opener=_rate_limited,
            token="",
            public_sha=lambda: "b" * 40,
            public_read=lambda path, sha: b'{"carriers":[]}',
        )
        limited_sha = limited.current_main_sha()
        limited_blob = limited.read_path("carriers/catalog.json", limited_sha)
        checks.append(_check(
            "github_readback_without_token",
            limited_sha == "b" * 40 and limited_blob == b'{"carriers":[]}' and limited.road == "sha_pinned_raw",
            limited.road,
        ))

        crash_dir = Path(directory) / "crash"
        crash_dir.mkdir()
        github = harness.FakeGitHub()
        github.put("carriers/catalog.json", {"carriers": []})
        mcp = harness.FakeMcp(github)
        store = harness.CrashSubmitStore(crash_dir / "state.sqlite3")
        sink = bridge.SlackTransport(harness.FakeSlack(), store, sleeper=lambda _s: None)
        service = bridge.GrokSlackBridge(store, mcp, github, sink, bot_user_id="UBOT", poll_budget=2, sleeper=lambda _s: None, grokcom_capacity=harness.CAPACITY)
        crashed = False
        try:
            service.handle_event("Ev-canary-crash", harness.event_payload("persist crash"))
        except RuntimeError:
            crashed = True
        checks.append(_check("crash_after_fire_before_persist", crashed and store.get("Ev-canary-crash").fire_action_calls == 1))
        store.close()
        service2, _slack, github, mcp2, store2 = harness.build_bridge(str(crash_dir), github=github, mcp=harness.FakeMcp(github))
        recovered = service2.recover_pending()
        fires = [name for name, _ in mcp2.calls if name == "fire_action"]
        checks.append(_check(
            "restart_does_not_resubmit",
            recovered >= 1 and fires == [],
            f"recovered={recovered} fires={len(fires)}",
        ))
        store2.close()

        durable_dir = Path(directory) / "durable"
        durable_dir.mkdir()
        db = durable_dir / "state.sqlite3"
        first, _slack, _github, mcp, store = harness.build_bridge(str(durable_dir), store=bridge.BridgeStore(db))
        first.handle_event("Ev-canary-durable", harness.event_payload("durable sqlite"))
        store.close()
        second, _slack2, _github2, mcp2, store2 = harness.build_bridge(str(durable_dir), store=bridge.BridgeStore(db))
        replay = second.handle_event("Ev-canary-durable", harness.event_payload("durable sqlite"))
        checks.append(_check(
            "restart_sqlite_does_not_resubmit",
            replay.get("state") in {"DELIVERED", "RETRY_DUPLICATE", "SOURCE_COLLAPSE"} and len([n for n, _ in mcp2.calls if n == "fire_action"]) == 0,
            str(replay.get("state")),
        ))
        store2.close()

        serve_args = type("Args", (), {
            "state_db": root / "serve.sqlite3",
            "mcp_url": "https://commons-spark-mcp.vercel.app/mcp",
            "health_bind": "off",
            "workers": 1,
            "recovery_interval": 1.0,
        })()
        old_bot = os.environ.pop("SLACK_BOT_TOKEN", None)
        old_app = os.environ.pop("SLACK_APP_TOKEN", None)
        serve_buf = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = serve_buf
            code = bridge.serve(serve_args)
        finally:
            sys.stdout = old_out
            if old_bot is not None:
                os.environ["SLACK_BOT_TOKEN"] = old_bot
            if old_app is not None:
                os.environ["SLACK_APP_TOKEN"] = old_app
        serve_out = serve_buf.getvalue()
        blob_parts.append(serve_out)
        checks.append(_check("serve_unconfigured_exits_2", code == 2 and "RUNTIME_UNCONFIGURED" in serve_out))
        checks.append(_check("serve_unconfigured_omits_token_prefixes", not bridge.TOKEN_VALUE_RE.search(serve_out)))

        example = bridge.integration_root() / "env.example"
        example_text = example.read_text(encoding="utf-8") if example.is_file() else ""
        checks.append(_check(
            "env_example_has_empty_values",
            "SLACK_BOT_TOKEN=\n" in example_text.replace("\r\n", "\n") and "SLACK_APP_TOKEN=\n" in example_text.replace("\r\n", "\n"),
        ))
        checks.append(_check("env_example_has_no_token_prefixes", not bridge.TOKEN_VALUE_RE.search(example_text)))

    combined = "\n".join(blob_parts)
    checks.append(_check("canary_stdio_has_no_live_token_prefixes", not bridge.TOKEN_VALUE_RE.search(combined)))
    ok = all(item["ok"] for item in checks)
    return {
        "schema": "commons-grok-slack-canary/v1",
        "ok": ok,
        "passed": sum(1 for item in checks if item["ok"]),
        "failed": [item["name"] for item in checks if not item["ok"]],
        "checks": checks,
        "final_delivery_owner": bridge.FINAL_DELIVERY_OWNER,
        "runtime_state": "CODE_LANDED_RUNTIME_UNCONFIGURED",
        "external_action": (
            "Create the Slack app from integrations/grok_slack/app_manifest.yaml "
            "(id A0BTJMFPTT6), open http://127.0.0.1:8789/, paste SLACK_BOT_TOKEN "
            "and SLACK_APP_TOKEN once (never into the Gemini 8780 page), then the "
            "encrypted vault plus serve survive restart."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
