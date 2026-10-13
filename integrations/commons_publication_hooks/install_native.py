"""Add native publication hooks to existing settings; never start a client."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _publication_handler(handler: dict) -> bool:
    """Recognize only this native adapter, including split command/args."""
    command = str(handler.get("command", ""))
    arguments = handler.get("args", [])
    if isinstance(arguments, list):
        command += " " + " ".join(str(argument) for argument in arguments)
    command = command.replace("\\", "/")
    return bool(re.search(
        r"(?:^|[/\s\"'])(?:commons-publication-hooks|"
        r"integrations/commons_publication_hooks)/native\.py(?=$|[\s\"'])",
        command,
    ))


def _refresh(handler: dict, command: str) -> None:
    handler["command"] = command
    handler.pop("args", None)


def configure(config: dict, *, client: str, command: str) -> dict:
    # Preserve global and per-hook disable flags. Adding a policy does not
    # authorize waking another hook, agent, or disabled product.
    hooks = config.setdefault("hooks", {})
    if client == "cursor":
        config.setdefault("version", 1)
        for event in ("sessionStart", "preToolUse", "beforeMCPExecution"):
            entries = hooks.setdefault(event, [])
            found = False
            for item in entries:
                if _publication_handler(item):
                    _refresh(item, command)
                    found = True
            if found:
                continue
            item = {"command": command, "timeout": 5}
            if event != "sessionStart":
                item["failClosed"] = True
            entries.append(item)
    else:
        for event in ("SessionStart", "BeforeAgent", "BeforeTool"):
            groups = hooks.setdefault(event, [])
            found = False
            for group in groups:
                for item in group.get("hooks", []):
                    if (item.get("name") == "commons-publication-" + event.lower()
                            or _publication_handler(item)):
                        _refresh(item, command)
                        found = True
            if found:
                continue
            groups.append({"matcher": "*", "hooks": [{
                "name": "commons-publication-" + event.lower(),
                "type": "command", "command": command, "timeout": 5000,
            }]})
    return config


def install(config_dir: Path, *, client: str) -> dict:
    if not config_dir.is_dir():
        raise ValueError("native client config directory must already exist")
    source = Path(__file__).resolve().parent
    repo = source.parents[1]
    destination = config_dir / "commons-publication-hooks"
    destination.mkdir(exist_ok=True)
    for name in ("hook.py", "native.py"):
        shutil.copy2(source / name, destination / name)
    shutil.copy2(repo / "commons_publication_policy.py",
                 destination / "commons_publication_policy.py")
    path = config_dir / ("hooks.json" if client == "cursor" else "settings.json")
    config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    command = f'"{sys.executable}" "{destination / "native.py"}" --client {client}'
    configure(config, client=client, command=command)
    temporary = path.with_suffix(path.suffix + ".commons-publication.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {"config": str(path), "hook": str(destination / "native.py"),
            "client_started": False, "disable_flags_preserved": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--client", choices=("cursor", "gemini"), required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.config_dir, client=args.client)))
