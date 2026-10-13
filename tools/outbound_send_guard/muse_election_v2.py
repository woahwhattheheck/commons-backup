#!/usr/bin/env python3
"""Canonical Muse publication-election v2 entrypoint.

Raw/caller-provided Slack snapshots are analysis evidence only: they may prove
HOLD, but cannot mint terminal SELECTED or NOT_SELECTED authority until a real
provider-authenticated adapter exists.

Authority threat model
----------------------
This module controls the supported application API and CLI surface. Callers
cannot provide the observation clock through either surface and the legacy raw
compiler is not an importable/runnable Python module. This is *not* a Python
sandbox: code already executing in this process can use reflection, mutate
module globals, monkeypatch dependencies, or execute arbitrary source and is
outside this boundary. A stronger same-process/adversarial-code claim requires
a separately reviewed provider/process isolation boundary.
"""
from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

AUTHORITY_THREAT_MODEL = (
    "supported API/CLI input authority; arbitrary same-process code mutation "
    "and reflection are out of scope"
)
_AUTHORITY_FIELDS = frozenset(
    {
        "authority_mode",
        "snapshot_authenticated",
        "snapshot_authentication_sha256",
        "valid_until",
        "request_context_sha256",
    }
)
_BLOCKED_LEGACY_EXPORTS = frozenset(
    {"compile_receipt", "verify_selected_binding", "main", "_build_parser", "_core"}
)


def _bind_boundary():
    """Bind the legacy deterministic engine inside this public boundary.

    The preserved predecessor source is data (`.py.inc`), not an importable
    module or `python -m` entrypoint. Only fail-closed public callables escape
    this closure. This removes the ordinary legacy authority bypass while
    preserving exact predecessor logic for replay/election analysis.
    """
    from tools.outbound_send_guard import muse_current_authority_v2 as current_auth

    engine_path = Path(__file__).with_name("_muse_election_v2_core.py.inc")
    engine_source = engine_path.read_text(encoding="utf-8")
    engine: dict[str, Any] = {
        "__name__": "tools.outbound_send_guard._muse_election_v2_embedded",
        "__package__": "tools.outbound_send_guard",
        "__file__": str(engine_path),
    }
    exec(compile(engine_source, str(engine_path), "exec"), engine, engine)

    negative_authority_fields = (
        current_auth._SELECTION_FIELDS + current_auth._WINNER_FIELDS
    )

    def legacy_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(receipt["payload"])
        for name in _AUTHORITY_FIELDS:
            payload.pop(name, None)
        return {"payload": payload, "receipt_sha256": engine["_digest"](payload)}

    def legacy_prior_receipts(
        prior_receipts: Iterable[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        projected: list[Mapping[str, Any]] = []
        for prior in prior_receipts:
            if current_auth.verify_untrusted_snapshot_receipt(prior):
                projected.append(legacy_projection(prior))
            else:
                projected.append(prior)
        return projected

    def compile_receipt(
        request: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        *,
        prior_receipts: Iterable[Mapping[str, Any]] = (),
        ledger_complete: bool,
    ) -> dict[str, Any]:
        """Compile raw snapshot analysis using the process clock, then seal it.

        The supported call surface intentionally has no `observed_at` input.
        Raw terminal SELECTED and NOT_SELECTED decisions are both demoted by the
        current-authority envelope until a provider-authenticated adapter is
        composed in a separate reviewed lane.
        """
        observed = current_auth._utc_now()
        raw = engine["compile_receipt"](
            request,
            snapshot,
            observed_at=engine["_fmt"](observed),
            prior_receipts=legacy_prior_receipts(prior_receipts),
            ledger_complete=ledger_complete,
        )
        if raw["payload"].get("decision") != "SELECTED":
            for name in negative_authority_fields:
                raw["payload"][name] = None
            raw["receipt_sha256"] = engine["_digest"](raw["payload"])
        if not engine["verify_receipt"](raw):
            raise engine["MuseElectionV2Error"](
                "embedded source receipt failed structural verification"
            )
        return current_auth.seal_untrusted_snapshot_receipt(raw)

    def verify_receipt(raw: Mapping[str, Any]) -> bool:
        if not current_auth.verify_untrusted_snapshot_receipt(raw):
            return False
        try:
            return engine["verify_receipt"](legacy_projection(raw))
        except (KeyError, TypeError, ValueError):
            return False

    def verify_selected_binding(
        request: Mapping[str, Any], receipt: Mapping[str, Any]
    ) -> bool:
        if not verify_receipt(receipt):
            return False
        if receipt["payload"].get("decision") != "SELECTED":
            return False
        return engine["verify_selected_binding"](request, legacy_projection(receipt))

    def prepare_request(*args: Any, **kwargs: Any) -> Any:
        return engine["prepare_request"](*args, **kwargs)

    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=__doc__)
        sub = parser.add_subparsers(dest="command", required=True)
        prep = sub.add_parser("prepare")
        for name in (
            "buyer-scope-sha256",
            "recipient-fingerprint",
            "offer-scope-sha256",
            "intent-sha256",
            "body-sha256",
        ):
            prep.add_argument("--" + name, required=True)
        prep.add_argument("--route-kind", required=True)
        prep.add_argument("--claimant", required=True)
        prep.add_argument("--operation-id", required=True)
        prep.add_argument("--lease-binding", required=True)
        prep.add_argument("--request-id", required=True)
        prep.add_argument("--requested-at", required=True)
        comp = sub.add_parser("compile")
        comp.add_argument("--request", required=True)
        comp.add_argument("--snapshot", required=True)
        comp.add_argument("--prior-ledger")
        comp.add_argument("--ledger-complete", action="store_true")
        verify = sub.add_parser("verify")
        verify.add_argument("--receipt", required=True)
        verify.add_argument("--request")
        return parser

    def main(argv: list[str] | None = None) -> int:
        args = build_parser().parse_args(argv)
        try:
            if args.command == "prepare":
                lease_binding = engine["_read_json"](args.lease_binding, "lease binding")
                candidate = {
                    "buyer_scope_sha256": args.buyer_scope_sha256,
                    "recipient_fingerprint": args.recipient_fingerprint,
                    "offer_scope_sha256": args.offer_scope_sha256,
                    "route_kind": args.route_kind,
                    "intent_sha256": args.intent_sha256,
                    "body_sha256": args.body_sha256,
                    "claimant": args.claimant,
                    "operation_id": args.operation_id,
                    "lease_binding": lease_binding,
                }
                engine["_write_json"](
                    prepare_request(
                        candidate,
                        request_id=args.request_id,
                        requested_at=args.requested_at,
                    )
                )
                return 0
            if args.command == "compile":
                request = engine["_read_json"](args.request, "request")
                snapshot = engine["_read_json"](args.snapshot, "snapshot")
                prior: list[Mapping[str, Any]] = []
                if args.prior_ledger:
                    ledger = engine["_read_json"](args.prior_ledger, "prior ledger")
                    if type(ledger) is not list:
                        raise engine["MuseElectionV2Error"]("prior ledger: array required")
                    prior = ledger
                receipt = compile_receipt(
                    request,
                    snapshot,
                    prior_receipts=prior,
                    ledger_complete=args.ledger_complete,
                )
                engine["_write_json"](receipt)
                return {"SELECTED": 0, "NOT_SELECTED": 3, "HOLD": 4}[
                    receipt["payload"]["decision"]
                ]
            receipt = engine["_read_json"](args.receipt, "receipt")
            ok = verify_receipt(receipt)
            if ok and args.request:
                ok = verify_selected_binding(
                    engine["_read_json"](args.request, "request"), receipt
                )
            engine["_write_json"]({"valid": ok})
            return 0 if ok else 2
        except (
            engine["MuseElectionV2Error"],
            OSError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    @functools.lru_cache(maxsize=None)
    def safe_proxy(name: str):
        value = engine[name]
        # Classes, including MuseElectionV2Error, must remain types so callers
        # can catch them. Wrapping a class as a function makes assertRaises fail.
        if isinstance(value, type) or not callable(value):
            return value

        @functools.wraps(value)
        def proxy(*args: Any, **kwargs: Any) -> Any:
            return value(*args, **kwargs)

        return proxy

    def module_getattr(name: str) -> Any:
        if name in _BLOCKED_LEGACY_EXPORTS or name.startswith("_muse_election_v2"):
            raise AttributeError(name)
        if name not in engine:
            raise AttributeError(name)
        return safe_proxy(name)

    def module_dir() -> list[str]:
        allowed = {name for name in engine if name not in _BLOCKED_LEGACY_EXPORTS}
        return sorted(allowed | set(globals()))

    return (
        compile_receipt,
        verify_receipt,
        verify_selected_binding,
        prepare_request,
        build_parser,
        main,
        module_getattr,
        module_dir,
    )


(
    compile_receipt,
    verify_receipt,
    verify_selected_binding,
    prepare_request,
    _build_parser,
    main,
    __getattr__,
    __dir__,
) = _bind_boundary()
del _bind_boundary


if __name__ == "__main__":
    raise SystemExit(main())
