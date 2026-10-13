"""Direct credential delivery: existing custody -> recipient-only ciphertext.

The delivery key is encryption, not caller identity. Any newcomer can request
the same references. No new vault, credential mint, or holder-session grant.
Only this module's local API returns plaintext; equipment calls return sealed
envelopes or constant errors before reaching the ordinary result journal.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import math
import os
import subprocess
import sys
import urllib.parse
from functools import lru_cache
from pathlib import Path


VERSION = "commons.credential-transfer.v1"
ALGORITHM = "X25519-HKDF-SHA256-AES256GCM"
CONTEXT_FIELDS = ("credential_ref", "transfer_id", "request_id", "call_id", "recipient_public_key")
HEADER_FIELDS = ("version", "algorithm", *CONTEXT_FIELDS, "ephemeral_public_key", "nonce")
CRYPTO_HELP = (
    "credential_crypto_unavailable: use a Python runtime with cryptography, "
    "or set COMMONS_CREDENTIAL_CRYPTO_PATH to its existing site-packages; "
    "see integrations/shared_equipment/requirements-credential-transfer.txt"
)


class CredentialTransferError(RuntimeError):
    """Messages are constant codes; never include provider output or values."""


@lru_cache(maxsize=1)
def crypto():
    """Lazy dependency: discovery and existing service tools need no crypto.

    The owner PC already bundles cryptography. An operator-set package path is
    deployment configuration, never a request argument. No package is installed.
    """
    paths = []
    configured = os.environ.get("COMMONS_CREDENTIAL_CRYPTO_PATH")
    if configured:
        paths.append(Path(configured))
    if sys.platform == "win32":
        paths.append(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages")
    added = []
    try:
        if importlib.util.find_spec("cryptography") is None:
            for path in paths:
                if (path / "cryptography/__init__.py").is_file() and str(path) not in sys.path:
                    sys.path.append(str(path))
                    added.append(str(path))
                    break
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        return X25519PrivateKey, X25519PublicKey, AESGCM, HKDF, hashes, serialization
    except Exception:
        raise CredentialTransferError(CRYPTO_HELP) from None
    finally:
        for path in added:
            sys.path.remove(path)


def public_hex(private_key) -> str:
    serialization = crypto()[5]
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hex(value, size: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid encoded bytes")
    raw = bytes.fromhex(value)
    if size is not None and len(raw) != size:
        raise ValueError("invalid byte length")
    return raw


def _context(request: dict) -> dict:
    result = {field: request[field] for field in CONTEXT_FIELDS}
    for field, value in result.items():
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError("invalid transfer context")
    _hex(result["recipient_public_key"], 32)
    return result


def _derive(private_key, peer_key, header: dict) -> bytes:
    _, _, _, HKDF, hashes, _ = crypto()
    # Protocol/version, recipient, request, source ref, ephemeral key, and nonce
    # bind both key derivation and AEAD associated data to this exact envelope.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=VERSION.encode("ascii") + b"\x00" + _json(header)).derive(private_key.exchange(peer_key))


def prepare_recipient(request: dict):
    """Validate encryption capability before any custody read."""
    _, PublicKey, _, _, _, _ = crypto()
    try:
        context = _context(request)
        public = PublicKey.from_public_bytes(_hex(context["recipient_public_key"], 32))
        # exchange rejects low-order/null keys before retrieving a credential.
        crypto()[0].generate().exchange(public)
        return context, public
    except Exception:
        raise CredentialTransferError("invalid_credential_delivery_request") from None


def seal_credential(request: dict, value) -> dict:
    """Reusable sender API for a credential already held in runtime memory.

    Returns only ciphertext. It does not persist or print the supplied value.
    Python does not guarantee erasure of immutable memory after function return.
    """
    context, recipient = prepare_recipient(request)
    try:
        PrivateKey, _, AESGCM, _, _, _ = crypto()
        ephemeral = PrivateKey.generate()
        header = {"version": VERSION, "algorithm": ALGORITHM, **context,
                  "ephemeral_public_key": public_hex(ephemeral), "nonce": os.urandom(12).hex()}
        clear = _json({"credential_ref": context["credential_ref"], "value": value})
        sealed = AESGCM(_derive(ephemeral, recipient, header)).encrypt(
            bytes.fromhex(header["nonce"]), clear, _json(header))
        return {**header, "ciphertext": sealed.hex()}
    except Exception:
        raise CredentialTransferError("credential_sealing_failed") from None


def open_credential(envelope: dict, private_key, expected: dict):
    """Decrypt in recipient memory, comparing against original request context."""
    crypto()
    try:
        context = _context(expected)
        if context["recipient_public_key"] != public_hex(private_key):
            raise ValueError("recipient mismatch")
        header = {field: envelope[field] for field in HEADER_FIELDS}
        if header["version"] != VERSION or header["algorithm"] != ALGORITHM:
            raise ValueError("protocol mismatch")
        if any(header[field] != context[field] for field in CONTEXT_FIELDS):
            raise ValueError("context mismatch")
        _, PublicKey, AESGCM, _, _, _ = crypto()
        sender = PublicKey.from_public_bytes(_hex(header["ephemeral_public_key"], 32))
        clear = AESGCM(_derive(private_key, sender, header)).decrypt(
            _hex(header["nonce"], 12), _hex(envelope["ciphertext"]), _json(header))
        payload = json.loads(clear)
        if payload["credential_ref"] != context["credential_ref"]:
            raise ValueError("source mismatch")
        return payload["value"]
    except Exception:
        raise CredentialTransferError("credential_delivery_invalid") from None


BOX_SECRET_PATHS = (
    "/home/box/agent-data/box-secrets.json",
    "/home/box/sand-data/box-secrets.json",
)
BOX_MANIFEST_KEY = "COMMONS_SHARED_VAULT_MANIFEST"


REFERENCES = (
    {"credential_ref": "slack/bot", "service": "slack", "source": "existing_grok_slack_vault.bot_token", "value_type": "string"},
    {"credential_ref": "slack/app", "service": "slack", "source": "existing_grok_slack_vault.app_token", "value_type": "string"},
    {"credential_ref": "github/token", "service": "github", "source": "gh auth token --hostname github.com", "value_type": "string"},
    {"credential_ref": "gemini/profile", "service": "gemini", "source": "gemini:antigravity via existing read_profile", "value_type": "object"},
    {"credential_ref": "gemini/access", "service": "gemini", "source": "existing read_profile.token.access_token", "value_type": "string"},
    {"credential_ref": "gemini/refresh", "service": "gemini", "source": "existing read_profile.token.refresh_token", "value_type": "string"},
)


def credential_references(sources=None) -> dict:
    """Discovery returns references only, including available/empty Claude entries."""
    return (sources or CredentialSources()).describe()


class CredentialSources:
    """Existing custody readers; use read() locally for direct in-memory access."""
    def __init__(self, *, gh="gh", gh_runner=None, slack_reader=None, gemini_reader=None,
                 config_path=None, claude_path=None, readers=None, box_paths=None):
        self.gh = gh
        self.gh_runner = gh_runner or subprocess.run
        self.slack_reader = slack_reader
        self.gemini_reader = gemini_reader
        self.config_path = Path(config_path or Path.home() / ".commons/credential_sources.json")
        self.claude_path = Path(claude_path or Path.home() / ".claude/.credentials.json")
        self.readers = dict(readers or {})
        self.box_paths = tuple(Path(path) for path in (BOX_SECRET_PATHS if box_paths is None else box_paths))

    def register(self, reference: str, reader) -> None:
        """Extend an existing runtime with another in-memory custody reader."""
        self.readers[reference] = reader

    def _configured(self) -> dict:
        if not self.config_path.exists():
            return {}
        value = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(value.get("sources"), dict):
            raise ValueError()
        return value["sources"]

    def _box_sources(self) -> dict:
        """Read the existing provider snapshot; no config, environment injection, or writes."""
        def strict_json(text):
            def invalid_constant(_value):
                raise ValueError()
            def finite_float(value):
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError()
                return number
            return json.loads(text, parse_constant=invalid_constant, parse_float=finite_float)

        for path in self.box_paths:
            try:
                text = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            stored = strict_json(text)
            if not isinstance(stored, dict) or not isinstance(stored.get("secrets"), dict):
                raise ValueError()
            secrets = stored["secrets"]
            if BOX_MANIFEST_KEY not in secrets:
                return {}
            manifest = strict_json(secrets[BOX_MANIFEST_KEY])
            if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
                raise ValueError()
            if manifest.get("format") != "concatenated-json":
                raise ValueError()
            parts, count = manifest.get("parts"), manifest.get("source_count")
            if not isinstance(parts, list) or not parts or any(not isinstance(part, str) or not part for part in parts):
                raise ValueError()
            if len(set(parts)) != len(parts) or type(count) is not int or count < 0:
                raise ValueError()
            operation = manifest.get("operation_id")
            if not isinstance(operation, str) or not operation:
                raise ValueError()
            payload = strict_json("".join(secrets[part] for part in parts))
            if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
                raise ValueError()
            if payload.get("operation_id") != operation:
                raise ValueError()
            sources = payload.get("sources")
            if not isinstance(sources, dict) or len(sources) != count:
                raise ValueError()
            for ref, record in sources.items():
                if not isinstance(ref, str) or not ref or not isinstance(record, dict) or "value" not in record:
                    raise ValueError()
                if record.get("encoding") not in ("base64", "native_json"):
                    raise ValueError()
                if record["encoding"] == "base64":
                    if not isinstance(record["value"], str):
                        raise ValueError()
                    base64.b64decode(record["value"], validate=True)
            return sources
        return {}

    def _claude_entries(self) -> dict:
        if not self.claude_path.exists():
            return {}
        value = json.loads(self.claude_path.read_text(encoding="utf-8"))
        result = value.get("mcpOAuth", {})
        if not isinstance(result, dict):
            raise ValueError()
        return result

    def describe(self) -> dict:
        rows = [{**row, "availability": "not_probed"} for row in REFERENCES]
        errors = []
        configured = {}
        try:
            configured = self._configured()
            for ref, descriptor in configured.items():
                rows.append({"credential_ref": ref, "source_type": descriptor["type"], "availability": "not_probed"})
        except Exception:
            errors.append("credential_source_config_unavailable")
        for ref in self.readers:
            rows.append({"credential_ref": ref, "source_type": "registered_runtime_reader", "availability": "not_probed"})
        try:
            for key, entry in self._claude_entries().items():
                if not isinstance(entry, dict):
                    continue
                for suffix, field in (("access", "accessToken"), ("refresh", "refreshToken")):
                    rows.append({"credential_ref": "claude/mcp/" + urllib.parse.quote(key, safe="") + "/" + suffix,
                                 "source_type": "existing_claude_mcp_oauth", "availability": "present" if entry.get(field) else "empty"})
        except Exception:
            errors.append("claude_credential_index_unavailable")
        try:
            for ref, record in self._box_sources().items():
                if ref not in configured and ref not in self.readers:
                    # Reflect the effective source when the box replaces a legacy reader.
                    rows = [row for row in rows if row["credential_ref"] != ref]
                    value = record["value"]
                    rows.append({"credential_ref": ref, "source_type": "existing_grokbot_box_bundle",
                                 "encoding": record["encoding"],
                                 "availability": "empty" if value is None or value == "" or value == {} else "present"})
        except Exception:
            errors.append("credential_box_bundle_unavailable")
        return {"schema": "commons.credential-references.v1", "same_references_for_every_peer": True,
                "references": rows, "errors": errors, "delivery_tool": "credential_retrieve_sealed",
                "envelope_version": VERSION, "config": "~/.commons/credential_sources.json"}

    @staticmethod
    def _gemini_module():
        path = Path.home() / ".gemini/commons_peer_relay.py"
        spec = importlib.util.spec_from_file_location("_commons_existing_gemini_custody", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _select(value, descriptor):
        # JSON Pointer as path selection, never executable code.
        pointer = descriptor.get("pointer", "")
        if pointer:
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise ValueError()
            for part in pointer[1:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
        return value

    def _descriptor_read(self, descriptor: dict):
        kind = descriptor["type"]
        if kind == "json_file":
            value = json.loads(Path(descriptor["path"]).expanduser().read_text(encoding="utf-8"))
        elif kind == "grok_slack_vault":
            from integrations.grok_slack.handoff import read_vault
            value = read_vault(Path(descriptor["path"]).expanduser())
        elif kind == "windows_credential":
            # Reuse existing binary-safe CredReadW declarations and structures.
            # A target may hold text or JSON; no assumption about encrypted files.
            import ctypes
            module = self._gemini_module()
            pointer = ctypes.c_void_p()
            if not module.advapi32.CredReadW(descriptor["target"], 1, 0, ctypes.byref(pointer)):
                raise OSError()
            try:
                credential = ctypes.cast(pointer, ctypes.POINTER(module.CREDENTIAL)).contents
                raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
                if descriptor.get("encoding") == "base64":
                    value = base64.b64encode(raw).decode("ascii")
                else:
                    value = raw.decode("utf-8").rstrip("\x00")
            finally:
                module.advapi32.CredFree(pointer)
            if descriptor.get("format") == "json":
                value = json.loads(value)
        else:
            raise ValueError()
        return self._select(value, descriptor)

    def read(self, reference: str):
        """Return an actual value to the local caller, never a broker result."""
        try:
            value = self._read(reference)
            if value is None or value == "" or value == {}:
                raise ValueError()
            return value
        except Exception:
            raise CredentialTransferError("existing_credential_source_unavailable_or_empty") from None

    def _read(self, reference: str):
        try:
            if reference in self.readers:
                return self.readers[reference]()
            try:
                configured = self._configured()
            except Exception:
                # A broken optional extension must not strand built-in custody.
                # describe() reports the config error without exposing its body.
                configured = {}
            if reference in configured:
                return self._descriptor_read(configured[reference])
            try:
                box = self._box_sources()
            except Exception:
                # An optional unreadable bundle must not strand other existing roads.
                # Discovery reports a constant error without the file contents.
                box = {}
            if reference in box:
                return box[reference]["value"]
            if reference.startswith("claude/mcp/"):
                encoded_key, suffix = reference[len("claude/mcp/"):].rsplit("/", 1)
                field = {"access": "accessToken", "refresh": "refreshToken"}[suffix]
                return self._claude_entries()[urllib.parse.unquote(encoded_key)][field]
            if reference in ("slack/bot", "slack/app"):
                if self.slack_reader is None:
                    from integrations.grok_slack.handoff import default_vault_path, read_vault
                    value = read_vault(default_vault_path())
                else:
                    value = self.slack_reader()
                return value["bot_token" if reference == "slack/bot" else "app_token"]
            if reference == "github/token":
                completed = self.gh_runner([self.gh, "auth", "token", "--hostname", "github.com"],
                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if completed.returncode or not completed.stdout.strip():
                    raise RuntimeError()
                return completed.stdout.strip()
            if reference in ("gemini/profile", "gemini/access", "gemini/refresh"):
                if self.gemini_reader is None:
                    value = self._gemini_module().read_profile()
                else:
                    value = self.gemini_reader()
                if reference == "gemini/profile":
                    return value
                return value["token"]["access_token" if reference == "gemini/access" else "refresh_token"]
        except Exception:
            raise CredentialTransferError("existing_credential_source_unavailable") from None
        raise CredentialTransferError("credential_reference_unavailable")

    def retrieve_sealed(self, request: dict) -> dict:
        # All failures are made nonsecret here, before caller journals/errors.
        prepare_recipient(request)
        try:
            value = self.read(request["credential_ref"])
            return seal_credential(request, value)
        except Exception:
            raise CredentialTransferError("credential_retrieval_failed") from None
