"""Headless Android adapter backed by ADB and UIAutomator XML.

The normal observation loop is framebuffer-free: Android exposes its accessibility
tree as XML, which is normalized into the same DeltaUI protocol used by Windows.
Pixels are transferred only for an explicit capture request.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Protocol

from host.titan_hands_windows.protocol import PROTOCOL_VERSION, DeltaTracker, ProtocolError, failure

from .lda_bridge import LdaBridge, LdaBridgeError, snapshot_nodes, to_lda_action, write_marked_image


BOUNDS_RE = re.compile(r"^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$")


class AndroidBackendError(RuntimeError):
    def __init__(self, reason: str, message: str, **evidence: Any) -> None:
        super().__init__(message)
        self.reason = reason
        self.evidence = evidence


class AndroidBackend(Protocol):
    serial: str | None

    def devices(self) -> list[dict[str, str]]: ...

    def resolve_serial(self) -> str: ...

    def shell(self, *args: str, timeout: float = 30) -> str: ...

    def exec_out(self, *args: str, timeout: float = 30) -> bytes: ...


class AdbClient:
    """Small ADB client with deterministic device selection and typed failures."""

    def __init__(self, adb_path: str | None = None, serial: str | None = None) -> None:
        configured = adb_path or os.environ.get("TITAN_HANDS_ADB")
        self.adb_path = configured or shutil.which("adb") or "adb"
        self.serial = serial or os.environ.get("TITAN_HANDS_ANDROID_SERIAL") or None
        self._autostart_attempted = False

    def _run(self, args: list[str], *, timeout: float, binary: bool) -> subprocess.CompletedProcess[Any]:
        command = [self.adb_path, *args]
        try:
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=timeout,
                text=not binary,
                encoding=None if binary else "utf-8",
                errors=None if binary else "replace",
            )
        except FileNotFoundError as exc:
            raise AndroidBackendError("ADB_MISSING", f"adb executable not found: {self.adb_path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AndroidBackendError("ADB_TIMEOUT", f"adb command timed out: {' '.join(args)}") from exc

    def devices(self) -> list[dict[str, str]]:
        completed = self._run(["devices", "-l"], timeout=10, binary=False)
        if completed.returncode != 0:
            raise AndroidBackendError(
                "ADB_FAILED",
                (completed.stderr or completed.stdout or "adb devices failed").strip(),
                returncode=completed.returncode,
            )
        result: list[dict[str, str]] = []
        for line in completed.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            entry = {"serial": parts[0], "state": parts[1] if len(parts) > 1 else "unknown"}
            for token in parts[2:]:
                if ":" in token:
                    key, value = token.split(":", 1)
                    entry[key] = value
            result.append(entry)
        return result

    def resolve_serial(self) -> str:
        all_online = [device for device in self.devices() if device.get("state") == "device"]
        if self.serial:
            if any(device.get("serial") == self.serial for device in all_online):
                return self.serial
            raise AndroidBackendError(
                "DEVICE_MISS",
                f"configured Android target is not online: {self.serial}",
                online=[device.get("serial") for device in all_online],
            )
        # Defaulting to an arbitrary single ADB target can silently select a personal
        # phone. Colony operation is emulator-only unless an operator explicitly sets
        # TITAN_HANDS_ANDROID_SERIAL.
        online = [device for device in all_online if device.get("serial", "").startswith("emulator-")]
        if not online and self._autostart_enabled() and not self._autostart_attempted:
            self._autostart_attempted = True
            self._start_headless_emulator()
            deadline = time.monotonic() + float(os.environ.get("TITAN_HANDS_ANDROID_BOOT_TIMEOUT", "240"))
            while time.monotonic() < deadline:
                online = [
                    device
                    for device in self.devices()
                    if device.get("state") == "device" and device.get("serial", "").startswith("emulator-")
                ]
                if online and self._boot_completed(online[0]["serial"]):
                    break
                online = []
                time.sleep(2)
        if not online:
            raise AndroidBackendError(
                "DEVICE_MISS",
                "no online Android emulator; set TITAN_HANDS_ANDROID_SERIAL to explicitly select another target",
                online=[device.get("serial") for device in all_online],
            )
        if len(online) > 1:
            raise AndroidBackendError(
                "DEVICE_AMBIGUOUS",
                "multiple Android targets are online; set TITAN_HANDS_ANDROID_SERIAL",
                online=[device.get("serial") for device in online],
            )
        self.serial = online[0]["serial"]
        return self.serial

    def _boot_completed(self, serial: str) -> bool:
        completed = self._run(
            ["-s", serial, "shell", "getprop", "sys.boot_completed"],
            timeout=10,
            binary=False,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "1"

    @staticmethod
    def _autostart_enabled() -> bool:
        return os.environ.get("TITAN_HANDS_ANDROID_AUTOSTART", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _start_headless_emulator(self) -> None:
        sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
        executable = os.environ.get("TITAN_HANDS_ANDROID_EMULATOR")
        if not executable and sdk_root:
            executable = str(Path(sdk_root) / "emulator" / "emulator.exe")
        if not executable or not Path(executable).is_file():
            raise AndroidBackendError(
                "EMULATOR_MISSING",
                "headless emulator executable is not configured",
                expected=executable or "TITAN_HANDS_ANDROID_EMULATOR",
            )
        avd_name = os.environ.get("TITAN_HANDS_ANDROID_AVD", "TitanHands_AOSP_API34")
        command = [
            executable,
            "-avd",
            avd_name,
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-gpu",
            "swiftshader_indirect",
            "-memory",
            os.environ.get("TITAN_HANDS_ANDROID_MEMORY_MB", "1536"),
            "-cores",
            os.environ.get("TITAN_HANDS_ANDROID_CORES", "2"),
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        environment = os.environ.copy()
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=creationflags,
            close_fds=True,
        )

    def shell(self, *args: str, timeout: float = 30) -> str:
        serial = self.resolve_serial()
        completed = self._run(["-s", serial, "shell", *args], timeout=timeout, binary=False)
        if completed.returncode != 0:
            raise AndroidBackendError(
                "ADB_FAILED",
                (completed.stderr or completed.stdout or "adb shell failed").strip(),
                returncode=completed.returncode,
                serial=serial,
            )
        return completed.stdout

    def exec_out(self, *args: str, timeout: float = 30) -> bytes:
        serial = self.resolve_serial()
        completed = self._run(["-s", serial, "exec-out", *args], timeout=timeout, binary=True)
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", "replace")
            raise AndroidBackendError(
                "ADB_FAILED",
                stderr.strip() or "adb exec-out failed",
                returncode=completed.returncode,
                serial=serial,
            )
        return bytes(completed.stdout)


def _bool(attributes: Mapping[str, str], name: str) -> bool:
    return attributes.get(name, "false").lower() == "true"


def _bounds(value: str) -> dict[str, int]:
    match = BOUNDS_RE.match(value or "")
    if not match:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    left, top, right, bottom = (int(group) for group in match.groups())
    return {
        "x": left,
        "y": top,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def _role(class_name: str) -> str:
    leaf = (class_name or "").rsplit(".", 1)[-1]
    return {
        "Button": "Button",
        "ImageButton": "Button",
        "EditText": "TextBox",
        "TextView": "Text",
        "CheckBox": "CheckBox",
        "RadioButton": "RadioButton",
        "Switch": "Switch",
        "ImageView": "Image",
        "ListView": "List",
        "RecyclerView": "List",
        "ScrollView": "Pane",
        "WebView": "Document",
    }.get(leaf, leaf or "Node")


def parse_uiautomator_xml(xml_text: str, serial: str) -> list[dict[str, Any]]:
    """Convert a UIAutomator hierarchy into deterministic semantic nodes."""

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise AndroidBackendError("OBSERVATION_INVALID", f"invalid UIAutomator XML: {exc}") from exc

    nodes: list[dict[str, Any]] = []

    def visit(element: ET.Element, path: tuple[int, ...], parent: str) -> None:
        if element.tag != "node":
            for index, child in enumerate(list(element)):
                visit(child, path + (index,), parent)
            return
        attributes = {str(key): str(value) for key, value in element.attrib.items()}
        identity = "|".join(
            [
                serial,
                ".".join(str(part) for part in path),
                attributes.get("resource-id", ""),
                attributes.get("class", ""),
            ]
        )
        node_id = "a_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        bounds = _bounds(attributes.get("bounds", ""))
        states = [
            name
            for name in (
                "enabled",
                "focusable",
                "focused",
                "selected",
                "checked",
                "checkable",
                "clickable",
                "long-clickable",
                "scrollable",
                "password",
            )
            if _bool(attributes, name)
        ]
        class_name = attributes.get("class", "")
        role = _role(class_name)
        actions: list[str] = []
        if _bool(attributes, "clickable"):
            actions.extend(["click", "invoke"])
        if _bool(attributes, "focusable"):
            actions.append("focus")
        if _bool(attributes, "checkable"):
            actions.append("toggle")
        if role == "TextBox":
            actions.extend(["set_value", "type_text"])
        if _bool(attributes, "scrollable"):
            actions.append("scroll")
        resource_id = attributes.get("resource-id", "")
        text = attributes.get("text", "")
        description = attributes.get("content-desc", "")
        nodes.append(
            {
                "id": node_id,
                "parent": parent,
                "role": role,
                "name": text or description or resource_id.rsplit("/", 1)[-1],
                "automation_id": resource_id,
                "class_name": class_name,
                "package": attributes.get("package", ""),
                "content_description": description,
                "value": text,
                "bounds": bounds,
                "states": states,
                "actions": sorted(set(actions)),
            }
        )
        for index, child in enumerate(list(element)):
            visit(child, path + (index,), node_id)

    visit(root, (), "")
    return nodes


def _center(node: Mapping[str, Any]) -> tuple[int, int]:
    bounds = node.get("bounds") or {}
    return (
        int(bounds.get("x", 0)) + int(bounds.get("width", 0)) // 2,
        int(bounds.get("y", 0)) + int(bounds.get("height", 0)) // 2,
    )


def _input_text(value: str) -> str:
    # Android's input command uses %s for spaces. Backslash escaping keeps the
    # shell metacharacters literal while ADB transports this as one argument.
    escaped = str(value).replace("%", "%25").replace(" ", "%s")
    for character in "\\()<>|;&*~'\"`$":
        escaped = escaped.replace(character, "\\" + character)
    return escaped


class AndroidHandsServer:
    """Android TITAN surface, preferring the owner's LDA Kotlin operator."""

    def __init__(self, backend: AndroidBackend | None = None, lda_bridge: LdaBridge | None = None) -> None:
        default_backend = backend is None
        self.backend = backend or AdbClient()
        self.tracker = DeltaTracker()
        self._nodes: dict[str, dict[str, Any]] = {}
        self._lda_mode = os.environ.get("TITAN_HANDS_ANDROID_BACKEND", "auto").strip().lower()
        self._lda = lda_bridge
        if self._lda is None and default_backend and self._lda_mode != "uiautomator":
            self._lda = LdaBridge(self.backend)

    def close(self) -> None:
        return None

    def _lda_available(self) -> bool:
        return self._lda is not None and self._lda.available()

    def _lda_snapshot(self) -> dict[str, Any]:
        assert self._lda is not None
        result = self._lda.observe()
        if not result.get("ok"):
            raise AndroidBackendError(
                str(result.get("failure_reason") or "LDA_BRIDGE_FAILED"),
                str(result.get("message") or "LDA Kotlin observation failed"),
            )
        screen = str(result.get("snapshot") or "")
        nodes = snapshot_nodes(screen)
        self._nodes = {node["id"]: node for node in nodes}
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "android",
            "serial": self.backend.resolve_serial(),
            "focus_id": next(
                (node["id"] for node in nodes if "focused" in node.get("states", [])), ""
            ),
            "pixels": "not-captured",
            "implementation": "lda-kotlin",
            "source": "ActionAccessibilityService.snapshotScreen",
            "screen": screen,
        }

    def _lda_capture(self, output: Path | None) -> dict[str, Any]:
        assert self._lda is not None
        capture = getattr(self._lda, "capture", None)
        if not callable(capture):
            result: dict[str, Any] = {
                "ok": False,
                "failure_reason": "UNKNOWN_OPERATION",
                "message": "LDA bridge has no capture operation",
            }
        else:
            result = capture()
        if not result.get("ok"):
            reason = str(result.get("failure_reason") or "LDA_BRIDGE_FAILED")
            if reason == "UNKNOWN_OPERATION" and self._lda_mode != "lda":
                output = output or Path("artifacts/titan-hands/android.png").resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(self.backend.exec_out("screencap", "-p", timeout=30))
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "pixel_capture",
                    "platform": "android",
                    "visual": "adb-framebuffer",
                    "mime": "image/png",
                    "pixel_ref": str(output),
                    "serial": self.backend.resolve_serial(),
                    "fallback": "adb-screencap",
                    "lda_failure_reason": reason,
                }
            raise AndroidBackendError(
                reason,
                str(result.get("message") or "LDA Kotlin marked capture failed"),
            )
        output = output or Path("artifacts/titan-hands/android.jpg").resolve()
        try:
            normalized = write_marked_image(result, output)
        except LdaBridgeError as exc:
            raise AndroidBackendError("LDA_CAPTURE_INVALID", str(exc)) from exc
        normalized.setdefault("protocol", PROTOCOL_VERSION)
        normalized.setdefault("kind", "pixel_capture")
        normalized.setdefault("platform", "android")
        normalized["serial"] = self.backend.resolve_serial()
        return normalized

    def _snapshot(self) -> dict[str, Any]:
        if self._lda_available():
            return self._lda_snapshot()
        if self._lda_mode == "lda":
            raise AndroidBackendError(
                "LDA_BRIDGE_UNAVAILABLE",
                "the LDA APK or its accessibility service is not available",
            )
        serial = self.backend.resolve_serial()
        remote_path = "/sdcard/titan_hands_window.xml"
        last_error: AndroidBackendError | None = None
        nodes: list[dict[str, Any]] = []
        for attempt in range(3):
            self.backend.shell("uiautomator", "dump", remote_path, timeout=30)
            xml_bytes = self.backend.exec_out("cat", remote_path, timeout=15)
            xml_text = xml_bytes.decode("utf-8", "replace")
            starts = [position for position in (xml_text.find("<?xml"), xml_text.find("<hierarchy")) if position >= 0]
            if starts:
                xml_text = xml_text[min(starts) :]
            try:
                nodes = parse_uiautomator_xml(xml_text, serial)
                if nodes:
                    break
                last_error = AndroidBackendError("OBSERVATION_INVALID", "UIAutomator returned an empty hierarchy")
            except AndroidBackendError as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(0.4)
        if not nodes:
            assert last_error is not None
            raise last_error
        self._nodes = {node["id"]: node for node in nodes}
        focused = next((node["id"] for node in nodes if "focused" in node["states"]), "")
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "android",
            "serial": serial,
            "focus_id": focused,
            "pixels": "not-captured",
        }

    def _node(self, node_id: str) -> dict[str, Any]:
        node = self._nodes.get(node_id)
        if node is None:
            self._snapshot()
            node = self._nodes.get(node_id)
        if node is None:
            raise AndroidBackendError("ELEMENT_STALE", f"Android node is no longer present: {node_id}")
        return node

    def _act(self, action: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if not action_type:
            raise ProtocolError("action.type is required")
        if self._lda_available():
            assert self._lda is not None
            result = self._lda.act(to_lda_action(action, self._nodes))
            result.setdefault("protocol", PROTOCOL_VERSION)
            result.setdefault("kind", "action_outcome")
            result.setdefault("platform", "android")
            result.setdefault("serial", self.backend.resolve_serial())
            result.setdefault("action", action_type)
            return result
        if self._lda_mode == "lda":
            raise AndroidBackendError(
                "LDA_BRIDGE_UNAVAILABLE",
                "the LDA APK or its accessibility service is not available",
            )
        node: dict[str, Any] | None = None
        if action.get("id"):
            node = self._node(str(action["id"]))

        if action_type in {"click", "invoke", "focus", "select", "toggle"}:
            if node is None:
                raise ProtocolError(f"{action_type} requires id")
            x, y = _center(node)
            self.backend.shell("input", "tap", str(x), str(y))
        elif action_type in {"type_text", "set_value"}:
            value = str(action.get("value") or action.get("text") or "")
            if node is not None:
                x, y = _center(node)
                self.backend.shell("input", "tap", str(x), str(y))
            if action_type == "set_value" and node is not None:
                existing = str(node.get("value") or "")
                self.backend.shell("input", "keyevent", "KEYCODE_MOVE_END")
                for _ in existing:
                    self.backend.shell("input", "keyevent", "KEYCODE_DEL")
            if value:
                self.backend.shell("input", "text", _input_text(value))
        elif action_type == "key":
            key = str(action.get("key") or "").strip()
            if not key:
                raise ProtocolError("key action requires key")
            key_map = {
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
                "enter": "KEYCODE_ENTER",
                "tab": "KEYCODE_TAB",
                "escape": "KEYCODE_ESCAPE",
                "delete": "KEYCODE_DEL",
                "volume_up": "KEYCODE_VOLUME_UP",
                "volume_down": "KEYCODE_VOLUME_DOWN",
            }
            self.backend.shell("input", "keyevent", key_map.get(key.lower(), key))
        elif action_type == "scroll":
            direction = str(action.get("direction") or "down").lower()
            width = max((node or {}).get("bounds", {}).get("width", 1080), 100)
            height = max((node or {}).get("bounds", {}).get("height", 1920), 100)
            left = int((node or {}).get("bounds", {}).get("x", 0))
            top = int((node or {}).get("bounds", {}).get("y", 0))
            cx, cy = left + width // 2, top + height // 2
            distance = max(80, int((height if direction in {"up", "down"} else width) * 0.35))
            points = {
                "down": (cx, cy + distance, cx, cy - distance),
                "up": (cx, cy - distance, cx, cy + distance),
                "right": (cx + distance, cy, cx - distance, cy),
                "left": (cx - distance, cy, cx + distance, cy),
            }
            if direction not in points:
                raise ProtocolError(f"unknown scroll direction: {direction}")
            self.backend.shell("input", "swipe", *(str(value) for value in points[direction]), "300")
        elif action_type == "launch":
            package = str(action.get("package") or "").strip()
            activity = str(action.get("activity") or "").strip()
            if not package:
                raise ProtocolError("launch requires package")
            if activity:
                self.backend.shell("am", "start", "-n", f"{package}/{activity}")
            else:
                self.backend.shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        elif action_type == "wait":
            seconds = float(action.get("seconds") or 1)
            time.sleep(max(0.0, min(seconds, 60.0)))
        elif action_type == "done":
            pass
        else:
            raise ProtocolError(f"unsupported Android action: {action_type}")
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "android",
            "action": action_type,
            "serial": self.backend.resolve_serial(),
        }

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise ProtocolError("request must be an object")
            op = str(request.get("op") or "").strip().lower()
            if op == "capabilities":
                devices = self.backend.devices()
                lda_ready = self._lda_available()
                online = [
                    device
                    for device in devices
                    if device.get("state") == "device"
                    and (
                        bool(getattr(self.backend, "serial", None))
                        or device.get("serial", "").startswith("emulator-")
                    )
                ]
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "capabilities",
                    "platform": "android",
                    "transport": "adb",
                    "observation": (
                        "lda-numbered-world-model" if lda_ready else "uiautomator-semantic-delta"
                    ),
                    "pixels": (
                        "lda-set-of-marks-on-demand" if lda_ready else "on-demand-only"
                    ),
                    "implementation": "lda-kotlin" if lda_ready else "uiautomator-fallback",
                    "fallback": "uiautomator" if self._lda_mode != "lda" else None,
                    "online": bool(online),
                    "devices": devices,
                    "actions": [
                        "click",
                        "invoke",
                        "focus",
                        "select",
                        "toggle",
                        "type_text",
                        "set_value",
                        "key",
                        "scroll",
                        "launch",
                        "wait",
                        "done",
                    ],
                }
            if op == "observe":
                return self.tracker.observe(self._snapshot())
            if op == "reset":
                self.tracker.reset()
                self._nodes.clear()
                return {"ok": True, "protocol": PROTOCOL_VERSION, "kind": "reset", "platform": "android"}
            if op == "act":
                action = request.get("action")
                if not isinstance(action, Mapping):
                    raise ProtocolError("act requires an action object")
                result = self._act(action)
                if result.get("ok") and request.get("observe_after", True):
                    result["observation"] = self.tracker.observe(self._snapshot())
                return result
            if op == "capture":
                requested_path = request.get("path")
                output = Path(str(requested_path)).resolve() if requested_path else None
                if self._lda_available():
                    return self._lda_capture(output)
                output = output or Path("artifacts/titan-hands/android.png").resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(self.backend.exec_out("screencap", "-p", timeout=30))
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "pixel_capture",
                    "platform": "android",
                    "visual": "adb-framebuffer",
                    "mime": "image/png",
                    "pixel_ref": str(output),
                    "serial": self.backend.resolve_serial(),
                }
            return failure("UNKNOWN_OPERATION", f"unknown operation: {op or '<empty>'}")
        except AndroidBackendError as exc:
            return failure(exc.reason, str(exc), **exc.evidence)
        except (ProtocolError, TypeError, ValueError) as exc:
            return failure("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return failure("BACKEND_ERROR", str(exc))
