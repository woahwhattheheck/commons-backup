from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import (
    ContractError,
    Corpus,
    ResourceManifest,
    build_run_receipt,
    canonical_bytes,
    load_json_strict,
    track1_predict,
    track2_rank,
)
from .publication import PairPublicationError, publish_pair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline SPARK dbGaP transparent baseline")
    parser.add_argument("--track", type=int, choices=(1, 2), required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--resources", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--abstain-coverage-bp", type=int, default=5000)
    args = parser.parse_args(argv)
    try:
        corpus_obj = load_json_strict(args.corpus)
        resources_obj = load_json_strict(args.resources)
        input_obj = load_json_strict(args.input)
        corpus = Corpus.from_obj(corpus_obj)
        resources = ResourceManifest.from_obj(resources_obj)
        if args.track == 1:
            output = track1_predict(
                corpus,
                input_obj,
                abstain_coverage_bp=args.abstain_coverage_bp,
                top_k=args.top_k,
            )
            policy = {
                "top_k": args.top_k,
                "abstain_coverage_bp": args.abstain_coverage_bp,
            }
        else:
            output = track2_rank(corpus, input_obj, top_k=args.top_k)
            policy = {"top_k": args.top_k}
        receipt = build_run_receipt(
            track=args.track,
            corpus=corpus,
            resources=resources,
            input_obj=input_obj,
            output_obj=output,
            source_version=args.source_version,
            policy=policy,
        )
        publication = publish_pair(
            Path(args.output),
            canonical_bytes(output) + b"\n",
            Path(args.receipt),
            canonical_bytes(receipt) + b"\n",
        )
    except PairPublicationError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "publication_status": exc.status,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "track": args.track,
                "output": args.output,
                "receipt": args.receipt,
                "publication": publication,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
