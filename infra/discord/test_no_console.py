"""Regression coverage for invisible Discord task and Git child launches."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
from infra.discord import run_powershell_no_console

SPEC = importlib.util.spec_from_file_location("no_console_bridge", ROOT / "commons_discord_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class NoConsoleTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "requires the real Windows console API")
    def test_watcher_has_no_console_and_retains_output_and_exit_status(self):
        with tempfile.TemporaryDirectory(prefix="commons-no-console-") as directory:
            script = Path(directory) / "probe.ps1"
            log = Path(directory) / "probe.log"
            script.write_text(
                'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; '
                'public class Probe { [DllImport("kernel32.dll")] '
                'public static extern IntPtr GetConsoleWindow(); }\'\n'
                'Write-Output ("CONSOLE=" + [Probe]::GetConsoleWindow().ToInt64())\n'
                'Write-Output "WATCHER_OUTPUT_PRESERVED"\nexit 23\n',
                encoding="utf-8",
            )
            powershell = str(Path(os.environ["SystemRoot"]) / "System32"
                             / "WindowsPowerShell" / "v1.0" / "powershell.exe")
            result = run_powershell_no_console.run(script, powershell, log)
            self.assertEqual(result, 23)
            output = log.read_text(encoding="utf-8")
            self.assertIn("CONSOLE=0", output)
            self.assertIn("WATCHER_OUTPUT_PRESERVED", output)

    def test_watcher_task_uses_no_console_root(self):
        script = (ROOT / "install_windows_runtime.ps1").read_text(encoding="utf-8")
        action = script.split("function New-HiddenPowerShellAction", 1)[1].split(
            "$bridgeAction", 1)[0]
        self.assertIn("New-ScheduledTaskAction -Execute $pythonw", action)
        self.assertIn("$noConsoleRunner", action)
        self.assertIn("run_powershell_no_console.py", script)

    def test_git_poll_keeps_cursor_behavior_without_allocating_windows(self):
        with mock.patch.object(bridge.subprocess, "check_output", side_effect=["new-head\n", ""]) as git:
            with mock.patch.object(bridge, "JOURNAL") as journal:
                journal.cursor.return_value = "old-head"
                bridge.poll_git()
                journal.set_cursor.assert_called_once_with("git-head", "new-head")
        self.assertEqual(git.call_count, 2)
        for call in git.call_args_list:
            self.assertEqual(call.kwargs["creationflags"],
                             getattr(bridge.subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    unittest.main()
