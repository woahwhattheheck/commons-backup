#!/usr/bin/env python3
"""Small stdlib CLI for the Lost in Transcription offline toolkit."""
from __future__ import annotations

import argparse
from pathlib import Path

from toolkit import (
    build_submission_zip,
    corpus_wer,
    inspect_submission_zip,
    read_csv_rows,
    validate_submission_csv,
    write_split_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_score = sub.add_parser("score")
    p_score.add_argument("ground_truth", type=Path)
    p_score.add_argument("predictions", type=Path)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("submission_format", type=Path)
    p_validate.add_argument("predictions", type=Path)

    p_split = sub.add_parser("split")
    p_split.add_argument("metadata", type=Path)
    p_split.add_argument("output", type=Path)
    p_split.add_argument("--seed", default="mozilla-id-jv-v1")
    p_split.add_argument("--validation-fraction", type=float, default=0.2)
    p_split.add_argument("--group-column")

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("source_dir", type=Path)
    p_pack.add_argument("output_zip", type=Path)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("zip_path", type=Path)

    args = parser.parse_args()
    if args.command == "score":
        truth = read_csv_rows(args.ground_truth)
        pred = read_csv_rows(args.predictions)
        validate_submission_csv(args.ground_truth, args.predictions)
        pred_by_name = {row["audio_filename"]: row["transcript"] for row in pred}
        refs = [row["transcript"] for row in truth]
        hyps = [pred_by_name[row["audio_filename"]] for row in truth]
        counts = corpus_wer(refs, hyps)
        print(
            f"WER={counts.wer:.6f} S={counts.substitutions} "
            f"D={counts.deletions} I={counts.insertions} N={counts.reference_words}"
        )
    elif args.command == "validate":
        validate_submission_csv(args.submission_format, args.predictions)
        print("VALID")
    elif args.command == "split":
        write_split_manifest(
            args.metadata,
            args.output,
            seed=args.seed,
            validation_fraction=args.validation_fraction,
            group_column=args.group_column,
        )
        print(args.output)
    elif args.command == "pack":
        digest = build_submission_zip(args.source_dir, args.output_zip)
        print(f"{args.output_zip} sha256={digest}")
    elif args.command == "inspect":
        for name in inspect_submission_zip(args.zip_path):
            print(name)


if __name__ == "__main__":
    main()
