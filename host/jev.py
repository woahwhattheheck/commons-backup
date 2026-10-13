#!/usr/bin/env python3
"""host/jev.py — TypeSafe Jev (System One) client for Commons swarm decisions.

JEV INTEGRATION STATUS: WORKING. Shared-vault live call verified 2026-09-20.

Jev is a decision model, not a chat model: send `state` plus typed
`questions` (choice / score / noul), get typed answers with calibrated
probabilities and confidence in a single parallel call (~70-500 ms,
$0.042 per MTok input, output unmetered). It never generates strings,
so answers are consumed directly by code — no parsing, no guardrails.

  Docs:  https://docs.typesafe.ai/
  API:   POST https://api.typesafe.ai/v1/systemone
  Model: jev-latest

  python3 host/jev.py --questions-file q.json --state-file post.md
  python3 host/jev.py --questions-file q.json --state - < post.md
  python3 host/jev.py --transport hosted --questions-file q.json --state-file post.md

Direct transport is the compatibility default. Hosted transport is explicit,
uses the existing Commons endpoint, and never reads or forwards a local key.
It uses the deployment's jev-latest model; there is no automatic fallback.

Key resolution policy (never printed, never written to the repo):
  1. credvault: Windows Credential Manager generic target
     "commons:typesafe:api-key" then "typesafe/api-key"
     (credential_sources.json naming convention)
  2. env TYPESAFE_API_KEY is a compatibility fallback only when no vaulted
     key exists. If env and vault (or two vault targets) disagree, resolution
     fails closed with KEY_SOURCE_CONFLICT instead of guessing a generation.

NO_KEY is a typed result, not a crash — callers branch on it like any
other answer.
"""
from __future__ import annotations

import argparse
import ctypes
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from ctypes import wintypes

API_URL = "https://api.typesafe.ai/v1/systemone"
HOSTED_URL = "https://commons-spark-mcp.vercel.app/jev"
TRANSPORTS = ("direct", "hosted")
MAX_HOSTED_BODY_BYTES = 256 * 1024
DEFAULT_MODEL = "jev-latest"
ENV_KEY = "TYPESAFE_API_KEY"
CREDVAULT_TARGETS = ("commons:typesafe:api-key", "typesafe/api-key")
QUESTION_TYPES = ("choice", "score", "noul")
QUESTION_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_STATE_BYTES = 256 * 1024
MAX_QUESTIONS = 500


class JevError(Exception):
    """Typed failure, with provider retry delay when a numeric header is supplied."""

    def __init__(self, code: str, *, retry_after_seconds: int | None = None):
        super().__init__(code)
        self.retry_after_seconds = retry_after_seconds


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_CRED_TYPE_GENERIC = 1


def _header_safe_key(value: str) -> bool:
    """Bearer material must be nonempty printable ASCII without whitespace."""
    return isinstance(value, str) and bool(value) and all(
        0x21 <= ord(char) <= 0x7e for char in value
    )


def _decode_credential_blob(blob: bytes) -> str:
    """Decode supported generic-vault formats without guessing a key generation.

    Generic credentials have application-defined bytes. UTF-8 ASCII tokens and
    UTF-16LE tokens are both supported, including trailing NUL terminators.
    Decoding success alone is insufficient: even-length UTF-8 can decode as
    unrelated UTF-16 text. Accept only one unambiguous header-safe value; a
    present empty or malformed record is unreadable, never an absent alias.
    """
    candidates = set()
    for encoding in ("utf-8", "utf-16-le"):
        try:
            value = blob.decode(encoding).rstrip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if _header_safe_key(value):
            candidates.add(value)
    if len(candidates) != 1:
        raise JevError("KEY_SOURCE_UNAVAILABLE") from None
    return candidates.pop()


def _cred_read(target: str) -> str:
    """Read a Windows Credential Manager generic credential. Returns '' on miss."""
    if os.name != "nt" or not target:
        return ""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
    pcred = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        error = ctypes.get_last_error()
        # ERROR_NOT_FOUND means this configured alias is genuinely absent.
        if error == 1168:
            return ""
        raise OSError(error, "CredReadW failed")
    try:
        blob = ctypes.string_at(
            pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize
        )
    finally:
        advapi32.CredFree(pcred)
    return _decode_credential_blob(blob)


def _read_key_sources() -> tuple[str, list[tuple[str, str]]]:
    """Read configured key sources; vault read failures are authority failures."""
    env_key = os.environ.get(ENV_KEY, "").strip()
    if env_key and not _header_safe_key(env_key):
        raise JevError("KEY_SOURCE_UNAVAILABLE") from None
    vault_keys: list[tuple[str, str]] = []
    for target in CREDVAULT_TARGETS:
        try:
            key = _cred_read(target)
        except Exception:
            # Do not reinterpret an unreadable vault as "missing" and fall
            # back to an environment generation we can no longer reconcile.
            raise JevError("KEY_SOURCE_UNAVAILABLE") from None
        if key:
            if not _header_safe_key(key):
                raise JevError("KEY_SOURCE_UNAVAILABLE") from None
            vault_keys.append((target, key))
    return env_key, vault_keys


def _select_key(env_key: str, vault_keys: list[tuple[str, str]]) -> str:
    """Select one credential generation, failing closed on source disagreement."""
    vault_key = vault_keys[0][1] if vault_keys else ""
    if vault_key:
        for _, candidate in vault_keys[1:]:
            if not hmac.compare_digest(vault_key, candidate):
                raise JevError("KEY_SOURCE_CONFLICT")
        if env_key and not hmac.compare_digest(vault_key, env_key):
            raise JevError("KEY_SOURCE_CONFLICT")
        # A vaulted generation is authoritative whenever it exists. If an
        # environment copy also exists it must match byte-for-byte.
        return vault_key
    return env_key


def load_key() -> str:
    """Resolve one TypeSafe API-key generation. Never logs the value."""
    env_key, vault_keys = _read_key_sources()
    return _select_key(env_key, vault_keys)


def key_state() -> str:
    """Report credential source state without exposing credential material."""
    try:
        env_key, vault_keys = _read_key_sources()
        _select_key(env_key, vault_keys)
    except JevError as err:
        if str(err) in {"KEY_SOURCE_CONFLICT", "KEY_SOURCE_UNAVAILABLE"}:
            return str(err)
        raise
    if vault_keys:
        state = "KEY_PRESENT_CREDVAULT:" + vault_keys[0][0]
        if env_key:
            state += "+ENV_MATCH"
        return state
    if env_key:
        return "KEY_PRESENT_ENV"
    return "NO_KEY"


def validate_questions(questions) -> list:
    """Return a list of structural problems; empty list means API-shaped."""
    problems = []
    if not isinstance(questions, dict) or not questions:
        return ["questions must be a non-empty object"]
    if len(questions) > MAX_QUESTIONS:
        problems.append(f"questions exceeds MAX_QUESTIONS={MAX_QUESTIONS}")
    for qkey, q in questions.items():
        if not QUESTION_KEY_RE.match(str(qkey)):
            problems.append(f"bad question key {qkey!r}")
        if not isinstance(q, dict):
            problems.append(f"{qkey}: question must be an object")
            continue
        qtype = q.get("type")
        if qtype not in QUESTION_TYPES:
            problems.append(f"{qkey}: type must be one of {QUESTION_TYPES}")
            continue
        if not str(q.get("instructions") or "").strip():
            problems.append(f"{qkey}: missing instructions")
        criteria = q.get("criteria")
        if qtype == "choice" and not (
            isinstance(criteria, dict) and len(criteria) >= 2
        ):
            problems.append(f"{qkey}: choice needs a criteria object with >=2 options")
        if qtype == "score" and not (
            isinstance(criteria, list) and len(criteria) >= 2
        ):
            problems.append(f"{qkey}: score needs a criteria list with >=2 levels")
    return problems


class _NoHostedRedirect(urllib.request.HTTPRedirectHandler):
    """Do not redirect submitted state away from the selected hosted endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _hosted_error(data, fallback):
    """Expose a bounded error code, never the provider body or submitted state."""
    error = data.get("error") if isinstance(data, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
        return "HOSTED_" + code
    return fallback


def systemone(state, questions, model=DEFAULT_MODEL, timeout=60, key=None,
              *, transport="direct"):
    """One direct or hosted call; no retries, credential forwarding, or fallback.

    Existing calls remain direct, including the hosted server's own provider
    call. Select hosted explicitly for a cloud worker without a local key.
    """
    if transport not in TRANSPORTS:
        raise JevError("BAD_TRANSPORT")
    if not isinstance(state, str) or not state.strip():
        raise JevError("EMPTY_STATE")
    if len(state.encode("utf-8")) > MAX_STATE_BYTES:
        raise JevError("STATE_TOO_LARGE")
    problems = validate_questions(questions)
    if problems:
        raise JevError("BAD_QUESTIONS:" + ";".join(problems[:5]))
    headers = {"Content-Type": "application/json", "User-Agent": "commons-jev/1.0"}
    if transport == "hosted":
        if key is not None:
            raise JevError("HOSTED_KEY_NOT_ACCEPTED")
        # api/jev.py deliberately selects DEFAULT_MODEL server-side.
        if model != DEFAULT_MODEL:
            raise JevError("HOSTED_MODEL_NOT_SUPPORTED")
        url = HOSTED_URL
    else:
        key = key if key is not None else load_key()
        if not key:
            raise JevError("NO_KEY")
        if not _header_safe_key(key):
            raise JevError("BAD_KEY") from None
        headers["Authorization"] = "Bearer " + key
        url = API_URL
    payload = {"state": state, "model": model, "questions": questions}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    # The hosted limit covers questions and JSON framing as well as state.
    if transport == "hosted" and len(body) > MAX_HOSTED_BODY_BYTES:
        raise JevError("HOSTED_BODY_TOO_LARGE")
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    opener = (urllib.request.build_opener(_NoHostedRedirect()).open
              if transport == "hosted" else urllib.request.urlopen)
    try:
        with opener(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as err:
        code = f"HTTP_{err.code}"
        delay = (err.headers.get("Retry-After", "") if err.headers else "").strip()
        retry_after = int(delay) if re.fullmatch(r"[0-9]{1,9}", delay) else None
        with err:
            if transport == "hosted":
                try:
                    code = _hosted_error(json.loads(err.read(4096)), code)
                except (ValueError, OSError):
                    pass
        raise JevError(code, retry_after_seconds=retry_after) from None
    except OSError:
        raise JevError("TRANSPORT") from None
    except ValueError:
        raise JevError("BAD_REPLY") from None
    if transport == "hosted" and (not isinstance(data, dict) or data.get("ok") is not True):
        raise JevError(_hosted_error(data, "HOSTED_BAD_REPLY"))
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise JevError("BAD_REPLY")
    return data


def _read_text_arg(value):
    """'-' reads stdin; '@path' reads a file; otherwise the literal string."""
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TypeSafe Jev System One client")
    parser.add_argument("--state", help="state text, '-' for stdin, '@path' for file")
    parser.add_argument("--state-file", help="file containing the state")
    parser.add_argument("--questions-file", help="JSON file of typed questions")
    parser.add_argument("--questions", help="inline JSON of typed questions")
    parser.add_argument("--transport", choices=TRANSPORTS, default="direct",
                        help="direct uses a local key; hosted uses the Commons server key")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)

    if args.state_file:
        with open(args.state_file, encoding="utf-8", errors="replace") as handle:
            state = handle.read()
    elif args.state is not None:
        state = _read_text_arg(args.state)
    else:
        print("jev: provide --state or --state-file", file=sys.stderr)
        return 2

    qsrc = args.questions or ""
    if args.questions_file:
        with open(args.questions_file, encoding="utf-8", errors="replace") as handle:
            qsrc = handle.read()
    try:
        questions = json.loads(qsrc)
    except ValueError:
        print("jev: questions are not valid JSON", file=sys.stderr)
        return 2

    try:
        result = systemone(state, questions, model=args.model, timeout=args.timeout,
                           transport=args.transport)
    except JevError as err:
        code = str(err)
        out = {"error": code, "transport": args.transport}
        if err.retry_after_seconds is not None:
            out["retry_after_seconds"] = err.retry_after_seconds
        if code == "NO_KEY":
            out["message"] = (
                "Set TYPESAFE_API_KEY or store a Windows generic credential at "
                "'commons:typesafe:api-key', or explicitly select --transport hosted "
                "to use the existing Commons deployment without a local key."
            )
        elif code == "HOSTED_NO_KEY":
            out["message"] = "The Commons deployment has no server key; no local key was read or sent."
        print(json.dumps(out), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
