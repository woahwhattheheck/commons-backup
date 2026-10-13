"""Install async forwarding into an existing capture gateway without starting it."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import shutil
from pathlib import Path


MARKER = "commons-async-upstream-v1"
UPSTREAM_KEYS = ("upstream_request_id", "upstream_status_url", "upstream_status",
                 "upstream_terminal", "upstream_error")
UPSTREAM_METHOD = '''    def upstream_turn(self, peer_name: str, message: str, on_submitted=None) -> str:
        # commons-async-upstream-v1: retain the direct gateway request handle.
        from commons_async_upstream import wait_peer_turn

        def post_json(url, payload, *, timeout):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8",
                         "User-Agent": "commons-gemini-peer-capture/1"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        def get_json(url, *, timeout):
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        return wait_peer_turn(
            self.upstream, peer_name, message, post_json=post_json,
            get_json=get_json, on_submitted=on_submitted,
        )
'''


def _replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("Existing capture gateway has a different forwarding layout")
    return source.replace(before, after, 1)


def patch_gateway(source: str) -> str:
    tree = ast.parse(source)
    terminal_marker = "# commons-async-terminal-v1"
    if terminal_marker not in source:
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "TERMINAL_STATUSES"
                               for target in node.targets)]
        if len(assignments) != 1:
            raise ValueError("Expected the existing capture terminal status set")
        terminal_lines = source.splitlines(keepends=True)
        terminal_lines.insert(assignments[0].end_lineno,
                              f"TERMINAL_STATUSES = TERMINAL_STATUSES | {{'interrupted'}}  {terminal_marker}\n")
        source = "".join(terminal_lines)
        tree = ast.parse(source)
    gateways = [node for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == "Gateway"]
    if len(gateways) != 1:
        raise ValueError("Expected the existing Gateway class")
    methods = {node.name: node for node in gateways[0].body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not {"__init__", "upstream_turn", "execute"} <= methods.keys():
        raise ValueError("Expected the existing capture forwarding methods")
    lines = source.splitlines(keepends=True)
    upstream = methods["upstream_turn"]
    execute = methods["execute"]
    constructor = methods["__init__"]
    old_constructor = "".join(lines[constructor.lineno - 1:constructor.end_lineno])
    old_upstream = "".join(lines[upstream.lineno - 1:upstream.end_lineno])
    old_execute = "".join(lines[execute.lineno - 1:execute.end_lineno])
    if MARKER in old_upstream:
        if ("on_submitted=remember_upstream" not in old_execute
                or "commons-async-recovery-v1" not in old_constructor):
            raise ValueError("Capture gateway contains an incomplete async installation")
        return source

    replacement = _replace_once(
        old_execute,
        "        started = time.monotonic()\n        try:\n",
        "        started = time.monotonic()\n"
        "        upstream_details = {}\n"
        "\n"
        "        def remember_upstream(details):\n"
        "            upstream_details.update({key: value for key, value in details.items()\n"
        f"                                     if key in {UPSTREAM_KEYS!r}}})\n"
        "            self.events.append(request_id=request_id, peer=peer_name,\n"
        "                               status=\"running\", **upstream_details)\n"
        "\n"
        "        try:\n",
    )
    replacement = _replace_once(
        replacement,
        "                    reply = self.upstream_turn(peer_name, message)\n",
        "                    reply = self.upstream_turn(\n"
        "                        peer_name, message, on_submitted=remember_upstream\n"
        "                    )\n",
    )
    replacement = _replace_once(
        replacement,
        "                reply_bytes=len(reply_bytes),\n",
        "                reply_bytes=len(reply_bytes),\n"
        "                **upstream_details,\n",
    )
    replacement = _replace_once(
        replacement,
        "        except Exception as exc:\n            return self.events.append(\n",
        "        except Exception as exc:\n"
        "            error_details = getattr(exc, \"details\", None)\n"
        "            if not isinstance(error_details, dict):\n"
        "                error_details = {}\n"
        "            return self.events.append(\n",
    )
    replacement = _replace_once(
        replacement,
        "                message=str(exc),\n",
        "                message=str(exc),\n"
        "                **{**upstream_details, **{key: value for key, value in error_details.items()\n"
        f"                   if key in {UPSTREAM_KEYS!r}}}}},\n",
    )
    recovery = _replace_once(
        old_constructor,
        "        self.events = EventStore(event_log)\n",
        "        self.events = EventStore(event_log)\n"
        "        # commons-async-recovery-v1: retain handles without replaying work.\n"
        "        if self.upstream is not None:\n"
        "            for event in list(self.events.latest_by_request.values()):\n"
        "                if event.get(\"status\") not in TERMINAL_STATUSES:\n"
        "                    details = {key: value for key, value in event.items()\n"
        f"                               if key in {UPSTREAM_KEYS!r}}}\n"
        "                    details.update(upstream_status=\"unknown\", upstream_terminal=False)\n"
        "                    self.events.append(\n"
        "                        request_id=event[\"request_id\"], peer=event.get(\"peer\"),\n"
        "                        status=\"interrupted\",\n"
        "                        message=\"capture restarted; remote work may continue at the retained handle\",\n"
        "                        **details,\n"
        "                    )\n",
    )
    for node, content in sorted(((upstream, UPSTREAM_METHOD), (execute, replacement),
                                (constructor, recovery)),
                                key=lambda item: item[0].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [content]
    result = "".join(lines)
    ast.parse(result)
    return result


def install(gateway: Path, helper: Path, backup_dir: Path) -> dict:
    gateway, helper, backup_dir = gateway.resolve(), helper.resolve(), backup_dir.resolve()
    if not gateway.is_file() or not helper.is_file():
        raise ValueError("Both the existing gateway and transport helper must exist")
    if gateway == helper:
        raise ValueError("The gateway and helper must be separate files")
    source = gateway.read_text(encoding="utf-8")
    patched = patch_gateway(source)
    helper_source = helper.read_text(encoding="utf-8")
    helper_tree = ast.parse(helper_source)
    names = {getattr(node, "name", None) for node in helper_tree.body}
    if not {"wait_peer_turn", "UpstreamTurnError"} <= names:
        raise ValueError("Transport helper has a different interface")

    destination = gateway.parent / "commons_async_upstream.py"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if patched != source:
        shutil.copy2(gateway, backup_dir / (gateway.name + "." + stamp + ".bak"))
    if destination.exists() and destination.read_text(encoding="utf-8") != helper_source:
        shutil.copy2(destination, backup_dir / (destination.name + "." + stamp + ".bak"))
    temporary_helper = destination.with_suffix(".py.async.tmp")
    temporary_helper.write_text(helper_source, encoding="utf-8")
    temporary_helper.replace(destination)
    if patched != source:
        temporary_gateway = gateway.with_suffix(".py.async.tmp")
        temporary_gateway.write_text(patched, encoding="utf-8")
        temporary_gateway.replace(gateway)
    return {"gateway": str(gateway), "helper": str(destination),
            "source_updated": patched != source, "process_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.gateway, args.helper, args.backup_dir)))
