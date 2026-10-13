"""Linux AT-SPI adapter for the existing TITAN Hands one-tool contract.

One model-facing MCP tool stays `titan_hands`. This module is the `target=linux`
hand: AT-SPI semantic tree + native actions for observe/act, compositor pixels
only when op=capture. Missing bus or libraries return a typed failure with a
measured probe. It does not remint the Windows or Android adapters.

Cite: p/coil-titan-hands-one-tool-20260826-01.md
      p/emissary-titan-hands-features-20260826-01.md
      p/emissary-titan-hands-unified-runtime-20260826-01.md
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from host.titan_hands_windows.protocol import PROTOCOL_VERSION, DeltaTracker, ProtocolError, failure


try:
    import dbus
    from dbus import bus as dbus_bus
    from dbus.exceptions import DBusException
except ImportError:  # pragma: no cover - measured at probe time
    dbus = None  # type: ignore[assignment]
    dbus_bus = None  # type: ignore[assignment]
    DBusException = Exception  # type: ignore[misc, assignment]

try:
    import pyatspi as _pyatspi  # noqa: F401
except ImportError:
    _pyatspi = None  # type: ignore[assignment]

try:
    import gi as _gi

    _gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi as _Atspi  # noqa: F401
except Exception:
    _Atspi = None  # type: ignore[assignment]


A11Y_BUS_NAME = "org.a11y.Bus"
A11Y_BUS_PATH = "/org/a11y/bus"
A11Y_BUS_IFACE = "org.a11y.Bus"
A11Y_STATUS_IFACE = "org.a11y.Status"
ATSPI_REGISTRY = "org.a11y.atspi.Registry"
ATSPI_ROOT_PATH = "/org/a11y/atspi/accessible/root"
ATSPI_ACCESSIBLE = "org.a11y.atspi.Accessible"
ATSPI_ACTION = "org.a11y.atspi.Action"
ATSPI_COMPONENT = "org.a11y.atspi.Component"
ATSPI_TEXT = "org.a11y.atspi.Text"
ATSPI_EDITABLE = "org.a11y.atspi.EditableText"
ATSPI_VALUE = "org.a11y.atspi.Value"
ATSPI_APPLICATION = "org.a11y.atspi.Application"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
PIXELS_ON_DEMAND = "on-demand-only"
PIXELS_NOT_CAPTURED = "not-captured"

LINUX_ACTIONS = (
    "invoke",
    "click",
    "set_value",
    "toggle",
    "expand",
    "collapse",
    "select",
    "focus",
    "type_text",
    "key",
    "scroll",
    "launch",
    "wait",
    "done",
)

ROLE_MAP = {
    "push button": "Button",
    "toggle button": "Button",
    "radio button": "RadioButton",
    "check box": "CheckBox",
    "combo box": "ComboBox",
    "entry": "Edit",
    "password text": "Edit",
    "text": "Text",
    "label": "Text",
    "frame": "Window",
    "window": "Window",
    "dialog": "Window",
    "desktop frame": "Desktop",
    "application": "Application",
    "panel": "Pane",
    "filler": "Pane",
    "scroll pane": "Pane",
    "menu item": "MenuItem",
    "menu": "Menu",
    "menu bar": "MenuBar",
    "tool bar": "ToolBar",
    "page tab": "Tab",
    "page tab list": "TabItem",
    "slider": "Slider",
    "link": "Hyperlink",
    "image": "Image",
    "list": "List",
    "list item": "ListItem",
    "table": "Table",
    "heading": "Header",
    "document frame": "Document",
    "terminal": "Pane",
    "status bar": "StatusBar",
    "split pane": "Pane",
    "progress bar": "ProgressBar",
    "spin button": "Spinner",
    "tree": "Tree",
    "tree item": "TreeItem",
    "icon": "Image",
    "canvas": "Pane",
}

# AT-SPI state bits from atspi-state.h (first 32 in flags[0], next in flags[1]).
STATE_BITS = {
    4: "checked",
    5: "collapsed",
    6: "defunct",
    7: "editable",
    8: "enabled",
    9: "expandable",
    10: "expanded",
    11: "focusable",
    12: "focused",
    20: "pressed",
    22: "selectable",
    23: "selected",
    24: "sensitive",
    25: "showing",
    30: "visible",
}

ACTION_ALIASES = {
    "invoke": ("click", "press", "activate", "default", "jump"),
    "click": ("click", "press", "activate"),
    "toggle": ("toggle", "click", "press"),
    "expand": ("expand", "open"),
    "collapse": ("collapse", "close"),
    "select": ("select", "click"),
}


class LinuxBackendError(RuntimeError):
    def __init__(self, reason: str, message: str, **evidence: Any) -> None:
        super().__init__(message)
        self.reason = reason
        self.evidence = evidence


class AtspiBackend(Protocol):
    def capabilities(self) -> dict[str, Any]: ...

    def snapshot(
        self, *, max_nodes: int, max_depth: int, include_offscreen: bool
    ) -> dict[str, Any]: ...

    def act(self, action: Mapping[str, Any]) -> dict[str, Any]: ...

    def capture(self, request: Mapping[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _plain(value: Any) -> Any:
    if dbus is not None:
        if isinstance(value, (dbus.String, dbus.ObjectPath, dbus.Signature)):
            return str(value)
        if isinstance(value, dbus.Boolean):
            return bool(value)
        if isinstance(value, (dbus.Int16, dbus.Int32, dbus.Int64, dbus.UInt16, dbus.UInt32, dbus.UInt64, dbus.Byte)):
            return int(value)
        if isinstance(value, dbus.Double):
            return float(value)
        if isinstance(value, (dbus.Array, list, tuple)):
            return [_plain(item) for item in value]
        if isinstance(value, dict):
            return {str(_plain(key)): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def measure_atspi_transport() -> dict[str, Any]:
    """Probe AT-SPI reachability. Does not invent a desktop."""

    evidence: dict[str, Any] = {
        "pyatspi": _pyatspi is not None,
        "gi_atspi": _Atspi is not None,
        "dbus_python": dbus is not None,
        "session_bus": False,
        "session_bus_error": "",
        "a11y_bus_name": False,
        "a11y_address": "",
        "a11y_bus": False,
        "registry": False,
        "is_enabled": None,
        "root_role": "",
        "child_count": None,
        "display": os.environ.get("DISPLAY") or "",
        "wayland": os.environ.get("WAYLAND_DISPLAY") or "",
        "at_spi_bus_env": os.environ.get("AT_SPI_BUS") or "",
        "dbus_session_env": os.environ.get("DBUS_SESSION_BUS_ADDRESS") or "",
    }
    if dbus is None:
        evidence["session_bus_error"] = "dbus-python is not importable"
        return evidence
    try:
        session = dbus.SessionBus()
        evidence["session_bus"] = True
    except Exception as exc:
        evidence["session_bus_error"] = f"{type(exc).__name__}: {exc}"
        return evidence
    try:
        names = [str(name) for name in session.list_names()]
        evidence["a11y_bus_name"] = A11Y_BUS_NAME in names
        bus_obj = session.get_object(A11Y_BUS_NAME, A11Y_BUS_PATH)
        address = str(bus_obj.GetAddress(dbus_interface=A11Y_BUS_IFACE))
        evidence["a11y_address"] = address
        try:
            status = dbus.Interface(bus_obj, DBUS_PROPERTIES)
            evidence["is_enabled"] = bool(status.Get(A11Y_STATUS_IFACE, "IsEnabled"))
        except Exception as exc:
            evidence["is_enabled_error"] = f"{type(exc).__name__}: {exc}"
        a11y = dbus_bus.BusConnection(address)
        evidence["a11y_bus"] = True
        a11y_names = [str(name) for name in a11y.list_names()]
        evidence["registry"] = ATSPI_REGISTRY in a11y_names
        if evidence["registry"]:
            root = a11y.get_object(ATSPI_REGISTRY, ATSPI_ROOT_PATH)
            acc = dbus.Interface(root, ATSPI_ACCESSIBLE)
            props = dbus.Interface(root, DBUS_PROPERTIES)
            evidence["root_role"] = str(acc.GetRoleName())
            evidence["child_count"] = int(props.Get(ATSPI_ACCESSIBLE, "ChildCount"))
        a11y.close()
    except Exception as extra:
        evidence["a11y_error"] = f"{type(extra).__name__}: {extra}"
    return evidence


def node_id(bus_name: str, path: str) -> str:
    digest = hashlib.sha256(f"{bus_name}|{path}".encode("utf-8")).hexdigest()
    return "l_" + digest[:20]


def state_names(flags: list[Any]) -> list[str]:
    packed = 0
    for index, part in enumerate(list(flags)[:2]):
        packed |= int(part) << (32 * index)
    names = [name for bit, name in STATE_BITS.items() if packed & (1 << bit)]
    if "showing" not in names and "visible" not in names:
        names.append("offscreen")
    return sorted(set(names))


def compositor_capture(
    path: str | Path,
    bounds: Mapping[str, Any] | None = None,
    *,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compositor/screenshot pixels only. Never the observe/act path."""

    locate = which or shutil.which
    execute = run or subprocess.run
    env = dict(environ or os.environ)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    display = env.get("DISPLAY") or ""
    wayland = env.get("WAYLAND_DISPLAY") or ""
    probes: list[str] = []
    geometry = None
    if bounds and all(key in bounds for key in ("x", "y", "width", "height")):
        geometry = (
            int(bounds["x"]),
            int(bounds["y"]),
            max(1, int(bounds["width"])),
            max(1, int(bounds["height"])),
        )

    grim = locate("grim")
    probes.append(f"grim={grim or 'missing'}")
    if grim and wayland:
        command = [grim, "-t", "png"]
        if geometry:
            x, y, width, height = geometry
            command.extend(["-g", f"{x},{y} {width}x{height}"])
        command.append(str(output))
        completed = execute(command, check=False, capture_output=True, text=True, env=dict(env))
        if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
            return _capture_receipt(output, "grim")
        probes.append(f"grim_rc={completed.returncode}")

    for name in ("gnome-screenshot", "scrot", "maim", "xfce4-screenshooter"):
        tool = locate(name)
        probes.append(f"{name}={tool or 'missing'}")
        if not tool or not display:
            continue
        if name == "gnome-screenshot":
            command = [tool, "-f", str(output)]
        elif name == "xfce4-screenshooter":
            command = [tool, "-f", str(output)]
        else:
            command = [tool, str(output)]
        completed = execute(command, check=False, capture_output=True, text=True, env=dict(env))
        if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
            return _capture_receipt(output, name)
        probes.append(f"{name}_rc={completed.returncode}")

    ffmpeg = locate("ffmpeg")
    probes.append(f"ffmpeg={ffmpeg or 'missing'}")
    if ffmpeg and display:
        width, height, origin_x, origin_y = _display_geometry(display, geometry, locate, execute, env)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "x11grab",
            "-video_size",
            f"{width}x{height}",
            "-i",
            f"{display}+{origin_x},{origin_y}",
            "-update",
            "1",
            "-frames:v",
            "1",
            str(output),
        ]
        completed = execute(command, check=False, capture_output=True, text=True, env=dict(env))
        if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
            return _capture_receipt(output, "ffmpeg-x11grab", width=width, height=height)
        probes.append(f"ffmpeg_rc={completed.returncode} stderr={(completed.stderr or '')[:240]}")

    raise LinuxBackendError(
        "PIXEL_UNSUPPORTED",
        "no compositor capture tool produced a PNG; pixels exist only on explicit capture",
        probes=probes,
        display=display,
        wayland=wayland,
        path=str(output),
    )


def _display_geometry(
    display: str,
    bounds: tuple[int, int, int, int] | None,
    locate: Callable[[str], str | None],
    execute: Callable[..., subprocess.CompletedProcess[str]],
    env: Mapping[str, str],
) -> tuple[int, int, int, int]:
    if bounds:
        return bounds[2], bounds[3], bounds[0], bounds[1]
    xdotool = locate("xdotool")
    if xdotool:
        completed = execute(
            [xdotool, "getdisplaygeometry"],
            check=False,
            capture_output=True,
            text=True,
            env=dict(env),
        )
        parts = (completed.stdout or "").split()
        if completed.returncode == 0 and len(parts) >= 2:
            return max(1, int(parts[0])), max(1, int(parts[1])), 0, 0
    del display
    return 1024, 768, 0, 0


def _capture_receipt(path: Path, method: str, **extra: Any) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "ok": True,
        "protocol": PROTOCOL_VERSION,
        "kind": "pixel_capture",
        "platform": "linux",
        "pixel_ref": str(path),
        "sha256": digest,
        "method": method,
        "bytes": path.stat().st_size,
    }
    result.update(extra)
    return result


class DbusAtspiBackend:
    """Thin dbus-python AT-SPI2 client. pyatspi/GI Atspi are optional extras."""

    def __init__(
        self,
        evidence: Mapping[str, Any] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        capture: Callable[..., dict[str, Any]] | None = None,
        session: Any | None = None,
        a11y: Any | None = None,
    ) -> None:
        if dbus is None or dbus_bus is None:
            raise LinuxBackendError(
                "TRANSPORT_UNCONFIGURED",
                "dbus-python is not importable; AT-SPI is reached over D-Bus",
                **measure_atspi_transport(),
            )
        self._run = runner or subprocess.run
        self._capture = capture or compositor_capture
        self._elements: dict[str, tuple[str, str]] = {}
        self._nodes: dict[str, dict[str, Any]] = {}
        if session is not None and a11y is not None:
            self.session = session
            self.a11y = a11y
            self.evidence = dict(evidence or {})
            return
        self.evidence = dict(evidence or measure_atspi_transport())
        try:
            self.session = dbus.SessionBus()
            bus_obj = self.session.get_object(A11Y_BUS_NAME, A11Y_BUS_PATH)
            address = str(bus_obj.GetAddress(dbus_interface=A11Y_BUS_IFACE))
            self.evidence["a11y_address"] = address
            try:
                status = dbus.Interface(bus_obj, DBUS_PROPERTIES)
                # Enabling the a11y flag is AT-SPI transport, not an auth gate.
                if not bool(status.Get(A11Y_STATUS_IFACE, "IsEnabled")):
                    status.Set(A11Y_STATUS_IFACE, "IsEnabled", dbus.Boolean(True, variant_level=1))
                self.evidence["is_enabled"] = bool(status.Get(A11Y_STATUS_IFACE, "IsEnabled"))
            except Exception as exc:
                self.evidence["is_enabled_error"] = f"{type(exc).__name__}: {exc}"
            self.a11y = dbus_bus.BusConnection(address)
            names = [str(name) for name in self.a11y.list_names()]
            if ATSPI_REGISTRY not in names:
                raise LinuxBackendError(
                    "TRANSPORT_UNCONFIGURED",
                    "AT-SPI registry is not on the a11y bus",
                    **self.evidence,
                )
            self.evidence["registry"] = True
            self.evidence["session_bus"] = True
            self.evidence["a11y_bus"] = True
        except LinuxBackendError:
            raise
        except Exception as exc:
            raise LinuxBackendError(
                "TRANSPORT_UNCONFIGURED",
                f"AT-SPI bus is not usable: {type(exc).__name__}: {exc}",
                **self.evidence,
            ) from exc

    def close(self) -> None:
        closer = getattr(self.a11y, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                return

    def _object(self, bus_name: str, path: str) -> Any:
        return self.a11y.get_object(str(bus_name), str(path))

    def _iface(self, bus_name: str, path: str, interface: str) -> Any:
        return dbus.Interface(self._object(bus_name, path), interface)

    def _prop(self, bus_name: str, path: str, interface: str, name: str, default: Any = None) -> Any:
        try:
            props = self._iface(bus_name, path, DBUS_PROPERTIES)
            return _plain(props.Get(interface, name))
        except Exception:
            return default

    def capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "capabilities",
            "platform": "linux",
            "adapter": "at-spi",
            "status": "live",
            "online": True,
            "transport": "dbus-at-spi2",
            "observation": "at-spi-semantic-delta",
            "pixels": PIXELS_ON_DEMAND,
            "actions": list(LINUX_ACTIONS),
            "capture": ["grim", "ffmpeg-x11grab", "scrot", "maim", "gnome-screenshot"],
            "probe": dict(self.evidence),
            "note": "Windows and Android adapters were not reminted. Pixels travel only when op=capture.",
        }

    def snapshot(
        self, *, max_nodes: int, max_depth: int, include_offscreen: bool
    ) -> dict[str, Any]:
        self._elements = {}
        self._nodes = {}
        nodes: list[dict[str, Any]] = []
        queue: list[tuple[str, str, str, int]] = [(ATSPI_REGISTRY, ATSPI_ROOT_PATH, "", 0)]
        seen: set[str] = set()
        truncated = False
        while queue and len(nodes) < max_nodes:
            bus_name, path, parent, depth = queue.pop(0)
            ident = node_id(bus_name, path)
            if ident in seen:
                continue
            seen.add(ident)
            try:
                node = self._read_node(bus_name, path, parent)
            except Exception:
                continue
            offscreen = "offscreen" in node["states"]
            if include_offscreen or not offscreen or depth == 0:
                nodes.append(node)
                self._elements[ident] = (bus_name, path)
                self._nodes[ident] = node
            if depth >= max_depth:
                continue
            try:
                children = _plain(self._iface(bus_name, path, ATSPI_ACCESSIBLE).GetChildren())
            except Exception:
                continue
            if not isinstance(children, list):
                continue
            for child in children:
                if not isinstance(child, list) or len(child) < 2:
                    continue
                if len(nodes) + len(queue) >= max_nodes:
                    truncated = True
                    break
                queue.append((str(child[0]), str(child[1]), ident, depth + 1))
        focus_id = next((node["id"] for node in nodes if "focused" in node["states"]), "")
        return {
            "ok": True,
            "kind": "semantic_snapshot",
            "platform": "linux",
            "adapter": "at-spi",
            "pixels": PIXELS_NOT_CAPTURED,
            "focus_id": focus_id,
            "truncated": truncated or bool(queue),
            "coverage": {
                "returned": len(nodes),
                "pending": len(queue),
                "max_nodes": max_nodes,
                "max_depth": max_depth,
            },
            "nodes": nodes,
        }

    def _read_node(self, bus_name: str, path: str, parent: str) -> dict[str, Any]:
        acc = self._iface(bus_name, path, ATSPI_ACCESSIBLE)
        atspi_role = str(acc.GetRoleName() or "unknown")
        interfaces = [str(item) for item in _plain(acc.GetInterfaces()) or []]
        flags = _plain(acc.GetState()) or []
        states = state_names(flags if isinstance(flags, list) else [])
        name = str(self._prop(bus_name, path, ATSPI_ACCESSIBLE, "Name", "") or "")
        description = str(self._prop(bus_name, path, ATSPI_ACCESSIBLE, "Description", "") or "")
        actions: list[str] = ["focus"] if ATSPI_COMPONENT in interfaces else []
        native_actions: list[str] = []
        if ATSPI_ACTION in interfaces:
            native_actions = self._action_names(bus_name, path)
            actions.extend(["invoke", "click"])
            lowered = {item.lower() for item in native_actions}
            if "toggle" in lowered:
                actions.append("toggle")
            if "expand" in lowered or "open" in lowered:
                actions.append("expand")
            if "collapse" in lowered or "close" in lowered:
                actions.append("collapse")
            if "select" in lowered:
                actions.append("select")
        if ATSPI_EDITABLE in interfaces or ATSPI_TEXT in interfaces:
            actions.extend(["type_text", "set_value"])
        if ATSPI_VALUE in interfaces:
            actions.append("set_value")
        if ATSPI_COMPONENT in interfaces:
            actions.append("click")
        actions = sorted({item for item in actions if item})
        bounds = None
        if ATSPI_COMPONENT in interfaces:
            try:
                extents = _plain(self._iface(bus_name, path, ATSPI_COMPONENT).GetExtents(0))
                if isinstance(extents, list) and len(extents) >= 4:
                    bounds = {
                        "x": int(extents[0]),
                        "y": int(extents[1]),
                        "width": int(extents[2]),
                        "height": int(extents[3]),
                    }
            except Exception:
                bounds = None
        value = ""
        if ATSPI_TEXT in interfaces:
            try:
                value = str(self._iface(bus_name, path, ATSPI_TEXT).GetText(0, -1) or "")
            except Exception:
                value = str(self._prop(bus_name, path, ATSPI_TEXT, "Text", "") or "")
        if not value and ATSPI_VALUE in interfaces:
            current = self._prop(bus_name, path, ATSPI_VALUE, "CurrentValue", "")
            if current not in (None, ""):
                value = str(current)
        ident = node_id(bus_name, path)
        return {
            "id": ident,
            "parent": parent,
            "role": ROLE_MAP.get(atspi_role, atspi_role.replace(" ", "_").title() or "unknown"),
            "atspi_role": atspi_role,
            "name": name,
            "description": description,
            "value": value,
            "bus_name": bus_name,
            "path": path,
            "bounds": bounds,
            "states": states,
            "actions": actions,
            "native_actions": native_actions,
            "interfaces": [item.rsplit(".", 1)[-1] for item in interfaces],
        }

    def _action_names(self, bus_name: str, path: str) -> list[str]:
        names: list[str] = []
        try:
            action = self._iface(bus_name, path, ATSPI_ACTION)
            try:
                packed = _plain(action.GetActions())
                if isinstance(packed, list):
                    for row in packed:
                        if isinstance(row, list) and row:
                            names.append(str(row[0]))
                        elif isinstance(row, str):
                            names.append(row)
            except Exception:
                count = int(self._prop(bus_name, path, ATSPI_ACTION, "NActions", 0) or 0)
                for index in range(count):
                    names.append(str(action.GetName(index)))
        except Exception:
            return names
        return names

    def _need(self, action: Mapping[str, Any]) -> tuple[str, str, str]:
        ident = str(action.get("id") or "")
        if not ident:
            raise ProtocolError(f"{action.get('type') or 'action'} requires id")
        if ident not in self._elements:
            self.snapshot(max_nodes=600, max_depth=8, include_offscreen=True)
        if ident not in self._elements:
            raise LinuxBackendError("ELEMENT_STALE", f"Linux node is no longer present: {ident}", id=ident)
        bus_name, path = self._elements[ident]
        return ident, bus_name, path

    def _do_named_action(self, bus_name: str, path: str, wanted: tuple[str, ...]) -> str | None:
        names = [item.lower() for item in self._action_names(bus_name, path)]
        action = self._iface(bus_name, path, ATSPI_ACTION)
        for index, name in enumerate(names):
            if name in wanted:
                ok = bool(_plain(action.DoAction(index)))
                if not ok:
                    raise LinuxBackendError(
                        "ACTION_FAILED",
                        f"AT-SPI DoAction({name}) returned false",
                        action=name,
                        index=index,
                    )
                return name
        if names:
            ok = bool(_plain(action.DoAction(0)))
            if not ok:
                raise LinuxBackendError("ACTION_FAILED", "AT-SPI DoAction(0) returned false", action=names[0])
            return names[0]
        return None

    def _click_bounds(self, bus_name: str, path: str) -> None:
        extents = _plain(self._iface(bus_name, path, ATSPI_COMPONENT).GetExtents(0))
        if not isinstance(extents, list) or len(extents) < 4:
            raise LinuxBackendError("ACTION_FAILED", "component has no screen extents")
        x = int(extents[0]) + max(1, int(extents[2])) // 2
        y = int(extents[1]) + max(1, int(extents[3])) // 2
        xdotool = shutil.which("xdotool")
        if not xdotool:
            raise LinuxBackendError(
                "COMMAND_FAILED",
                "AT-SPI Action is absent and xdotool is not on PATH for click fallback",
                xdotool=None,
            )
        completed = self._run(
            [xdotool, "mousemove", "--sync", str(x), str(y), "click", "1"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise LinuxBackendError(
                "COMMAND_FAILED",
                (completed.stderr or completed.stdout or "xdotool click failed").strip(),
                returncode=completed.returncode,
            )

    def act(self, action: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if not action_type:
            raise ProtocolError("action.type is required")
        if action_type == "wait":
            milliseconds = int(action.get("milliseconds") or 250)
            seconds = float(action.get("seconds") or milliseconds / 1000.0)
            time.sleep(max(0.0, min(seconds, 60.0)))
            return self._outcome(action_type)
        if action_type == "done":
            return {
                "ok": True,
                "protocol": PROTOCOL_VERSION,
                "kind": "done",
                "platform": "linux",
                "message": str(action.get("message") or ""),
            }
        if action_type == "launch":
            file_name = str(action.get("file") or action.get("command") or "").strip()
            if not file_name:
                raise ProtocolError("launch requires file")
            args = action.get("args") or []
            if not isinstance(args, list):
                raise ProtocolError("launch args must be a list")
            process = subprocess.Popen(
                [file_name, *[str(item) for item in args]],
                start_new_session=True,
            )
            return self._outcome(action_type, process_id=process.pid, file=file_name)
        if action_type == "key":
            key = str(action.get("key") or "").strip()
            if not key:
                raise ProtocolError("key action requires key")
            ident = str(action.get("id") or "")
            if ident:
                _, bus_name, path = self._need(action)
                try:
                    self._iface(bus_name, path, ATSPI_COMPONENT).GrabFocus()
                except Exception:
                    pass
            xdotool = shutil.which("xdotool")
            if not xdotool:
                raise LinuxBackendError("COMMAND_FAILED", "xdotool is not on PATH for key input", xdotool=None)
            completed = self._run(
                [xdotool, "key", "--clearmodifiers", key],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise LinuxBackendError(
                    "COMMAND_FAILED",
                    (completed.stderr or completed.stdout or "xdotool key failed").strip(),
                    returncode=completed.returncode,
                )
            return self._outcome(action_type, key=key)
        ident, bus_name, path = self._need(action)
        interfaces = [str(item) for item in _plain(self._iface(bus_name, path, ATSPI_ACCESSIBLE).GetInterfaces()) or []]
        if action_type == "focus":
            ok = bool(_plain(self._iface(bus_name, path, ATSPI_COMPONENT).GrabFocus()))
            if not ok:
                raise LinuxBackendError("ACTION_FAILED", "GrabFocus returned false", id=ident)
            return self._outcome(action_type, id=ident)
        if action_type in {"set_value", "type_text"}:
            text = str(action.get("value") or action.get("text") or "")
            if ATSPI_EDITABLE in interfaces:
                ok = bool(_plain(self._iface(bus_name, path, ATSPI_EDITABLE).SetTextContents(text)))
                if not ok:
                    raise LinuxBackendError("ACTION_FAILED", "SetTextContents returned false", id=ident)
                return self._outcome(action_type, id=ident)
            if ATSPI_VALUE in interfaces and action_type == "set_value":
                props = self._iface(bus_name, path, DBUS_PROPERTIES)
                props.Set(ATSPI_VALUE, "CurrentValue", dbus.Double(float(text or 0), variant_level=1))
                return self._outcome(action_type, id=ident)
            if ATSPI_COMPONENT in interfaces:
                try:
                    self._iface(bus_name, path, ATSPI_COMPONENT).GrabFocus()
                except Exception:
                    pass
            xdotool = shutil.which("xdotool")
            if not xdotool:
                raise LinuxBackendError(
                    "COMMAND_FAILED",
                    "no AT-SPI text/value iface and xdotool is not on PATH",
                    id=ident,
                )
            completed = self._run(
                [xdotool, "type", "--clearmodifiers", "--", text],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise LinuxBackendError(
                    "COMMAND_FAILED",
                    (completed.stderr or completed.stdout or "xdotool type failed").strip(),
                    returncode=completed.returncode,
                )
            return self._outcome(action_type, id=ident)
        if action_type in ACTION_ALIASES:
            if ATSPI_ACTION in interfaces:
                used = self._do_named_action(bus_name, path, ACTION_ALIASES[action_type])
                return self._outcome(action_type, id=ident, native_action=used)
            if action_type in {"invoke", "click", "toggle", "select"} and ATSPI_COMPONENT in interfaces:
                self._click_bounds(bus_name, path)
                return self._outcome(action_type, id=ident, native_action="xdotool-click")
            raise LinuxBackendError(
                "UNKNOWN_OPERATION",
                f"AT-SPI node has no handler for {action_type}",
                id=ident,
                interfaces=[item.rsplit(".", 1)[-1] for item in interfaces],
            )
        if action_type == "scroll":
            if ATSPI_ACTION in interfaces:
                used = self._do_named_action(bus_name, path, ("scroll", "scroll down", "scroll up"))
                if used:
                    return self._outcome(action_type, id=ident, native_action=used)
            if ATSPI_COMPONENT in interfaces:
                self._click_bounds(bus_name, path)
            delta = int(action.get("delta") or -120)
            key = "Page_Down" if delta < 0 else "Page_Up"
            xdotool = shutil.which("xdotool")
            if not xdotool:
                raise LinuxBackendError("COMMAND_FAILED", "xdotool is not on PATH for scroll", xdotool=None)
            completed = self._run(
                [xdotool, "key", key],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise LinuxBackendError(
                    "COMMAND_FAILED",
                    (completed.stderr or completed.stdout or "xdotool scroll failed").strip(),
                    returncode=completed.returncode,
                )
            return self._outcome(action_type, id=ident)
        raise LinuxBackendError("UNKNOWN_OPERATION", f"linux adapter has no handler for {action_type}")

    def capture(self, request: Mapping[str, Any]) -> dict[str, Any]:
        output = Path(str(request.get("path") or "artifacts/titan-hands/linux.png"))
        bounds = None
        ident = str(request.get("id") or "")
        if ident:
            if ident not in self._elements:
                self.snapshot(max_nodes=600, max_depth=8, include_offscreen=True)
            node = self._nodes.get(ident)
            if node and isinstance(node.get("bounds"), dict):
                bounds = node["bounds"]
        result = self._capture(output, bounds)
        result.setdefault("protocol", PROTOCOL_VERSION)
        result.setdefault("kind", "pixel_capture")
        result.setdefault("platform", "linux")
        if ident:
            result["id"] = ident
        return result

    def _outcome(self, action_type: str, **extra: Any) -> dict[str, Any]:
        result = {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "linux",
            "adapter": "at-spi",
            "action": action_type,
        }
        result.update(extra)
        return result


class UnconfiguredAtspi:
    """Present adapter, absent bus. Typed failure instead of a fake desktop."""

    def __init__(self, error: LinuxBackendError, capture: Callable[..., dict[str, Any]] | None = None) -> None:
        self.error = error
        self._capture = capture or compositor_capture

    def capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "capabilities",
            "platform": "linux",
            "adapter": "at-spi",
            "status": "transport-unconfigured",
            "online": False,
            "transport": "dbus-at-spi2",
            "observation": "at-spi-semantic-delta",
            "pixels": PIXELS_ON_DEMAND,
            "actions": list(LINUX_ACTIONS),
            "probe": dict(self.error.evidence),
            "failure_reason": self.error.reason,
            "message": str(self.error),
            "note": "Linux AT-SPI adapter is implemented. The bus/libraries were not reachable. Windows and Android adapters were not reminted.",
        }

    def snapshot(self, **_kwargs: Any) -> dict[str, Any]:
        raise self.error

    def act(self, action: Mapping[str, Any]) -> dict[str, Any]:
        del action
        raise self.error

    def capture(self, request: Mapping[str, Any]) -> dict[str, Any]:
        output = Path(str(request.get("path") or "artifacts/titan-hands/linux.png"))
        return self._capture(output, None)

    def close(self) -> None:
        return None


class LinuxHandsServer:
    """handle({op}) Linux target. Same DeltaUI contract as Windows/Android."""

    def __init__(
        self,
        backend: AtspiBackend | None = None,
        connect: Callable[[], AtspiBackend] | None = None,
        capture: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.tracker = DeltaTracker()
        self._capture = capture
        if backend is not None:
            self.backend = backend
            return
        try:
            self.backend = (connect or DbusAtspiBackend)()
        except LinuxBackendError as exc:
            self.backend = UnconfiguredAtspi(exc, capture=capture)

    def close(self) -> None:
        closer = getattr(self.backend, "close", None)
        if callable(closer):
            closer()

    def _observe(self, request: Mapping[str, Any]) -> dict[str, Any]:
        raw = self.backend.snapshot(
            max_nodes=int(request.get("max_nodes") or 600),
            max_depth=int(request.get("max_depth") or 8),
            include_offscreen=bool(request.get("include_offscreen", False)),
        )
        if not raw.get("ok"):
            return raw
        return self.tracker.observe(raw)

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise ProtocolError("request must be an object")
            op = str(request.get("op") or "").strip().lower()
            if op == "capabilities":
                result = dict(self.backend.capabilities())
                result.setdefault("protocol", PROTOCOL_VERSION)
                result.setdefault("kind", "capabilities")
                result.setdefault("platform", "linux")
                result.setdefault("adapter", "at-spi")
                return result
            if op == "observe":
                return self._observe(request)
            if op == "reset":
                self.tracker.reset()
                return {"ok": True, "protocol": PROTOCOL_VERSION, "kind": "reset", "platform": "linux"}
            if op == "act":
                action = request.get("action")
                if not isinstance(action, Mapping):
                    raise ProtocolError("act requires an action object")
                result = self.backend.act(action)
                result.setdefault("protocol", PROTOCOL_VERSION)
                if result.get("ok") and request.get("observe_after", True):
                    result["observation"] = self._observe(request)
                return result
            if op == "capture":
                if self._capture is not None:
                    path = str(request.get("path") or "artifacts/titan-hands/linux.png")
                    return self._capture(path, None)
                result = self.backend.capture(request)
                result.setdefault("protocol", PROTOCOL_VERSION)
                result.setdefault("kind", "pixel_capture")
                return result
            return failure("UNKNOWN_OPERATION", f"unknown operation: {op or '<empty>'}")
        except LinuxBackendError as exc:
            return failure(exc.reason, str(exc), **exc.evidence)
        except (ProtocolError, TypeError, ValueError) as exc:
            return failure("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return failure("BACKEND_ERROR", str(exc))
