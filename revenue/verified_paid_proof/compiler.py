"""Fail-closed paid-proof compiler and release-boundary renderer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .core import (
    CompiledProof,
    POLICY_VERSION,
    STATUSES,
    ProofError,
    _canonical_json,
    _money,
    _public_proof_id,
    _redacted_customer_id,
    strict_json_loads,
)
from .validation import validate_and_normalize

SCHEMA_VERSION = 3
PROVENANCE_BLOCKER = "evidence_provenance_unverified"
PUBLIC_RELEASE_STATE = "NO_PUBLIC_CLAIM"
CANDIDATE_WARNING = (
    "UNVERIFIED_CALLER_RECORD: candidate content is private inspection material only; "
    "it is not paid-proof authority and must not be published or treated as verified."
)


def _compile_unverified_candidate(record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate legacy content/permission policy without granting evidence authority."""

    blockers: list[str] = []
    withheld: list[str] = []

    payment_asserted = (
        record["payment"]["status"] == "SETTLED"
        and bool(record["payment"]["evidence_refs"])
    )
    delivery_accepted_asserted = (
        record["delivery"]["status"] == "ACCEPTED"
        and bool(record["delivery"]["evidence_refs"])
    )
    revoked_asserted = record["revocation"]["revoked"]
    p = record["permissions"]

    if not payment_asserted:
        blockers.append("settled_payment_not_asserted")
    if revoked_asserted:
        blockers.append("publication_permission_revoked")

    public_requested = p["public_proof"]["granted"]
    public_payment_allowed = public_requested and p["payment_fact"]["granted"]
    if payment_asserted and not public_requested:
        withheld.append("all_public_projection:no_public_proof_permission")
    elif payment_asserted and public_requested and not p["payment_fact"]["granted"]:
        withheld.append("payment_fact:no_payment_fact_permission")

    if not payment_asserted or revoked_asserted:
        status = "HOLD"
    elif not public_payment_allowed:
        status = "PRIVATE_VERIFIED"
    elif p["customer_identity"]["granted"]:
        status = "PUBLIC_NAMED"
    else:
        status = "PUBLIC_ANONYMOUS"
    if status not in STATUSES:
        raise ProofError("internal candidate status invariant failed")

    public_enabled = status in {"PUBLIC_ANONYMOUS", "PUBLIC_NAMED"}
    named = status == "PUBLIC_NAMED"

    if named:
        customer_label = record["customer"]["display_name"]
    elif public_enabled:
        customer_label = _redacted_customer_id(record["engagement_id"])
        if record["customer"]["display_name"] is not None:
            withheld.append("customer_identity")
    else:
        customer_label = None

    exact_amount: str | None = None
    if public_enabled:
        if p["exact_amount"]["granted"]:
            pay = record["payment"]
            exact_amount = _money(
                pay["amount_minor"],
                pay["currency"],
                pay["currency_decimals"],
            )
        else:
            withheld.append("exact_amount")

    public_delivery = False
    if delivery_accepted_asserted:
        if public_enabled and p["delivery_acceptance"]["granted"]:
            public_delivery = True
        else:
            withheld.append("delivery_acceptance")

    public_quote: str | None = None
    if record["quote"]["text"] is not None:
        if public_enabled and p["quote"]["granted"]:
            public_quote = record["quote"]["text"]
        else:
            withheld.append("quote")

    public_logo_ref: str | None = None
    if record["customer"]["logo_ref"] is not None:
        if public_enabled and named and p["logo"]["granted"]:
            public_logo_ref = record["customer"]["logo_ref"]
        else:
            withheld.append("logo")

    candidate_outcomes: list[dict[str, Any]] = []
    private_outcomes: list[dict[str, Any]] = []
    for outcome in record["outcomes"]:
        private_outcomes.append(
            {"claim": outcome["claim"], "evidence_refs": outcome["evidence_refs"]}
        )
        if public_enabled and outcome["publication_permission"]["granted"]:
            # Even the private candidate keeps source locators out of its would-be public shape.
            candidate_outcomes.append({"claim": outcome["claim"]})
        else:
            # Never echo the claim itself into metadata that might be rendered later.
            withheld.append("outcome_claim")

    permission_refs = {
        scope: p[scope]["evidence_refs"]
        for scope in sorted(p)
        if p[scope]["granted"]
    }

    candidate_projection = {
        "status": status,
        "proof_id": (
            _public_proof_id(record["engagement_id"]) if public_enabled else None
        ),
        "customer": customer_label,
        "paid_engagement": True if public_enabled and payment_asserted else None,
        "exact_amount": exact_amount,
        "delivery_accepted": True if public_delivery else None,
        "quote": public_quote,
        "logo_ref": public_logo_ref,
        "outcomes": candidate_outcomes,
    }

    return {
        "status": status,
        "payment_asserted": payment_asserted,
        "delivery_accepted_asserted": delivery_accepted_asserted,
        "revoked_asserted": revoked_asserted,
        "blockers": sorted(set(blockers)),
        "withheld": sorted(set(withheld)),
        "public_projection": candidate_projection,
        "private_outcomes": private_outcomes,
        "permission_evidence_refs": permission_refs,
    }


def _empty_public_projection() -> dict[str, Any]:
    return {
        "status": "HOLD",
        "proof_id": None,
        "customer": None,
        "paid_engagement": None,
        "exact_amount": None,
        "delivery_accepted": None,
        "quote": None,
        "logo_ref": None,
        "outcomes": [],
    }


def _public_release_without_receipt() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "release_state": PUBLIC_RELEASE_STATE,
        "commercial_claim": None,
        "reason": PROVENANCE_BLOCKER,
    }


def _public_release() -> dict[str, Any]:
    payload = _public_release_without_receipt()
    receipt = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {**payload, "public_receipt_sha256": receipt}


def _render_public_markdown(payload: dict[str, Any]) -> str:
    """Render only the fixed fail-closed public envelope.

    Caller-controlled buyer, payment, outcome, quote, permission, reference, and blocker
    content never enters this renderer.
    """

    expected = _public_release()
    if payload != expected:
        raise ProofError("public release payload failed closed")
    return "\n".join(
        [
            "# Verified Paid Proof",
            "",
            f"**Release state:** `{PUBLIC_RELEASE_STATE}`",
            f"**Policy:** `{POLICY_VERSION}`",
            "",
            "No public paid-work claim is authorized from this record.",
            "Caller-supplied payment, delivery, permission, and evidence references have not "
            "been independently authenticated.",
            "",
            f"**Public receipt:** `{payload['public_receipt_sha256']}`",
            "",
        ]
    )


def _receipt_payload(
    normalized_input: dict[str, Any],
    proof_without_receipt: dict[str, Any],
    public_release: dict[str, Any],
    public_markdown: str,
) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "normalized_input": normalized_input,
        "proof": proof_without_receipt,
        "public_release": public_release,
        "public_markdown": public_markdown,
    }


def compile_proof(raw: dict[str, Any]) -> CompiledProof:
    """Compile a caller record while refusing to certify its provenance."""

    record = validate_and_normalize(raw)
    candidate = _compile_unverified_candidate(record)

    blockers = [PROVENANCE_BLOCKER]
    if not candidate["payment_asserted"]:
        blockers.append("settled_payment_not_verified")
    if candidate["revoked_asserted"]:
        blockers.append("publication_permission_revoked")

    # Top-level withholding is deliberately content-free. Candidate detail remains private.
    withheld = ["all_public_projection:evidence_provenance_unverified"]
    public_projection = _empty_public_projection()
    release = _public_release()
    public_markdown = _render_public_markdown(release)

    private_evidence = {
        "evidence_provenance": {
            "verified": False,
            "reason": PROVENANCE_BLOCKER,
            "authority": None,
        },
        "payment_verified": False,
        "payment_asserted": candidate["payment_asserted"],
        "payment": record["payment"],
        "delivery_accepted": False,
        "delivery_accepted_asserted": candidate["delivery_accepted_asserted"],
        "delivery": record["delivery"],
        "customer": record["customer"],
        "quote": record["quote"],
        "outcomes": candidate["private_outcomes"],
        "permission_evidence_refs": candidate["permission_evidence_refs"],
        "revocation": record["revocation"],
        "normalized_input": record,
        "unverified_candidate": {
            "warning": CANDIDATE_WARNING,
            "status": candidate["status"],
            "blockers": candidate["blockers"],
            "withheld": candidate["withheld"],
            "public_projection": candidate["public_projection"],
        },
    }

    proof_without_receipt = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "status": "HOLD",
        "engagement_id": record["engagement_id"],
        "blockers": sorted(set(blockers)),
        "withheld": withheld,
        "public_projection": public_projection,
        "public_release": release,
        "private_evidence": private_evidence,
    }
    receipt = hashlib.sha256(
        _canonical_json(
            _receipt_payload(
                record,
                proof_without_receipt,
                release,
                public_markdown,
            )
        ).encode("utf-8")
    ).hexdigest()
    proof = dict(proof_without_receipt)
    proof["receipt_sha256"] = receipt
    return CompiledProof(
        proof=proof,
        markdown=public_markdown,
        receipt_sha256=receipt,
    )


def _verify_compiled(compiled: CompiledProof) -> None:
    if type(compiled) is not CompiledProof:
        raise ProofError("public release requires a compiler-produced CompiledProof")

    proof = compiled.proof
    if not isinstance(proof, dict):
        raise ProofError("compiled proof must be an object")
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ProofError("compiled proof schema is not release-authorized")
    if proof.get("policy_version") != POLICY_VERSION:
        raise ProofError("compiled proof policy is not release-authorized")
    if proof.get("status") != "HOLD":
        raise ProofError("compiled proof status invariant failed for raw records")
    if proof.get("public_projection") != _empty_public_projection():
        raise ProofError("compiled public projection must remain empty")
    if PROVENANCE_BLOCKER not in proof.get("blockers", []):
        raise ProofError("compiled proof lost provenance blocker")

    expected_release = _public_release()
    if proof.get("public_release") != expected_release:
        raise ProofError("compiled public release envelope is invalid")
    expected_markdown = _render_public_markdown(expected_release)
    if compiled.markdown != expected_markdown:
        raise ProofError("compiled public markdown is invalid")

    private = proof.get("private_evidence")
    if not isinstance(private, dict):
        raise ProofError("compiled proof lost private evidence envelope")
    record = private.get("normalized_input")
    if not isinstance(record, dict):
        raise ProofError("compiled proof lost normalized input authority")
    renormalized = validate_and_normalize(record)
    if _canonical_json(renormalized) != _canonical_json(record):
        raise ProofError("normalized input no longer validates canonically")

    without_receipt = dict(proof)
    proof_receipt = without_receipt.pop("receipt_sha256", None)
    if proof_receipt != compiled.receipt_sha256:
        raise ProofError("compiled proof receipt fields disagree")
    expected_receipt = hashlib.sha256(
        _canonical_json(
            _receipt_payload(
                record,
                without_receipt,
                expected_release,
                expected_markdown,
            )
        ).encode("utf-8")
    ).hexdigest()
    if expected_receipt != compiled.receipt_sha256:
        raise ProofError("compiled proof receipt verification failed")


def public_payload(compiled: CompiledProof) -> dict[str, Any]:
    """Return the only release-authorized public JSON envelope for raw records."""

    _verify_compiled(compiled)
    # Round-trip gives the caller an independent object rather than a mutable reference
    # into the internal proof envelope.
    return json.loads(_canonical_json(compiled.proof["public_release"]))


def public_json(compiled: CompiledProof) -> str:
    return json.dumps(
        public_payload(compiled),
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def compile_text(text: str) -> CompiledProof:
    return compile_proof(strict_json_loads(text))


def _reject_symlink_ancestry(path: Path) -> None:
    absolute = path.absolute()
    current = absolute.parent
    while True:
        if current.is_symlink():
            raise ProofError(f"output path has symlink ancestor: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def _create_dir_exclusive(path: Path) -> Path:
    absolute = path.absolute()
    _reject_symlink_ancestry(absolute)
    parent = absolute.parent
    if not parent.exists() or not parent.is_dir():
        raise ProofError(f"output parent must already exist and be a directory: {parent}")
    if absolute.exists() or absolute.is_symlink():
        raise ProofError(f"output directory already exists: {absolute}")
    try:
        os.mkdir(absolute, 0o700)
    except FileExistsError as exc:
        raise ProofError(f"output directory already exists: {absolute}") from exc
    return absolute


def _write_new_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def write_outputs(
    compiled: CompiledProof,
    internal_dir: Path,
    public_dir: Path,
) -> None:
    """Write private and public artifacts to separate fresh directories.

    Both destination directories must not exist. Files are created with O_EXCL and
    O_NOFOLLOW where available; overwrite, co-location, nesting, and symlink ancestry
    are rejected.
    """

    _verify_compiled(compiled)

    internal = internal_dir.absolute()
    public = public_dir.absolute()
    if internal == public or internal in public.parents or public in internal.parents:
        raise ProofError("internal and public output directories must be disjoint")

    created_dirs: list[Path] = []
    created_files: list[Path] = []
    try:
        internal = _create_dir_exclusive(internal)
        created_dirs.append(internal)
        public = _create_dir_exclusive(public)
        created_dirs.append(public)

        outputs = [
            (internal / "proof.json", compiled.proof_json()),
            (internal / "receipt.sha256", compiled.receipt_sha256 + "\n"),
            (public / "proof.md", compiled.markdown),
            (public / "public.json", public_json(compiled)),
            (
                public / "receipt.sha256",
                public_payload(compiled)["public_receipt_sha256"] + "\n",
            ),
        ]
        for path, text in outputs:
            _write_new_text(path, text)
            created_files.append(path)
    except Exception:
        for path in reversed(created_files):
            try:
                path.unlink()
            except OSError:
                pass
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
