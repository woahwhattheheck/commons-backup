"""Canonical deployment wrapper for prospect contact coordination.

Production reads and writes are bound to one protected authority-ref generation.
The wrapper resolves the authority head once, verifies the authority marker and
contact record at that immutable commit, builds the next whole-tree commit, and
advances the authority ref with a non-force fast-forward.  This closes the
per-path Contents-CAS/ref-rewind seam while preserving the lower-level state
machine.  Custom transports remain a test seam only.
"""
from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
import re
import unicodedata
import urllib.parse
from typing import Any, Mapping

from . import lock as core

AUTHORITY_MARKER_PATH = f"{core.AUTHORITY_ROOT}/AUTHORITY.json"
AUTHORITY_MARKER_SCHEMA = "prospect-contact-lock-authority/v1"
EXPECTED_AUTHORITY_MARKER: dict[str, str] = {
    "schema": AUTHORITY_MARKER_SCHEMA,
    "generation": core.AUTHORITY_GENERATION,
    "api_origin": core.CANONICAL_API_ORIGIN,
    "repository": core.CANONICAL_REPOSITORY,
    "branch": core.AUTHORITY_BRANCH,
    "root": core.AUTHORITY_ROOT,
    "authority_digest": core.AUTHORITY_DIGEST,
}

_SIGNAL_PHRASES = (
    "paid", "payment", "bounty", "prize", "invoice", "fee",
    "commission", "award", "purchase order", "retainer",
)
_NEGATIVE_COMP_RE = re.compile(
    r"(?:\b(?:unpaid|gratis|volunteer|free)\b|"
    r"\bpro\s+bono\b|"
    r"\b(?:no|not|without|zero)\s+(?:pay|paid|payment|fee|compensation|bounty|prize|invoice|commission|retainer)\b|"
    r"\b(?:no|not|without)\s+(?:[$€£]\s*[0-9]|[0-9][0-9,.]*\s*(?:usd|eur|gbp|rtc)\b))",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(
    r"(?:[$€£]\s*(?P<lead>[0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"(?P<trail>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:usd|eur|gbp|rtc)\b)",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


def _api_url(path: str, query: str = "") -> str:
    url = f"{core.CANONICAL_API_ORIGIN}/repos/{core.CANONICAL_REPOSITORY}/{path.lstrip('/')}"
    if query:
        url += "?" + query
    core._assert_canonical_url(url)
    return url


def _branch_metadata_url() -> str:
    return _api_url(f"branches/{urllib.parse.quote(core.AUTHORITY_BRANCH, safe='')}")


def _authority_ref_url() -> str:
    ref = urllib.parse.quote(f"heads/{core.AUTHORITY_BRANCH}", safe="/")
    return _api_url(f"git/refs/{ref}")


def _git_commit_url(commit_sha: str) -> str:
    if not _SHA40_RE.fullmatch(commit_sha):
        raise core.ValidationError("authority commit SHA invalid")
    return _api_url(f"git/commits/{commit_sha}")


def _content_url_at(path: str, commit_sha: str) -> str:
    if not _SHA40_RE.fullmatch(commit_sha):
        raise core.ValidationError("authority commit SHA invalid")
    return _api_url(
        f"contents/{urllib.parse.quote(path, safe='/')}",
        urllib.parse.urlencode({"ref": commit_sha}),
    )


def _strict_compensation_category(text: str) -> str:
    if not isinstance(text, str):
        raise core.ValidationError("compensation_path must be text")
    norm = unicodedata.normalize("NFKC", text.strip()).casefold()
    if not norm or len(norm) > 500 or core.CONTROL_RE.search(norm):
        raise core.ValidationError("compensation_path invalid")
    if _NEGATIVE_COMP_RE.search(norm):
        raise core.ValidationError(
            "compensation_path contains explicit free/negative compensation language"
        )

    saw_zero = False
    for match in _AMOUNT_RE.finditer(norm):
        raw = (match.group("lead") or match.group("trail") or "").replace(",", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            continue
        if amount > 0:
            return core._compensation_category(text)
        if amount == 0:
            saw_zero = True
    if saw_zero:
        raise core.ValidationError(
            "compensation_path contains an explicit zero amount without a distinct positive amount"
        )

    tokens = _TOKEN_RE.findall(norm)
    for phrase in _SIGNAL_PHRASES:
        words = phrase.split()
        width = len(words)
        for i in range(0, len(tokens) - width + 1):
            if tokens[i : i + width] == words:
                return core._compensation_category(text)

    raise core.ValidationError(
        "compensation_path must contain a positive amount or an exact non-negated paid/award signal"
    )


class ProspectContactLock(core.ProspectContactLock):
    """Canonical mutation surface over the core state machine.

    Default production transport requires a protected canonical branch and uses
    whole-ref CAS.  Caller-supplied transports remain the pre-existing test seam;
    transactional fakes opt in with ``supports_authority_transactions = True``.
    """

    def __init__(self, token: str, transport: core.Transport | None = None) -> None:
        super().__init__(token, transport)
        self._transactional_authority = transport is None or bool(
            getattr(transport, "supports_authority_transactions", False)
        )
        self._snapshot_head_sha: str | None = None
        self._snapshot_tree_sha: str | None = None
        self._snapshot_target_path: str | None = None
        self._snapshot_blob_sha: str | None = None

    def _request_json(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None = None,
    ) -> tuple[core.Response, Mapping[str, Any]]:
        headers = dict(self._headers)
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = core._canonical_json_bytes(body)
        response = self._transport.request(method, url, headers, payload)
        core._server_time(response.headers)
        parsed: Any = {}
        if response.body:
            parsed = core._parse_json_strict(response.body)
        if not isinstance(parsed, Mapping):
            raise core.ValidationError("GitHub authority response must be an object")
        return response, parsed

    def _verify_legacy_authority_marker(self) -> None:
        """Compatibility for repository-injected fake transports only."""
        path = urllib.parse.quote(AUTHORITY_MARKER_PATH, safe="/")
        url = (
            f"{core.CANONICAL_API_ORIGIN}/repos/{core.CANONICAL_REPOSITORY}/contents/"
            f"{path}?ref={urllib.parse.quote(core.AUTHORITY_BRANCH, safe='')}"
        )
        core._assert_canonical_url(url)
        response = self._transport.request("GET", url, self._headers, None)
        core._server_time(response.headers)
        if response.status != 200:
            raise core.RemoteError(
                "canonical prospect-contact authority marker unavailable; fail closed"
            )
        envelope = core._parse_json_strict(response.body)
        if not isinstance(envelope, Mapping):
            raise core.ValidationError("authority marker envelope invalid")
        blob_sha = envelope.get("sha")
        if not isinstance(blob_sha, str) or not _SHA40_RE.fullmatch(blob_sha):
            raise core.ValidationError("authority marker blob SHA invalid")
        if envelope.get("encoding") != "base64" or not isinstance(envelope.get("content"), str):
            raise core.ValidationError("authority marker encoding invalid")
        try:
            raw = base64.b64decode(envelope["content"], validate=False)
        except Exception as exc:
            raise core.ValidationError("authority marker base64 invalid") from exc
        if core._parse_json_strict(raw) != EXPECTED_AUTHORITY_MARKER:
            raise core.ValidationError("canonical authority marker mismatch")

    def _resolve_authority_snapshot(self) -> tuple[str, str, str]:
        branch_response, branch_doc = self._request_json("GET", _branch_metadata_url())
        if branch_response.status != 200:
            raise core.RemoteError(
                f"canonical authority branch metadata failed with HTTP {branch_response.status}"
            )
        if branch_doc.get("protected") is not True:
            raise core.RemoteError(
                "canonical prospect-contact authority branch is not protected; fail closed"
            )
        branch_commit = branch_doc.get("commit")
        if not isinstance(branch_commit, Mapping):
            raise core.ValidationError("authority branch commit metadata invalid")
        branch_sha = str(branch_commit.get("sha", ""))
        if not _SHA40_RE.fullmatch(branch_sha):
            raise core.ValidationError("authority branch commit metadata invalid")

        ref_response, ref_doc = self._request_json("GET", _authority_ref_url())
        if ref_response.status != 200:
            raise core.RemoteError(
                f"canonical authority ref read failed with HTTP {ref_response.status}"
            )
        obj = ref_doc.get("object")
        if not isinstance(obj, Mapping) or obj.get("type") != "commit":
            raise core.ValidationError("authority ref object invalid")
        head_sha = str(obj.get("sha", ""))
        if not _SHA40_RE.fullmatch(head_sha):
            raise core.ValidationError("authority ref commit SHA invalid")
        if head_sha != branch_sha:
            raise core.ConflictError("authority head moved during protection/ref snapshot")

        commit_response, commit_doc = self._request_json("GET", _git_commit_url(head_sha))
        if commit_response.status != 200:
            raise core.RemoteError(
                f"authority commit read failed with HTTP {commit_response.status}"
            )
        tree = commit_doc.get("tree")
        if not isinstance(tree, Mapping):
            raise core.ValidationError("authority commit tree metadata invalid")
        tree_sha = str(tree.get("sha", ""))
        if not _SHA40_RE.fullmatch(tree_sha):
            raise core.ValidationError("authority tree SHA invalid")
        return head_sha, tree_sha, core._server_time(commit_response.headers)

    def _read_content_at(
        self, path: str, commit_sha: str
    ) -> tuple[Mapping[str, Any] | None, str | None, str]:
        response = self._transport.request(
            "GET", _content_url_at(path, commit_sha), self._headers, None
        )
        server_time = core._server_time(response.headers)
        if response.status == 404:
            return None, None, server_time
        if response.status != 200:
            raise core.RemoteError(
                f"canonical authority content read failed with HTTP {response.status}"
            )
        envelope = core._parse_json_strict(response.body)
        if not isinstance(envelope, Mapping):
            raise core.ValidationError("GitHub content envelope invalid")
        blob_sha = envelope.get("sha")
        if not isinstance(blob_sha, str) or not _SHA40_RE.fullmatch(blob_sha):
            raise core.ValidationError("GitHub content blob SHA invalid")
        if envelope.get("encoding") != "base64" or not isinstance(envelope.get("content"), str):
            raise core.ValidationError("GitHub content encoding invalid")
        try:
            raw = base64.b64decode(envelope["content"], validate=False)
        except Exception as exc:
            raise core.ValidationError("GitHub content base64 invalid") from exc
        parsed = core._parse_json_strict(raw)
        if not isinstance(parsed, Mapping):
            raise core.ValidationError("canonical authority content must be an object")
        return parsed, blob_sha, server_time

    def _verify_authority_marker_at(self, head_sha: str) -> None:
        marker, _, _ = self._read_content_at(AUTHORITY_MARKER_PATH, head_sha)
        if marker is None:
            raise core.RemoteError(
                "canonical prospect-contact authority marker unavailable; fail closed"
            )
        if dict(marker) != EXPECTED_AUTHORITY_MARKER:
            raise core.ValidationError("canonical authority marker mismatch")

    def _get(self, target: core.Target):
        if not self._transactional_authority:
            if hasattr(self._transport, "authority_available"):
                self._verify_legacy_authority_marker()
            return super()._get(target)

        head_sha, tree_sha, server_time = self._resolve_authority_snapshot()
        self._verify_authority_marker_at(head_sha)
        path = core._record_path(target)
        raw_record, blob_sha, record_time = self._read_content_at(path, head_sha)
        self._snapshot_head_sha = head_sha
        self._snapshot_tree_sha = tree_sha
        self._snapshot_target_path = path
        self._snapshot_blob_sha = blob_sha
        if raw_record is None:
            return None, None, record_time or server_time
        return core._validate_record(raw_record, target), blob_sha, record_time or server_time

    def _put(
        self,
        target: core.Target,
        record: Mapping[str, Any],
        current_blob_sha: str | None,
        message: str,
    ) -> tuple[str, str | None]:
        if not self._transactional_authority:
            return super()._put(target, record, current_blob_sha, message)

        head_sha = self._snapshot_head_sha
        tree_sha = self._snapshot_tree_sha
        path = self._snapshot_target_path
        if not head_sha or not tree_sha or path != core._record_path(target):
            raise core.ConflictError("authority snapshot missing; refresh before mutation")
        if current_blob_sha != self._snapshot_blob_sha:
            raise core.ConflictError("authority record snapshot changed before mutation")

        raw_record = core._canonical_json_bytes(record) + b"\n"
        blob_response, blob_doc = self._request_json(
            "POST",
            _api_url("git/blobs"),
            {"content": raw_record.decode("utf-8"), "encoding": "utf-8"},
        )
        if blob_response.status != 201:
            raise core.RemoteError(
                f"authority blob create failed with HTTP {blob_response.status}"
            )
        new_blob_sha = str(blob_doc.get("sha", ""))
        if not _SHA40_RE.fullmatch(new_blob_sha):
            raise core.ValidationError("authority blob create receipt invalid")

        tree_response, tree_doc = self._request_json(
            "POST",
            _api_url("git/trees"),
            {
                "base_tree": tree_sha,
                "tree": [{
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": new_blob_sha,
                }],
            },
        )
        if tree_response.status != 201:
            raise core.RemoteError(
                f"authority tree create failed with HTTP {tree_response.status}"
            )
        new_tree_sha = str(tree_doc.get("sha", ""))
        if not _SHA40_RE.fullmatch(new_tree_sha):
            raise core.ValidationError("authority tree create receipt invalid")

        commit_response, commit_doc = self._request_json(
            "POST",
            _api_url("git/commits"),
            {"message": message, "tree": new_tree_sha, "parents": [head_sha]},
        )
        if commit_response.status != 201:
            raise core.RemoteError(
                f"authority commit create failed with HTTP {commit_response.status}"
            )
        new_commit_sha = str(commit_doc.get("sha", ""))
        if not _SHA40_RE.fullmatch(new_commit_sha):
            raise core.ValidationError("authority commit create receipt invalid")

        ref_response, ref_doc = self._request_json(
            "PATCH",
            _authority_ref_url(),
            {"sha": new_commit_sha, "force": False},
        )
        if ref_response.status in {409, 412, 422}:
            raise core.ConflictError(
                "canonical authority head CAS lost; refresh before any external action"
            )
        if ref_response.status != 200:
            raise core.RemoteError(
                f"canonical authority ref advance failed with HTTP {ref_response.status}"
            )
        obj = ref_doc.get("object")
        if not isinstance(obj, Mapping) or obj.get("sha") != new_commit_sha:
            raise core.ValidationError("authority ref advance receipt invalid")

        verify_record, verify_blob, _ = self._read_content_at(path, new_commit_sha)
        if verify_record is None or dict(verify_record) != dict(record) or verify_blob != new_blob_sha:
            raise core.RemoteError("authority immutable readback mismatch after ref advance")

        self._snapshot_head_sha = new_commit_sha
        self._snapshot_tree_sha = new_tree_sha
        self._snapshot_blob_sha = new_blob_sha
        return new_blob_sha, new_commit_sha

    def arm(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
        message_sha256: str,
        channel: str,
        compensation_path: str,
    ) -> dict[str, Any]:
        _strict_compensation_category(compensation_path)
        return super().arm(
            kind,
            raw_target,
            agent_id=agent_id,
            operation_id=operation_id,
            message_sha256=message_sha256,
            channel=channel,
            compensation_path=compensation_path,
        )

    def finalize_contacted(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
        message_sha256: str,
        channel: str,
        compensation_path: str,
        provider_receipt: str,
    ) -> dict[str, Any]:
        _strict_compensation_category(compensation_path)
        return super().finalize_contacted(
            kind,
            raw_target,
            agent_id=agent_id,
            operation_id=operation_id,
            message_sha256=message_sha256,
            channel=channel,
            compensation_path=compensation_path,
            provider_receipt=provider_receipt,
        )
