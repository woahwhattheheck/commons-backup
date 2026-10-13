"""ADB transport into the owner's existing LDA Kotlin handset operator."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Mapping, Protocol


ACTION = "com.local.deviceagent.TITAN_HANDS"
COMPONENT = "com.local.deviceagent/.TitanHandsReceiver"
RESULT_RE = re.compile(r'\bdata=(?:"([A-Za-z0-9+/=]+)"|([A-Za-z0-9+/=]+))')
ELEMENT_RE = re.compile(r"^\[(\d+)]\s*(.*)$")


class AdbShell(Protocol):
    serial: str | None

    def resolve_serial(self) -> str: ...

    def shell(self, *args: str, timeout: float = 30) -> str: ...


class LdaBridgeError(RuntimeError):
    pass


class LdaBridge:
    """Calls the Kotlin receiver; it does not implement a second Android executor."""

    def __init__(self, backend: AdbShell) -> None:
        self.backend = backend

    def _call(self, op: str, action: Mapping[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
        args = ["am", "broadcast", "-W", "-a", ACTION, "-n", COMPONENT, "--es", "op", op]
        if action is not None:
            raw = json.dumps(dict(action), ensure_ascii=False, separators=(",", ":"))
            encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
            args.extend(["--es", "action_b64", encoded])
        output = self.backend.shell(*args, timeout=timeout)
        match = RESULT_RE.search(output)
        if not match:
            raise LdaBridgeError(f"LDA TITAN receiver returned no result data: {output.strip()}")
        try:
            decoded = base64.b64decode(match.group(1) or match.group(2), validate=True).decode("utf-8")
            result = json.loads(decoded)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LdaBridgeError("LDA TITAN receiver returned invalid base64 JSON") from exc
        if not isinstance(result, dict):
            raise LdaBridgeError("LDA TITAN receiver result was not an object")
        return result

    def capabilities(self) -> dict[str, Any]:
        return self._call("capabilities")

    def available(self) -> bool:
        try:
            result = self.capabilities()
            return bool(result.get("ok") and result.get("accessibility_ready"))
        except Exception:
            return False

    def observe(self) -> dict[str, Any]:
        return self._call("observe")

    def act(self, action: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("act", action)

    def capture(self) -> dict[str, Any]:
        return self._call("capture", timeout=45)


def snapshot_nodes(snapshot: str) -> list[dict[str, Any]]:
    """Expose the LDA's numbered representation without replacing or reinterpreting it."""

    nodes: list[dict[str, Any]] = [
        {
            "id": "lda:screen",
            "parent": "",
            "role": "Document",
            "name": "LDA compact screen",
            "value": snapshot,
            "source": "ActionAccessibilityService.snapshotScreen",
            "states": [],
            "actions": [],
        }
    ]
    for line in snapshot.splitlines():
        match = ELEMENT_RE.match(line.strip())
        if not match:
            continue
        source_id = int(match.group(1))
        description = match.group(2).strip()
        lowered = description.lower()
        role = "TextBox" if "field" in lowered or "editable" in lowered else "Button"
        actions = ["click", "invoke"]
        if role == "TextBox":
            actions.extend(["set_value", "type_text"])
        states = [
            state
            for state in ("disabled", "selected", "focused", "checked")
            if f"[{state}" in lowered
        ]
        nodes.append(
            {
                "id": f"lda:{source_id}",
                "parent": "lda:screen",
                "role": role,
                "name": description,
                "value": description,
                "source_id": source_id,
                "source": "ActionAccessibilityService.snapshotScreen",
                "states": states,
                "actions": actions,
            }
        )
    return nodes


def source_id(value: Any, nodes: Mapping[str, Mapping[str, Any]]) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text in nodes and "source_id" in nodes[text]:
        return int(nodes[text]["source_id"])
    if text.isdigit():
        return int(text)
    match = re.fullmatch(r"lda[:_](\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def to_lda_action(action: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Translate common TITAN verbs into the LDA's native free-form action language."""

    action_type = str(action.get("type") or action.get("action") or "").strip().lower()
    if not action_type:
        raise LdaBridgeError("action.type is required")
    payload = dict(action)
    payload.pop("type", None)
    payload.pop("action", None)
    node_id = source_id(action.get("id"), nodes)
    if node_id is not None:
        payload["id"] = node_id

    if action_type in {"click", "invoke", "focus", "select", "toggle"}:
        payload["action"] = "click"
    elif action_type == "type_text":
        payload["action"] = "set_text"
        payload["text"] = str(action.get("text") or action.get("value") or "")
    elif action_type == "set_value" and not ({"percent", "pct"} & set(action)):
        payload["action"] = "set_text"
        payload["text"] = str(action.get("text") or action.get("value") or "")
    elif action_type == "launch":
        payload = {
            "action": "open_app",
            "name": str(action.get("name") or action.get("app") or action.get("package") or ""),
        }
    elif action_type == "key":
        key = str(action.get("key") or "").strip().lower()
        payload = {"action": key if key in {"back", "home", "enter"} else "press_key", "key": key}
    else:
        # Preserve the LDA's much larger native action language (find, aim, tap_grid, draw,
        # sketch, assert, get_text, open_app, batch, and future verbs) as a free-form road.
        payload["action"] = action_type
    return payload


def write_marked_image(result: Mapping[str, Any], output: Path) -> dict[str, Any]:
    """Persist the LDA Set-of-Marks JPEG and drop the wire base64 from the model-facing result."""

    encoded = str(result.get("image_b64") or "")
    if not encoded:
        raise LdaBridgeError("LDA marked capture returned no image_b64")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise LdaBridgeError("LDA marked capture image_b64 is not valid base64") from exc
    if not payload:
        raise LdaBridgeError("LDA marked capture image is empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    normalized = dict(result)
    normalized.pop("image_b64", None)
    normalized.pop("snapshot", None)
    normalized["ok"] = True
    normalized["pixel_ref"] = str(output)
    normalized["bytes"] = len(payload)
    normalized.setdefault("kind", "pixel_capture")
    normalized.setdefault("visual", "set-of-marks")
    normalized.setdefault("implementation", "lda-kotlin")
    normalized.setdefault("mime", "image/jpeg")
    return normalized
