"""Target router for the local TITAN Hands adapters."""

from __future__ import annotations

import os
from typing import Any, Callable, Mapping, Protocol

from host.titan_hands_windows.protocol import PROTOCOL_VERSION, ProtocolError, failure
from host.titan_hands_windows.server import TitanHandsServer as WindowsHandsServer

from .android import AndroidHandsServer


class HandsServer(Protocol):
    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


class TitanHandsBroker:
    """One stable model-facing surface for Windows and Android hands."""

    def __init__(
        self,
        factories: Mapping[str, Callable[[], HandsServer]] | None = None,
        default_target: str | None = None,
    ) -> None:
        self.factories = dict(
            factories
            or {
                "windows": WindowsHandsServer,
                "android": AndroidHandsServer,
            }
        )
        self.default_target = (
            default_target or os.environ.get("TITAN_HANDS_DEFAULT_TARGET") or "windows"
        ).strip().lower()
        self._servers: dict[str, HandsServer] = {}

    def close(self) -> None:
        for server in self._servers.values():
            server.close()
        self._servers.clear()

    def _server(self, target: str) -> HandsServer:
        target = target.strip().lower()
        if target not in self.factories:
            raise ProtocolError(f"unknown TITAN Hands target: {target}")
        if target not in self._servers:
            self._servers[target] = self.factories[target]()
        return self._servers[target]

    def _capability(self, target: str) -> dict[str, Any]:
        try:
            result = self._server(target).handle({"op": "capabilities"})
            return {"target": target, **result}
        except Exception as exc:
            return {
                "target": target,
                "ok": False,
                "protocol": PROTOCOL_VERSION,
                "kind": "failure",
                "failure_reason": "TARGET_UNAVAILABLE",
                "message": str(exc),
            }

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise ProtocolError("request must be an object")
            op = str(request.get("op") or "").strip().lower()
            target_value = request.get("target")
            if op == "targets" or (op == "capabilities" and not target_value):
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "target_catalog",
                    "default_target": self.default_target,
                    "targets": [self._capability(target) for target in sorted(self.factories)],
                }
            target = str(target_value or self.default_target).strip().lower()
            forwarded = dict(request)
            forwarded.pop("target", None)
            result = self._server(target).handle(forwarded)
            result.setdefault("target", target)
            return result
        except ProtocolError as exc:
            return failure("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return failure("BACKEND_ERROR", str(exc))
