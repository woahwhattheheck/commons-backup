#!/usr/bin/env python3
"""Build or replay an exact-source citation bundle from synthetic preparation inputs."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "uiowa_rfq_18649_citations"

from .contract import load_json
from .export import write_new_bundle
from .resolver import Resolver
from .sample import make_sample


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sample = sub.add_parser('rehearse', help='Run retained-byte fixtures through actual extractor and compiler')
    sample.add_argument('--out', type=Path, required=True)
    build = sub.add_parser('build', help='Resolve an existing citation packet and compiler report')
    build.add_argument('--packet', type=Path, required=True)
    build.add_argument('--report', type=Path, required=True)
    build.add_argument('--sources-root', type=Path, required=True)
    build.add_argument('--out', type=Path, required=True)
    audit = sub.add_parser('audit-093', help='Map canonical 093 source-intake needs without inventing documents')
    audit.add_argument('--input', type=Path, default=Path(__file__).resolve().parent.parent /
                       'uiowa_rfq_18649_traceability_rehearsal')
    audit.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'rehearse':
            with tempfile.TemporaryDirectory(prefix='uiowa-retained-demo-') as temp:
                root = Path(temp)
                packet, report = make_sample(root)
                result = write_new_bundle(Resolver(packet, report, root), args.out)
        elif args.command == 'audit-093':
            from .canonical_093 import audit_rehearsal, write_audit
            result = write_audit(audit_rehearsal(args.input), args.out)
        else:
            result = write_new_bundle(Resolver(load_json(args.packet), load_json(args.report),
                                              args.sources_root), args.out)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        print(json.dumps({'error': type(exc).__name__, 'detail': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
