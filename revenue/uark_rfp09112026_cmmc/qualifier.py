#!/usr/bin/env python3
"""Historical/integrity-only UArk RFP09112026 qualifier facade.

This compatibility surface intentionally preserves the original deterministic
compiler and receipt verifier. It is not CURRENT authority because its
``evaluated_at_utc`` value is caller supplied. Use ``current_authority.py`` for
process-clock compilation and fresh current verification.

Persisted Markdown from this historical facade is deliberately refused. Every
renderer reachable through the facade's exported function metadata is hardened
in the loaded core namespace itself, so recovering a core global cannot recover
an unlabeled renderer or a legacy Markdown-persisting ``main``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_CORE_PATH = Path(__file__).with_name("_qualifier_core.py")
_SPEC = importlib.util.spec_from_file_location(
    "uark_rfp09112026_qualifier_historical_core", _CORE_PATH
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import contract
    raise ImportError(f"cannot load UArk qualifier core from {_CORE_PATH}")
_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)

# Harden the loaded historical core *before* any core function is re-exported.
# This deliberately replaces the two legacy callables in the core module's own
# globals dictionary.  Therefore another exported core function's ``__globals__``
# can recover only these hardened definitions, not the predecessor raw renderer
# or raw CLI main.  The replacement functions carry no callable defaults or
# closures containing the predecessor callables.
_HARDENED_CORE_SOURCE = r'''
_HISTORICAL_BANNER = "# HISTORICAL / INTEGRITY ONLY / NOT CURRENT"


def render_markdown(packet: dict[str, Any]) -> str:
    verify_packet(packet)
    d = packet["decision"]
    blockers = "\n".join(f"- {x}" for x in d["blockers"]) or "- none"
    risks = "\n".join(f"- {x}" for x in d["risks"]) or "- none"
    body = (
        "# UArk RFP09112026 qualification\n\n"
        f"**Route:** `{d['route_requested']}`  \n"
        f"**Status:** `{d['status']}`  \n"
        f"**Submission ready:** `{str(d['submission_ready']).lower()}`  \n"
        f"**Internal workshare target:** `${packet['internal_workshare_target_usd']:,}` — `{PRICE_BOUNDARY}`\n\n"
        "## Blockers\n" + blockers + "\n\n"
        "## Risks / packet gaps\n" + risks + "\n\n"
        "## Authority boundary\n"
        "This result authorizes no buyer or partner contact, no portal action, no signature, no price commitment, "
        "no certification/assessment representation, no FCI/CUI handling, no contract acceptance, and no award/revenue claim. "
        "Any email requires a fresh collision/provider-history fence and explicit Muse single-writer selection.\n\n"
        f"Receipt: `{packet['packet_receipt_sha256']}`\n"
    )
    return _HISTORICAL_BANNER + "\n\n" + body


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        print(
            "NOTICE: HISTORICAL_INTEGRITY_ONLY; use current_authority.py for CURRENT authority",
            file=sys.stderr,
        )
        if args.command == "compile":
            if args.markdown_out:
                raise InputError(
                    "HISTORICAL_INTEGRITY_ONLY qualifier refuses persisted Markdown; "
                    "use current_authority.py for CURRENT Markdown"
                )
            packet = compile_qualification(read_json_file(args.input_json))
            json_text = canonical_json(packet) + "\n"
            if args.json_out:
                _write_exclusive(args.json_out, json_text)
            else:
                sys.stdout.write(json_text)
            return 0
        if args.command == "verify":
            verify_packet(read_json_file(args.packet_json))
            print("VERIFIED")
            return 0
        raise InputError("unknown command")
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
'''
exec(_HARDENED_CORE_SOURCE, _core.__dict__)
del _HARDENED_CORE_SOURCE

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

AUTHORITY_MODE = "HISTORICAL_INTEGRITY_ONLY"
compile_historical = _core.compile_qualification
verify_packet_historical = _core.verify_packet
compile_qualification = compile_historical
verify_packet = verify_packet_historical
render_markdown = _core.render_markdown
main = _core.main

# Do not retain the module handle on the facade. Exported core functions still
# have their normal globals dictionary, but the unsafe predecessor callables
# were replaced in that dictionary before export.
del _core, _SPEC, _name


if __name__ == "__main__":
    raise SystemExit(main())
