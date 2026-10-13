from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class AssetTests(unittest.TestCase):
    def test_codex_registration_is_direct_and_no_prompt(self):
        script = (ROOT / "host" / "titan_hands" / "register_codex.ps1").read_text(encoding="utf-8")
        self.assertIn("host.titan_hands.mcp_one", script)
        self.assertNotIn("'host.titan_hands.mcp_server'", script)
        self.assertIn('default_tools_approval_mode = \"approve\"', script)
        self.assertIn("TITAN_HANDS_ANDROID_AUTOSTART=0", script)
        self.assertNotIn("TITAN_HANDS_ANDROID_AUTOSTART=1", script)
        self.assertIn("TITAN_HANDS_ANDROID_BACKEND=auto", script)

    def test_headless_setup_uses_verified_official_archive(self):
        script = (ROOT / "host" / "titan_hands" / "setup_android_headless.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("dl.google.com/android/repository/commandlinetools-win-", script)
        self.assertIn("90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a", script)
        self.assertIn("system-images;android-34;default;x86_64", script)

    def test_headless_launcher_avoids_snapshot_disk_pressure_and_surfaces_logs(self):
        script = (ROOT / "host" / "titan_hands" / "start_android_headless.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'-no-snapshot'", script)
        self.assertIn("'-no-snapstorage'", script)
        self.assertIn("'-QuickbootFileBacked'", script)
        self.assertIn("snapshots\\default_boot\\ram.img", script)
        self.assertIn("SetLength(0)", script)
        self.assertIn("RedirectStandardError", script)
        self.assertIn("exited before ADB registration", script)

    def test_headless_launcher_recovers_exact_offline_avd_before_spawning(self):
        script = (ROOT / "host" / "titan_hands" / "start_android_headless.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("function Get-AdbEmulators", script)
        self.assertIn("function Get-ExactAvdProcesses", script)
        self.assertIn("[int]$TimeoutSeconds = 480", script)
        self.assertIn("$processName -ieq 'emulator.exe'", script)
        self.assertIn("^qemu-system-.+-headless\\.exe$", script)
        self.assertIn("emu avd name", script)
        self.assertIn("$_.avd -eq $AvdName", script)
        self.assertIn("[regex]::Escape($AvdName)", script)
        self.assertIn("& $adb reconnect offline", script)
        self.assertIn("Stop-Process -Id $process.ProcessId -Force -PassThru", script)
        self.assertIn("Wait-Process -Timeout 10", script)
        self.assertIn("refusing to start a duplicate emulator", script)
        self.assertIn("offline_reconnect_attempted", script)
        self.assertIn("offline_process_restarted", script)
        self.assertIn("function Wait-HeadlessBoot", script)
        self.assertIn("function Test-AndroidCoreServices", script)
        self.assertIn("shell service check package", script)
        self.assertIn("Service package:\\s+found", script)
        self.assertIn("$booted -eq '1' -and (Test-AndroidCoreServices", script)
        self.assertNotIn("if ($booted -eq '1') { return $candidateSerial }", script)
        self.assertIn("readiness_probe = 'sys.boot_completed+service package'", script)
        self.assertIn("boot_incomplete_process_restarted", script)
        self.assertIn("timeout_seconds_per_attempt", script)
        self.assertNotIn("-wipe-data", script)
        self.assertLess(
            script.index("& $adb reconnect offline"),
            script.index("Start-Process -FilePath $emulator"),
        )

    def test_windows_launch_omits_argument_list_when_empty(self):
        script = (ROOT / "host" / "titan_hands_windows" / "backend.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("if ($arguments.Count -gt 0)", script)
        self.assertIn("$startParameters.ArgumentList = $arguments", script)
        self.assertIn("Start-Process @startParameters", script)

    def test_lda_installer_builds_the_owner_kotlin_and_probes_receiver(self):
        script = (ROOT / "host" / "titan_hands" / "install_lda_emulator.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn(":app:assembleDebug", script)
        self.assertIn("com.local.deviceagent/.TitanHandsReceiver", script)
        self.assertIn("ActionAccessibilityService", script)
        self.assertIn("cmd package compile -m speed -f $packageName", script)
        self.assertIn("LDA package precompile failed", script)

    def test_receiver_exposes_marked_capture_op(self):
        receiver = (ROOT / "lda" / "app" / "src" / "main" / "java" / "com" / "local" / "deviceagent" / "TitanHandsReceiver.kt").read_text(
            encoding="utf-8"
        )
        overlay = (ROOT / "lda" / "app" / "src" / "main" / "java" / "com" / "local" / "deviceagent" / "TitanHandsMarks.kt").read_text(
            encoding="utf-8"
        )
        self.assertIn('"capture"', receiver)
        self.assertIn("goAsync()", receiver)
        self.assertIn("captureScreenshot", receiver)
        self.assertIn("currentMarks()", receiver)
        self.assertIn("set-of-marks", receiver)
        self.assertIn("TitanHandsMarks.jpeg", receiver)
        self.assertIn("0xF01E88E5", overlay)
        self.assertIn("0x99FFC107", overlay)
        self.assertIn("marks.ids.getOrNull", overlay)
        self.assertIn("Set-of-Marks", (ROOT / "host" / "titan_hands" / "mcp_server.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
