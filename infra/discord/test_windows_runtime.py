import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))

from infra.discord import assert_ready


class WindowsRuntimeTest(unittest.TestCase):
    def text(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_installer_has_safe_standby_and_verified_cloud_cutover(self):
        script = self.text("install_windows_runtime.ps1")
        self.assertIn("Commons Discord Live Bridge v1", script)
        self.assertIn("Commons Discord Main Watcher v1", script)
        self.assertIn("Commons Discord Health Watcher v1", script)
        self.assertIn("CloudCutoverVerified", script)
        self.assertIn("TemporaryStandby", script)
        self.assertIn("REFUSE_LOCAL_REACTIVATION", script)
        self.assertIn("Stop-ScheduledTask", script)
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertIn("New-ScheduledTask", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("New-ScheduledTaskSettingsSet -Hidden", script)
        self.assertIn("Get-Command pythonw.exe", script)
        self.assertIn("commons_discord_bridge.py", script)
        self.assertIn("New-ScheduledTaskAction -Execute $pythonw", script)
        self.assertNotIn("$bridgeRunner", script)
        self.assertIn("New-TimeSpan -Minutes 15", script)
        self.assertIn("New-TimeSpan -Minutes 5", script)
        self.assertIn("-RestartCount 3", script)
        self.assertIn("-RestartCount 1", script)
        self.assertNotIn("-RestartCount 99", script)
        self.assertNotIn("-RepetitionInterval (New-TimeSpan -Minutes 1)", script)

    def test_installer_preserves_checkout_and_open_door(self):
        script = self.text("install_windows_runtime.ps1")
        for destructive in ("reset", "clean -", "Remove-Item"):
            self.assertNotIn(destructive, script)

    def test_health_watcher_is_bounded_and_preserves_bridge_until_cutover(self):
        script = self.text("health_watch_windows_runtime.ps1")
        self.assertIn("[int]$TimeoutSec = 10", script)
        self.assertIn("[int]$RetryCount = 3", script)
        self.assertIn("[int]$RetryDelaySec = 20", script)
        self.assertIn("curl.exe", script)
        self.assertIn("schtasks.exe", script)
        self.assertIn("/End /TN $bridgeTask", script)
        self.assertIn("/Run /TN $bridgeTask", script)
        self.assertIn("journal-open and server startup grace", script)
        self.assertNotIn("Start-Process", script)

    def test_bridge_task_owns_the_listener_process_for_reliable_restart(self):
        installer = self.text("install_windows_runtime.ps1")
        self.assertIn("New-ScheduledTaskAction -Execute $pythonw", installer)
        self.assertIn("-Argument ('-B \"' + $bridgeScript + '\"')", installer)
        self.assertNotIn("run_bridge_windows.ps1", installer)

    def test_hidden_standby_bridge_and_watcher_preserve_functionality(self):
        bridge = self.text("run_bridge_windows.ps1")
        watcher = self.text("run_main_watcher_windows.ps1")
        self.assertIn("commons_discord_bridge.py", bridge)
        self.assertIn("& $python", bridge.lower())
        self.assertNotIn("Start-Process", bridge)
        self.assertIn("--untracked-files=no", watcher)
        self.assertIn("pull --ff-only --quiet origin main", watcher)
        self.assertIn("*> $null", watcher)
        self.assertGreater(
            watcher.index("pull --ff-only --quiet origin main"),
            watcher.index("--untracked-files=no"),
        )
        for destructive in ("reset", "clean -", "Remove-Item"):
            self.assertNotIn(destructive, bridge + watcher)

    def test_cloud_workflow_replaces_the_resident_bridge(self):
        workflow = (ROOT.parents[1] / ".github" / "workflows" / "commons-discord-cloud.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("python3 commons_discord.py sync-in", workflow)
        self.assertIn("python3 commons_discord.py to-discord send", workflow)
        self.assertIn("assert_ready.py discord_to_commons", workflow)
        self.assertIn("assert_ready.py commons_to_discord", workflow)
        self.assertIn("schedule:", workflow)
        self.assertNotIn("self-hosted", workflow)

    def test_cloud_readiness_fails_dark_and_accepts_exact_ready_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "doctor.json"
            report.write_text(
                json.dumps(
                    {
                        "discord_to_commons": {"state": "READY"},
                        "commons_to_discord": {"state": "DARK"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                assert_ready.main(["discord_to_commons", str(report)]),
                0,
            )
            self.assertEqual(
                assert_ready.main(["commons_to_discord", str(report)]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
