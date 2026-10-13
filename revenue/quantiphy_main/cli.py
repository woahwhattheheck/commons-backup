from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .maintrack import (
    QuantiPhyMainError,
    build_recipe,
    canonical_bytes,
    load_json_file,
    strict_json_loads,
    verify_submission_bundle,
    write_bundle_exclusive,
)


def _write_exclusive(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise QuantiPhyMainError(f"output already exists: {path}")
    with path.open("xb") as handle:
        handle.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quantiphy-main")
    sub = parser.add_subparsers(dest="command", required=True)

    fit = sub.add_parser("fit")
    fit.add_argument("dataset")
    fit.add_argument("receipts")
    fit.add_argument("--budget-microusd", type=int, required=True)
    fit.add_argument("--folds", type=int, default=4)
    fit.add_argument("--recipe-out", required=True)

    package = sub.add_parser("package")
    package.add_argument("dataset")
    package.add_argument("receipts")
    package.add_argument("recipe")
    package.add_argument("--dest", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("dataset")
    verify.add_argument("receipts")
    verify.add_argument("manifest")
    verify.add_argument("submission")

    args = parser.parse_args(argv)
    try:
        dataset = load_json_file(args.dataset)
        receipts = load_json_file(args.receipts)
        if args.command == "fit":
            recipe = build_recipe(dataset, receipts, budget_microusd=args.budget_microusd, fold_count=args.folds)
            _write_exclusive(Path(args.recipe_out), canonical_bytes(recipe))
            print(json.dumps({"selected": recipe["selected"], "public_validation_mra": recipe["public_validation_mra"]}, sort_keys=True))
            return 0
        recipe = load_json_file(args.recipe if hasattr(args, "recipe") else args.manifest)
        if args.command == "package":
            manifest = write_bundle_exclusive(args.dest, dataset, receipts, recipe)
            print(json.dumps({"manifest_sha256": manifest["manifest_sha256"], "readiness": manifest["readiness"]}, sort_keys=True))
            return 0
        manifest = recipe
        submission = Path(args.submission).read_bytes()
        verify_submission_bundle(dataset, receipts, manifest, submission)
        print("VERIFIED")
        return 0
    except (QuantiPhyMainError, OSError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
