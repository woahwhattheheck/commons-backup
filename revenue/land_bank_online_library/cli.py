"""CLI for the Land Bank T12-09-26 fail-closed readiness carrier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import (
    EvidenceRef,
    PaidWorkshare,
    PrimeCandidate,
    SourceCustody,
    SubmissionAuthority,
    compile_readiness,
    render_markdown,
)


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid input JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _ref(value: Any) -> EvidenceRef | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("evidence reference must be an object")
    return EvidenceRef(
        label=value.get("label", ""),
        locator=value.get("locator", ""),
        sha256_hex=value.get("sha256", ""),
        note=value.get("note", ""),
    )


def _refs(value: Any) -> tuple[EvidenceRef, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("evidence references must be a list")
    out: list[EvidenceRef] = []
    for item in value:
        ref = _ref(item)
        if ref is not None:
            out.append(ref)
    return tuple(out)


def compile_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    source_data = data.get("source_custody", {})
    prime_data = data.get("prime", {})
    workshare_data = data.get("paid_workshare", {})
    auth_data = data.get("submission_authority", {})
    if not all(
        isinstance(value, dict)
        for value in (source_data, prime_data, workshare_data, auth_data)
    ):
        raise ValueError("source_custody, prime, paid_workshare, and submission_authority must be objects")

    raw_evidence = prime_data.get("evidence", {})
    if not isinstance(raw_evidence, dict):
        raise ValueError("prime.evidence must be an object")

    source = SourceCustody(
        authoritative_tender_ref=_ref(source_data.get("authoritative_tender_ref")),
        annexure_refs=_refs(source_data.get("annexure_refs")),
        secondary_listing_refs=_refs(source_data.get("secondary_listing_refs")),
    )
    prime = PrimeCandidate(
        legal_name=prime_data.get("legal_name", ""),
        evidence={str(key): _ref(value) for key, value in raw_evidence.items()},
    )
    workshare = PaidWorkshare(
        owner=workshare_data.get("owner", ""),
        deliverables=tuple(workshare_data.get("deliverables", [])),
        acceptance_criteria=tuple(workshare_data.get("acceptance_criteria", [])),
        exclusions=tuple(workshare_data.get("exclusions", [])),
        commercial_state=workshare_data.get("commercial_state", "PAID_SCOPE_TO_BE_AGREED"),
    )
    auth = SubmissionAuthority(
        buyer_submission_instructions_verified=auth_data.get("buyer_submission_instructions_verified") is True,
        authorized_signatory_confirmed=auth_data.get("authorized_signatory_confirmed") is True,
        prime_approved_submission=auth_data.get("prime_approved_submission") is True,
        physical_delivery_authorized=auth_data.get("physical_delivery_authorized") is True,
    )
    return compile_readiness(
        source_custody=source,
        prime=prime,
        workshare=workshare,
        submission_authority=auth,
        authority_root=data.get("authority_root") is True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)

    try:
        pack = compile_from_dict(_load(args.input))
    except (TypeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    rendered = json.dumps(pack, sort_keys=True, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(pack), encoding="utf-8")
    return 0 if pack["submission_status"] == "SUBMISSION_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
