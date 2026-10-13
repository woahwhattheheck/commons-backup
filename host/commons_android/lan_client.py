"""LAN client for the physical Commons Android Titan Hands host.

The phone APK is the adapter. This forwards the existing one-tool JSON
to http://<phone>:8745/. It does not remint host/titan_hands/android.py
(ADB / headless emulator). Linux AT-SPI stays named-next.

Cite: p/wire-commons-android-apk-20260826-01.md
      p/emissary-titan-hands-unified-runtime-20260826-01.md
      p/grok-titan-android-open-lan-20260828-01.md
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from host.titan_hands_windows.protocol import PROTOCOL_VERSION, failure


DEFAULT_PORT = 8745


class LanAndroidServer:
    """Thin HTTP forwarder. DeltaUI observe/act/capture live on the phone."""

    def __init__(
        self,
        base_url: str | None = None,
        post: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
        pairing: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("TITAN_HANDS_ANDROID_LAN") or "").rstrip("/")
        self._post = post
        # pairing is leftover env accepted and ignored. The host is credential-free.
        self.pairing = (pairing or "").strip()

    def close(self) -> None:
        return None

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        op = str(request.get("op") or "").strip().lower()
        if not self.base_url and self._post is None:
            if op == "capabilities":
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "capabilities",
                    "platform": "android",
                    "transport": "lan",
                    "online": False,
                    "pixels": "on-demand-only",
                    "observation": "accessibility-semantic-delta",
                    "pairing": "none",
                    "note": "set TITAN_HANDS_ANDROID_LAN to the phone URL after Start host",
                }
            return failure(
                "HOST_OFFLINE",
                "set TITAN_HANDS_ANDROID_LAN to the Commons Android host URL",
            )
        try:
            result = dict(self._send(dict(request)))
        except Exception as exc:
            return failure("HOST_OFFLINE", str(exc), transport="lan")
        if op == "capture":
            result = _persist_capture(result, request.get("path"))
        result.setdefault("protocol", PROTOCOL_VERSION)
        result.setdefault("target", "android-lan")
        return result

    def _send(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._post is not None:
            return self._post(self.base_url or "mock://android-lan", request)
        url = self.base_url + "/"
        payload = json.dumps(dict(request), ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CommonsAndroidLan/1",
        }
        http = Request(
            url,
            data=payload,
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(http, timeout=45) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
        except URLError as exc:
            raise RuntimeError(f"android-lan unreachable: {exc.reason}") from exc
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise RuntimeError("android-lan returned a non-object")
        return parsed


def _persist_capture(result: dict[str, Any], path: Any) -> dict[str, Any]:
    encoded = str(result.get("image_png_b64") or result.get("image_b64") or "")
    if not encoded:
        return result
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError:
        return result
    output = Path(str(path or "artifacts/titan-hands/android-lan.png")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    cleaned = dict(result)
    cleaned.pop("image_png_b64", None)
    cleaned.pop("image_b64", None)
    cleaned["pixel_ref"] = str(output)
    cleaned["bytes"] = len(payload)
    cleaned.setdefault("kind", "pixel_capture")
    return cleaned
