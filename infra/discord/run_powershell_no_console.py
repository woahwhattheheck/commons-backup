"""Run a scheduled PowerShell watcher without allocating a console window.

Invoke this file with pythonw.exe. PowerShell's own -WindowStyle Hidden acts
after console creation and can flash Windows Terminal on an interactive task.
The watcher, its exit status, and its normal recovery behavior remain intact.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import traceback
from pathlib import Path


def run(script: Path, powershell: str, log_file: Path) -> int:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with log_file.open("ab", buffering=0) as log:
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-ExecutionPolicy", "Bypass", "-File", str(script.resolve())],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
                startupinfo=startup,
                check=False,
            )
            return result.returncode
        except Exception:
            log.write(traceback.format_exc().encode("utf-8"))
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--powershell", default=str(
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"))
    parser.add_argument("--log-file", type=Path, default=(
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "Commons" / "discord-runtime.log"))
    args = parser.parse_args()
    return run(args.script, args.powershell, args.log_file)


if __name__ == "__main__":
    raise SystemExit(main())
