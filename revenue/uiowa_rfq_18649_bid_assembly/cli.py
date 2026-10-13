"""Assemble a review-draft bid folder. Exit 0 ok, 1 findings under --strict, 2 refuse."""

from __future__ import annotations

import argparse
import os
import sys

try:
    from .assembler import (
        ERROR,
        AssemblyError,
        BidAssembly,
        PaginationError,
        load_manifest,
    )
except ImportError:
    from assembler import (
        ERROR,
        AssemblyError,
        BidAssembly,
        PaginationError,
        load_manifest,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Assemble a hash-bound RFQ 18649 review-draft folder."
    )
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any ERROR-severity issue was raised",
    )
    args = ap.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        root = os.path.dirname(os.path.abspath(args.manifest))
        result = BidAssembly(manifest, root).assemble(args.out)
    except (AssemblyError, PaginationError) as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2
    r = result["readiness"]
    print("assembled -> %s" % args.out)
    print(
        "  proposal.pdf: %d pages (%d bytes), pagination settled in %d pass(es)"
        % (
            result["render"]["pdf_pages"],
            result["render"]["pdf_bytes"],
            result["render"]["pagination_passes"],
        )
    )
    print(
        "  sections: %d   attachments: %d"
        % (len(result["sections"]), len(result["attachments"]))
    )
    print(
        "  required attachments declared %d / present %d / NOT SUPPLIED %d %s"
        % (
            r["required_declared"],
            r["required_present"],
            len(r["required_not_supplied"]),
            ("(%s)" % ", ".join(r["required_not_supplied"]))
            if r["required_not_supplied"]
            else "",
        )
    )
    print("  status: %s" % r["status"])
    print("  currentness: %s" % result["reconciliation"]["status"])
    for i in result["issues"]:
        print("  [%-5s] %-42s %s" % (i["severity"], i["code"], i["detail"]))
    if args.strict and any(i["severity"] == ERROR for i in result["issues"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
