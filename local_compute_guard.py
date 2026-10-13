#!/usr/bin/env python3
"""Reject unsafe automatic owner-laptop compute roads.

The laptop may inject, address, read, display, or execute an explicitly chosen
physical-device action. Ordinary repo events may not start resident services,
emulators, host gate evaluators, infinite loops, visible terminal churn, or the
self-hosted runner. A hidden bounded relay may remain only until its cloud
replacement has a real successful readback.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Rule:
    path: str
    required: tuple[str, ...] = ()
    banned: tuple[str, ...] = ()


RULES = (
    Rule(
        "infra/discord/install_windows_runtime.ps1",
        required=(
            "CloudCutoverVerified",
            "TemporaryStandby",
            "REFUSE_LOCAL_REACTIVATION",
            "Unregister-ScheduledTask",
            "CLOUD_ONLY",
            "-WindowStyle Hidden",
            "New-ScheduledTaskSettingsSet -Hidden",
            "New-TimeSpan -Minutes 15",
        ),
        banned=("-RestartCount 99", "-RepetitionInterval (New-TimeSpan -Minutes 1)"),
    ),
    Rule(
        "infra/discord/run_bridge_windows.ps1",
        required=("commons_discord_bridge.py", "Compatibility standby only"),
        banned=("Start-Process",),
    ),
    Rule(
        "infra/discord/health_watch_windows_runtime.ps1",
        required=("[int]$RetryCount = 3", "curl.exe", "schtasks.exe"),
        banned=("Start-Process",),
    ),
    Rule(
        "host/titan_hands/register_codex.ps1",
        required=("TITAN_HANDS_ANDROID_AUTOSTART=0",),
        banned=("TITAN_HANDS_ANDROID_AUTOSTART=1",),
    ),
    Rule(
        "muhl/containers/MUHL_VISIBLE/FOUNDRY_FOREVER.bat",
        required=("REFUSE_LOCAL_COMPUTE",),
        banned=("goto loop", "timeout /t", "schtasks", "python muhl_foundry_live.py"),
    ),
    Rule(
        "muhl/containers/MUHL_VISIBLE/muhl_foundry_live.py",
        required=('os.environ.get("GITHUB_ACTIONS"', "REFUSE_LOCAL_COMPUTE"),
    ),
    Rule(
        ".github/workflows/commons-board.yml",
        required=("does not allocate the owner's self-hosted laptop runner",),
        banned=("uses: ./.github/workflows/commons-device-executor.yml",),
    ),
    Rule(
        ".github/workflows/commons-discord-cloud.yml",
        required=("runs-on: ubuntu-latest", "commons_discord.py sync-in", "to-discord send"),
        banned=("self-hosted",),
    ),
    Rule(
        ".github/workflows/muhlnickel-foundry-cloud.yml",
        required=("runs-on: ubuntu-latest", "timeout-minutes: 15", "actions/upload-artifact@v4"),
        banned=("self-hosted",),
    ),
)

RETIRED_HOST_EVALUATORS = (
    "host/pfc_harness.py",
    "infra/host/pfc_harness.py",
    "infra/host/sdc_fwd_sdc.py",
    "infra/host/sdc_fwd_start.py",
    "muhl/desktop/MUHLNICKEL_HARNESSES/pfc_harness.py",
)


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for rule in RULES:
        path = root / rule.path
        if not path.is_file():
            errors.append(f"missing placement file: {rule.path}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in rule.required:
            if token not in text:
                errors.append(f"{rule.path}: missing {token!r}")
        lower = text.lower()
        for token in rule.banned:
            if token.lower() in lower:
                errors.append(f"{rule.path}: banned {token!r}")

    for name in RETIRED_HOST_EVALUATORS:
        path = root / name
        if not path.is_file():
            errors.append(f"missing compatibility tombstone: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if "REFUSE_HOST_COMPUTE" not in text:
            errors.append(f"{name}: missing fail-closed receipt")
        for token in ("mmap.mmap", "subprocess.run", "subprocess.Popen", "GGUF("):
            if token in text:
                errors.append(f"{name}: active host evaluator token {token!r}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("LOCAL COMPUTE PLACEMENT — REJECTED", file=sys.stderr)
        for error in errors:
            print("- " + error, file=sys.stderr)
        return 1
    print("LOCAL COMPUTE PLACEMENT — CLOUD_PRIMARY / SAFE_STANDBY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
