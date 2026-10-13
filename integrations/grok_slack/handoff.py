#!/usr/bin/env python3
"""Loopback browser activation for the grok.com Slack connector.

Gemini's DPAPI handoff stays on 127.0.0.1:8780. This Grok surface binds a
separate loopback port (default 127.0.0.1:8789), writes a current-user
encrypted vault (Windows DPAPI, otherwise SHAKE-256 + HMAC bound to the
current user), and never routes Grok tokens into the Gemini bridge, chat,
git, logs, status JSON, or plaintext disk.

Possession of the loopback page is enough. No repository login, account,
or approval gate.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, MutableMapping
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

try:
    import pwd
except ImportError:  # Windows
    pwd = None  # type: ignore[assignment]


SLACK_APP_ID = "A0BTJMFPTT6"
SCHEMA = "commons-grok-slack-handoff/v1"
GEMINI_HANDOFF_BIND = "127.0.0.1:8780"
DEFAULT_HANDOFF_BIND = "127.0.0.1:8789"
DEFAULT_HEALTH_BIND = "127.0.0.1:8788"
VAULT_VAR = "COMMONS_GROK_SLACK_VAULT"
HANDOFF_BIND_VAR = "COMMONS_GROK_SLACK_HANDOFF_BIND"
HEALTH_BIND_VAR = "COMMONS_GROK_SLACK_HEALTH_BIND"
GEMINI_HOME_NAME = ".gemini"
MAGIC = b"CGSVAULT1"
KIND_WIN = b"W"
KIND_POSIX = b"P"
MAX_BODY = 8_192
BOT_PREFIX = "xoxb-"
APP_PREFIX = "xapp-"


class VaultError(RuntimeError):
    """Encrypted vault could not be used. Messages never include secrets."""


def integration_root() -> Path:
    return Path(__file__).resolve().parent


def default_vault_path(env: MutableMapping[str, str] | None = None) -> Path:
    source = env if env is not None else os.environ
    raw = source.get(VAULT_VAR)
    if raw:
        return Path(raw)
    return Path.home() / ".commons" / "grok_slack.vault"


def default_handoff_bind(env: MutableMapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    return source.get(HANDOFF_BIND_VAR) or DEFAULT_HANDOFF_BIND


def gemini_home() -> Path:
    return Path.home() / GEMINI_HOME_NAME


def is_loopback_bind(value: str) -> bool:
    text = (value or "").strip()
    if not text or ":" not in text:
        return False
    host, port_text = text.rsplit(":", 1)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    try:
        port = int(port_text)
    except ValueError:
        return False
    return 0 <= port <= 65535


def parse_loopback_bind(value: str) -> tuple[str, int]:
    text = (value or "").strip()
    if not is_loopback_bind(text):
        raise VaultError("handoff bind must be loopback host:port")
    host, port_text = text.rsplit(":", 1)
    port = int(port_text)
    if port == 8780:
        raise VaultError("refusing Gemini handoff port; Grok uses a separate loopback bind")
    return host, port


def current_user_material() -> bytes:
    uid = os.getuid() if hasattr(os, "getuid") else 0
    name = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if pwd is not None:
        try:
            name = pwd.getpwuid(uid).pw_name
        except (KeyError, AttributeError, OSError):
            pass
    machine = b""
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            machine = path.read_bytes().strip()
            if machine:
                break
        except OSError:
            continue
    return b"|".join(
        (
            b"commons-grok-slack-vault-v1",
            str(uid).encode("ascii"),
            name.encode("utf-8", "replace"),
            machine,
        )
    )


class Protector:
    name = "abstract"

    def protect(self, plaintext: bytes) -> bytes:
        raise NotImplementedError

    def unprotect(self, blob: bytes) -> bytes:
        raise NotImplementedError


class WinDpapiProtector(Protector):
    """Current-user DPAPI. Tokens never sit on disk in plaintext."""

    name = "win_dpapi"

    def protect(self, plaintext: bytes) -> bytes:
        return _crypt_protect_data(plaintext)

    def unprotect(self, blob: bytes) -> bytes:
        return _crypt_unprotect_data(blob)


class PosixUserProtector(Protector):
    """Current-user authenticated stream (SHAKE-256 + HMAC-SHA256).

    Bound to uid/username/machine-id. File mode 0600. Not DPAPI, but the
    ciphertext is useless to another user or host and is never plaintext.
    """

    name = "posix_user"

    def __init__(self, material: bytes | None = None) -> None:
        self.material = material if material is not None else current_user_material()

    def _keys(self, nonce: bytes) -> tuple[bytes, bytes]:
        root = hashlib.sha256(self.material).digest()
        enc_key = hashlib.sha256(root + b"|enc|" + nonce).digest()
        mac_key = hashlib.sha256(root + b"|mac|" + nonce).digest()
        return enc_key, mac_key

    def protect(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(16)
        enc_key, mac_key = self._keys(nonce)
        stream = hashlib.shake_256(enc_key).digest(len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        return nonce + tag + ciphertext

    def unprotect(self, blob: bytes) -> bytes:
        if len(blob) < 48:
            raise VaultError("vault unreadable")
        nonce, tag, ciphertext = blob[:16], blob[16:48], blob[48:]
        enc_key, mac_key = self._keys(nonce)
        expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise VaultError("vault unreadable")
        stream = hashlib.shake_256(enc_key).digest(len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream))


def platform_protector(material: bytes | None = None) -> Protector:
    if sys.platform == "win32" and material is None:
        return WinDpapiProtector()
    return PosixUserProtector(material=material)


def _cdata_from_bytes(data: bytes):
    """Copy ciphertext including embedded NUL bytes.

    DPAPI blobs are binary and routinely contain 0x00. ctypes.create_string_buffer
    plus .value assignment is a C-string path and is not used here, so a vault
    written by the localhost handoff can be unprotect()'d in another process.
    """
    import ctypes

    n = len(data)
    if n <= 0:
        return (ctypes.c_ubyte * 1)(), 0
    buf = (ctypes.c_ubyte * n).from_buffer_copy(data)
    return buf, n


def _bytes_from_cdata(ptr: object, length: int) -> bytes:
    import ctypes

    if ptr is None or length <= 0:
        return b""
    return ctypes.string_at(ptr, length)


def _win_crypt32():
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    return crypt32, kernel32, DATA_BLOB


def _local_free(kernel32: object, pb_data: object) -> None:
    import ctypes

    if not pb_data:
        return
    kernel32.LocalFree(ctypes.cast(pb_data, ctypes.c_void_p))  # type: ignore[union-attr]


def _crypt_protect_data(plaintext: bytes) -> bytes:
    import ctypes

    crypt32, kernel32, DATA_BLOB = _win_crypt32()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    buf, n = _cdata_from_bytes(plaintext)
    inbound = DATA_BLOB(n, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    outbound = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(inbound),
        "commons-grok-slack",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(outbound),
    )
    if not ok:
        raise VaultError("vault protect failed")
    try:
        return _bytes_from_cdata(outbound.pbData, outbound.cbData)
    finally:
        _local_free(kernel32, outbound.pbData)


def _crypt_unprotect_data(blob: bytes) -> bytes:
    """Decrypt a current-user DPAPI blob. Tries UI_FORBIDDEN then flags=0.

    Existing CGSVAULT1W files are left untouched. Never unlinks the vault.
    """
    import ctypes

    crypt32, kernel32, DATA_BLOB = _win_crypt32()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    buf, n = _cdata_from_bytes(blob)
    inbound = DATA_BLOB(n, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    for flags in (CRYPTPROTECT_UI_FORBIDDEN, 0):
        outbound = DATA_BLOB()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(inbound),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(outbound),
        )
        if not ok:
            continue
        try:
            return _bytes_from_cdata(outbound.pbData, outbound.cbData)
        finally:
            _local_free(kernel32, outbound.pbData)
    raise VaultError("vault unreadable")


def protector_for_kind(kind: bytes, *, protector: Protector | None = None) -> Protector:
    if protector is not None:
        return protector
    if kind == KIND_WIN:
        return WinDpapiProtector()
    return PosixUserProtector()



def _looks_like_bot(value: str) -> bool:
    return value.startswith(BOT_PREFIX) and len(value) > len(BOT_PREFIX) + 8


def _looks_like_app(value: str) -> bool:
    return value.startswith(APP_PREFIX) and len(value) > len(APP_PREFIX) + 8


def write_vault(
    path: Path,
    bot_token: str,
    app_token: str,
    *,
    protector: Protector | None = None,
    app_id: str = SLACK_APP_ID,
) -> dict[str, Any]:
    if not _looks_like_bot(bot_token) or not _looks_like_app(app_token):
        raise VaultError("token shape rejected")
    if path.resolve() == gemini_home().resolve() or gemini_home() in path.resolve().parents:
        raise VaultError("refusing Gemini home for Grok vault")
    worker = protector or platform_protector()
    inner = json.dumps(
        {
            "v": 1,
            "slack_app_id": app_id,
            "bot_token": bot_token,
            "app_token": app_token,
            "stored_at": int(time.time()),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    blob = worker.protect(inner)
    if bot_token.encode("utf-8") in blob or app_token.encode("utf-8") in blob:
        raise VaultError("protector returned plaintext")
    kind = KIND_WIN if worker.name == "win_dpapi" else KIND_POSIX
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = MAGIC + kind + blob
    tmp = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(tmp), flags, 0o600)
    try:
        os.write(fd, payload)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    if hasattr(os, "chmod"):
        os.chmod(tmp, 0o600)
    try:
        loaded = read_vault(tmp, protector=worker)
        if not hmac.compare_digest(loaded["bot_token"], bot_token) or not hmac.compare_digest(loaded["app_token"], app_token):
            raise VaultError("vault unreadable")
    except VaultError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        # Existing ciphertext at `path` is left untouched. Never unlink the live vault.
        raise
    os.replace(tmp, path)
    if hasattr(os, "chmod"):
        os.chmod(path, 0o600)
    return {
        "vault": "present",
        "encrypted": True,
        "plaintext_disk": False,
        "protector": worker.name,
        "slack_app_id": app_id,
        "secrets_printed": False,
        "verified": True,
    }


def read_vault(path: Path, *, protector: Protector | None = None) -> dict[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VaultError("vault unreadable") from exc
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 2:
        raise VaultError("vault unreadable")
    kind = raw[len(MAGIC) : len(MAGIC) + 1]
    blob = raw[len(MAGIC) + 1 :]
    worker = protector_for_kind(kind, protector=protector)
    try:
        inner = worker.unprotect(blob)
        payload = json.loads(inner.decode("utf-8"))
    except (VaultError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise VaultError("vault unreadable") from exc
    bot = payload.get("bot_token")
    app = payload.get("app_token")
    if not isinstance(bot, str) or not isinstance(app, str):
        raise VaultError("vault unreadable")
    if not _looks_like_bot(bot) or not _looks_like_app(app):
        raise VaultError("vault unreadable")
    app_id = payload.get("slack_app_id")
    if not isinstance(app_id, str) or not app_id:
        app_id = SLACK_APP_ID
    return {"bot_token": bot, "app_token": app, "slack_app_id": app_id, "protector": worker.name}


def inject_vault_into(
    env: MutableMapping[str, str],
    *,
    vault_path: Path | None = None,
    protector: Protector | None = None,
) -> dict[str, Any]:
    """Fill missing Slack env keys from the vault. Process env wins. No values returned."""
    report: dict[str, Any] = {
        "vault": "missing",
        "keys_set": [],
        "secrets_printed": False,
        "slack_app_id": SLACK_APP_ID,
        "gemini_isolated": True,
    }
    path = vault_path or default_vault_path(env)
    if not path.is_file():
        return report
    report["vault"] = "present"
    try:
        payload = read_vault(path, protector=protector)
    except VaultError:
        report["vault"] = "unreadable"
        return report
    if not env.get("SLACK_BOT_TOKEN") and payload["bot_token"]:
        env["SLACK_BOT_TOKEN"] = payload["bot_token"]
        report["keys_set"].append("SLACK_BOT_TOKEN")
    if not env.get("SLACK_APP_TOKEN") and payload["app_token"]:
        env["SLACK_APP_TOKEN"] = payload["app_token"]
        report["keys_set"].append("SLACK_APP_TOKEN")
    report["slack_app_id"] = payload.get("slack_app_id") or SLACK_APP_ID
    return report


def redacted_status(
    *,
    env: MutableMapping[str, str] | None = None,
    vault_path: Path | None = None,
    protector: Protector | None = None,
    live: bool | None = None,
    health_bind: str = DEFAULT_HEALTH_BIND,
    handoff_bind: str = DEFAULT_HANDOFF_BIND,
    child_state: str = "",
) -> dict[str, Any]:
    source = env if env is not None else os.environ
    path = vault_path or default_vault_path(source)
    vault_state = "missing"
    readable = False
    if path.is_file():
        vault_state = "present"
        try:
            read_vault(path, protector=protector)
            readable = True
        except VaultError:
            vault_state = "unreadable"
    bot = "present" if source.get("SLACK_BOT_TOKEN") or readable else "missing"
    app = "present" if source.get("SLACK_APP_TOKEN") or readable else "missing"
    probed_live = bool(live) if live is not None else False
    state = "SERVING" if probed_live else (
        "VAULT_PRESENT" if readable else (
            "RUNTIME_UNCONFIGURED" if bot == "missing" or app == "missing" else "NOT_READY"
        )
    )
    return {
        "schema": SCHEMA,
        "slack_app_id": SLACK_APP_ID,
        "slack_bot_token": bot,
        "slack_app_token": app,
        "vault": vault_state,
        "vault_encrypted": vault_state in {"present", "unreadable"},
        "plaintext_disk": False,
        "live": probed_live,
        "ready": probed_live and bot == "present" and app == "present",
        "gemini_isolated": True,
        "gemini_handoff_bind": GEMINI_HANDOFF_BIND,
        "handoff_bind": handoff_bind,
        "health_bind": health_bind,
        "final_delivery_owner": "grok_slack_bridge",
        "state": child_state or state,
        "loopback_only": True,
        "auth": "none",
    }


def probe_live(url: str, timeout: float = 2.0) -> bool:
    if not url:
        return False
    try:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "commons-grok-slack-handoff"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("live")) and payload.get("state") == "SERVING"


def background_process_kwargs(platform: str | None = None) -> dict[str, Any]:
    """Return detached, no-console child settings for the bridge process."""
    target = platform or sys.platform
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if target == "win32":
        # CREATE_NO_WINDOW prevents the bridge from allocating a console even
        # when a watchdog or scheduled task starts the handoff repeatedly.
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        startup_factory = getattr(subprocess, "STARTUPINFO", None)
        if startup_factory is not None:
            startupinfo = startup_factory()
            startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001))
            startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
            kwargs["startupinfo"] = startupinfo
    else:
        # Keep a local handoff shutdown from re-parenting the bridge onto the
        # caller's terminal session.
        kwargs["start_new_session"] = True
    return kwargs


PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store">
<title>Commons Grok Slack — local activate</title>
<style>
:root { color-scheme: dark; }
body { margin: 0; font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; background: #111; color: #f4f0e8; }
main { max-width: 40rem; margin: 0 auto; padding: 1.5rem; }
h1 { font-size: 1.35rem; margin: 0 0 0.5rem; }
label { display: block; font-weight: 600; margin: 1rem 0 0.35rem; }
input { width: 100%; box-sizing: border-box; padding: 0.6rem; font: inherit; background: #000; color: #f4f0e8; border: 2px solid #f4f0e8; }
button { margin-top: 1rem; padding: 0.7rem 1.1rem; font: inherit; font-weight: 700; cursor: pointer; background: #f4f0e8; color: #111; border: 0; }
.note, status, pre { color: #d8d2c4; }
pre { white-space: pre-wrap; border: 1px solid #555; padding: 0.75rem; }
.ok { color: #9f6; }
.warn { color: #fc6; }
</style>
</head>
<body>
<main>
<h1>Activate Commons Grok Slack</h1>
<p>Loopback only. App <code>A0BTJMFPTT6</code>. Tokens stay on this machine, encrypted for the current user. They are never shown again, logged, or written as plaintext.</p>
<p class="note">Gemini stays on <code>127.0.0.1:8780</code>. This page does not touch that bridge.</p>
<form id="activate" autocomplete="off">
<label for="bot">Slack bot token</label>
<input id="bot" name="bot_token" type="password" required spellcheck="false">
<label for="app">Slack app token</label>
<input id="app" name="app_token" type="password" required spellcheck="false">
<button type="submit">Activate</button>
</form>
<p id="msg" class="note">Status is redacted. Paste once. Restart keeps the vault.</p>
<pre id="status">loading…</pre>
</main>
<script>
const statusEl = document.getElementById("status");
const msg = document.getElementById("msg");
async function loadStatus() {
  const res = await fetch("/status", { cache: "no-store" });
  const data = await res.json();
  statusEl.textContent = JSON.stringify(data, null, 2);
  return data;
}
document.getElementById("activate").addEventListener("submit", async (event) => {
  event.preventDefault();
  const bot = document.getElementById("bot");
  const app = document.getElementById("app");
  msg.textContent = "Encrypting and starting…";
  const res = await fetch("/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: bot.value, app_token: app.value })
  });
  bot.value = "";
  app.value = "";
  const data = await res.json();
  msg.className = data.ok ? "ok" : "warn";
  msg.textContent = data.ok ? "Vault stored. Tokens not shown. Bridge start requested." : (data.error || "activate failed");
  statusEl.textContent = JSON.stringify(data.status || data, null, 2);
});
loadStatus();
setInterval(loadStatus, 4000);
</script>
</body>
</html>
"""


def _loopback_host_ok(handler: BaseHTTPRequestHandler) -> bool:
    host = (handler.headers.get("Host") or "").split("%", 1)[0]
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


class HandoffApp:
    def __init__(
        self,
        *,
        bind: str = DEFAULT_HANDOFF_BIND,
        vault_path: Path | None = None,
        protector: Protector | None = None,
        starter: Callable[[str, str], None] | None = None,
        live_probe: Callable[[], bool] | None = None,
        health_bind: str = DEFAULT_HEALTH_BIND,
        env: MutableMapping[str, str] | None = None,
    ) -> None:
        self.bind = bind
        self.host, self.port = parse_loopback_bind(bind)
        self.vault_path = vault_path or default_vault_path(env)
        self.protector = protector or platform_protector()
        self.starter = starter
        self.live_probe = live_probe
        self.health_bind = health_bind
        self.env = env if env is not None else os.environ
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.child: subprocess.Popen[bytes] | None = None
        self.child_lock = threading.Lock()
        self.last_child_state = ""

    def status(self) -> dict[str, Any]:
        live = False
        if self.live_probe is not None:
            live = bool(self.live_probe())
        else:
            live = probe_live(f"http://127.0.0.1:{self.health_bind.rsplit(':', 1)[-1]}/health") if ":" in self.health_bind else False
        return redacted_status(
            env=self.env,
            vault_path=self.vault_path,
            protector=self.protector,
            live=live,
            health_bind=self.health_bind,
            handoff_bind=self.bind,
            child_state=self.last_child_state,
        )

    def activate(self, bot_token: str, app_token: str) -> dict[str, Any]:
        write_vault(self.vault_path, bot_token, app_token, protector=self.protector)
        inject_vault_into(self.env, vault_path=self.vault_path, protector=self.protector)
        started = False
        if self.starter is not None:
            self.starter(bot_token, app_token)
            started = True
            self.last_child_state = "START_REQUESTED"
        else:
            started = self.ensure_bridge()
        status = self.status()
        return {
            "ok": True,
            "started": started,
            "slack_bot_token": "present",
            "slack_app_token": "present",
            "slack_app_id": SLACK_APP_ID,
            "plaintext_disk": False,
            "secrets_printed": False,
            "status": status,
        }

    def ensure_bridge(self) -> bool:
        if probe_live(f"http://127.0.0.1:{self.health_bind.rsplit(':', 1)[-1]}/health"):
            self.last_child_state = "SERVING"
            return True
        try:
            payload = read_vault(self.vault_path, protector=self.protector)
        except VaultError:
            self.last_child_state = "RUNTIME_UNCONFIGURED"
            return False
        child_env = os.environ.copy()
        child_env["SLACK_BOT_TOKEN"] = payload["bot_token"]
        child_env["SLACK_APP_TOKEN"] = payload["app_token"]
        cmd = [
            sys.executable,
            str(integration_root() / "bridge.py"),
            "serve",
            "--health-bind",
            self.health_bind,
        ]
        with self.child_lock:
            if self.child is not None and self.child.poll() is None:
                self.last_child_state = "CHILD_RUNNING"
                return True
            self.child = subprocess.Popen(  # noqa: S603
                cmd,
                env=child_env,
                cwd=str(integration_root().parents[1]),
                **background_process_kwargs(),
            )
            self.last_child_state = "CHILD_SPAWNED"
        return True

    def load_and_maybe_start(self) -> None:
        inject_vault_into(self.env, vault_path=self.vault_path, protector=self.protector)
        if not self.vault_path.is_file():
            self.last_child_state = "RUNTIME_UNCONFIGURED"
            return
        if self.starter is not None:
            try:
                payload = read_vault(self.vault_path, protector=self.protector)
                self.starter(payload["bot_token"], payload["app_token"])
                self.last_child_state = "START_REQUESTED"
            except VaultError:
                self.last_child_state = "RUNTIME_UNCONFIGURED"
            return
        try:
            self.ensure_bridge()
        except VaultError:
            self.last_child_state = "RUNTIME_UNCONFIGURED"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        app = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner_self) -> None:  # type: ignore[no-untyped-def]
                if not _loopback_host_ok(inner_self):
                    inner_self.send_response(404)
                    inner_self.end_headers()
                    return
                path = inner_self.path.split("?", 1)[0]
                if path in {"/", "/index.html", "/activate"}:
                    body = PAGE_HTML.encode("utf-8")
                    inner_self.send_response(200)
                    inner_self.send_header("Content-Type", "text/html; charset=utf-8")
                    inner_self.send_header("Cache-Control", "no-store")
                    inner_self.send_header("Content-Length", str(len(body)))
                    inner_self.end_headers()
                    inner_self.wfile.write(body)
                    return
                if path in {"/status", "/health"}:
                    payload = app.status()
                    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
                    inner_self.send_response(200)
                    inner_self.send_header("Content-Type", "application/json; charset=utf-8")
                    inner_self.send_header("Cache-Control", "no-store")
                    inner_self.send_header("Content-Length", str(len(blob)))
                    inner_self.end_headers()
                    inner_self.wfile.write(blob)
                    return
                inner_self.send_response(404)
                inner_self.end_headers()

            def do_POST(inner_self) -> None:  # type: ignore[no-untyped-def]
                if not _loopback_host_ok(inner_self):
                    inner_self.send_response(404)
                    inner_self.end_headers()
                    return
                path = inner_self.path.split("?", 1)[0]
                if path != "/activate":
                    inner_self.send_response(404)
                    inner_self.end_headers()
                    return
                length = int(inner_self.headers.get("Content-Length") or "0")
                if length <= 0 or length > MAX_BODY:
                    inner_self._json(400, {"ok": False, "error": "body rejected"})
                    return
                raw = inner_self.rfile.read(length)
                bot = ""
                app_token = ""
                ctype = (inner_self.headers.get("Content-Type") or "").split(";", 1)[0].strip()
                try:
                    if ctype == "application/json":
                        parsed = json.loads(raw.decode("utf-8"))
                        bot = str(parsed.get("bot_token") or "")
                        app_token = str(parsed.get("app_token") or "")
                    else:
                        fields = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                        bot = (fields.get("bot_token") or [""])[0]
                        app_token = (fields.get("app_token") or [""])[0]
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    inner_self._json(400, {"ok": False, "error": "body rejected"})
                    return
                try:
                    result = app.activate(bot, app_token)
                except VaultError as exc:
                    inner_self._json(400, {"ok": False, "error": str(exc), "status": app.status()})
                    return
                finally:
                    bot = ""
                    app_token = ""
                inner_self._json(200, result)

            def _json(inner_self, code: int, payload: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
                blob = json.dumps(payload, sort_keys=True).encode("utf-8")
                inner_self.send_response(code)
                inner_self.send_header("Content-Type", "application/json; charset=utf-8")
                inner_self.send_header("Cache-Control", "no-store")
                inner_self.send_header("Content-Length", str(len(blob)))
                inner_self.end_headers()
                inner_self.wfile.write(blob)

            def log_message(inner_self, _format: str, *_args: Any) -> None:  # type: ignore[no-untyped-def]
                return

        return Handler

    def start(self) -> str:
        self.server = ThreadingHTTPServer((self.host, self.port), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, name="grok-slack-handoff", daemon=True)
        self.thread.start()
        return self.url

    @property
    def url(self) -> str:
        if self.server is None:
            return f"http://{self.host}:{self.port}/"
        host, port = self.server.server_address[:2]
        display = "127.0.0.1" if host in {"0.0.0.0", "", "::"} else str(host)
        return f"http://{display}:{port}/"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        with self.child_lock:
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()


def serve_handoff(args: argparse.Namespace) -> int:
    bind = str(getattr(args, "handoff_bind", None) or default_handoff_bind())
    app = HandoffApp(
        bind=bind,
        vault_path=Path(args.vault) if getattr(args, "vault", None) else default_vault_path(),
        health_bind=str(getattr(args, "health_bind", None) or os.environ.get(HEALTH_BIND_VAR) or DEFAULT_HEALTH_BIND),
    )
    app.load_and_maybe_start()
    url = app.start()
    print(json.dumps({
        "ok": True,
        "url": url,
        "slack_app_id": SLACK_APP_ID,
        "gemini_handoff_bind": GEMINI_HANDOFF_BIND,
        "state": app.status()["state"],
        "secrets_printed": False,
    }, sort_keys=True))
    if getattr(args, "open_browser", False):
        webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return 0
    finally:
        app.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "status"), nargs="?", default="serve")
    parser.add_argument("--handoff-bind", default=None, help="loopback host:port, default 127.0.0.1:8789")
    parser.add_argument("--health-bind", default=None)
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--open-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print(json.dumps(redacted_status(
            vault_path=args.vault,
            handoff_bind=args.handoff_bind or default_handoff_bind(),
            health_bind=args.health_bind or DEFAULT_HEALTH_BIND,
        ), indent=2, sort_keys=True))
        return 0
    return serve_handoff(args)


if __name__ == "__main__":
    raise SystemExit(main())
