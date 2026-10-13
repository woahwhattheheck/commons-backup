"""Publish the existing question-card renderers without destroying prior reports.

This is a publication helper, not a second question-card engine. The caller
supplies the actual loader, classifier and two renderers. All input interpretation
and rendering finish before output files are touched. Each destination replacement
is atomic; the three-file set is NOT a crash-atomic transaction.

Standalone recovery route:
    python export_publication.py check --data data --out /tmp/new-review
All bundled demonstration records are fictional. No network or model calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable

OUTPUT_NAMES = ("cards.json", "cards.csv", "question_cards.md")


def _same_file(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return os.path.samefile(first, second)
    except FileNotFoundError:
        return False


def _preflight(data_dir: Path, observations_file: str, out_dir: Path) -> None:
    inputs = [data_dir / name for name in
              ("templates.json", "sources.json", "interview_register.json", observations_file)]
    for name in OUTPUT_NAMES:
        target = out_dir / name
        if target.is_dir():
            raise ValueError(f"INVALID_OUTPUT: {name} is a directory")
        for source in inputs:
            if _same_file(target, source):
                raise ValueError(f"INPUT_OUTPUT_ALIAS: {name} would replace an input file")


def _publish(out_dir: Path, payloads: dict[str, bytes]) -> None:
    """Stage ALL bytes on the output filesystem before the first replacement.

    A failed staging write changes no destination. A failed replacement leaves
    that destination intact, but earlier replacements may already have succeeded.
    Only temporary files created by this call are ever removed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[Path, Path]] = []
    try:
        for name in OUTPUT_NAMES:
            with tempfile.NamedTemporaryFile(mode="wb", dir=out_dir,
                    prefix=".question-cards-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                pending.append((temporary, out_dir / name))
                handle.write(payloads[name])
                handle.flush()
        for temporary, target in pending:
            os.replace(temporary, target)
    finally:
        for temporary, _ in pending:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def build_export(data_dir, out_dir, observations_file="observations.json", *,
                 load_bundle: Callable, build_cards: Callable,
                 write_cards_csv: Callable, write_cards_markdown: Callable):
    """Keep existing classification/output bytes, changing only publication order.

    Malformed structural/rendering values are input errors. Observation-level
    diagnostics retain the actual classifier's meanings and do not become a
    fabricated successful assessment. Callbacks are the existing component's
    functions, not replacement models or mocks.
    """
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    _preflight(data_dir, observations_file, out_dir)
    try:
        bundle = load_bundle(str(data_dir), observations_file)
        notice = bundle["observations"]["fiction_notice"]
        if not isinstance(notice, str) or not notice.strip():
            raise ValueError("INVALID_BUNDLE: fiction_notice must be a nonempty string")
        cards, diagnostics, coverage = build_cards(bundle)
        payload = {"fiction_notice": notice, "cards": cards,
                   "diagnostics": diagnostics, "coverage": coverage}
        json_bytes = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="question-cards-render-") as directory:
            stage = Path(directory)
            write_cards_csv(stage / "cards.csv", cards)
            write_cards_markdown(stage / "question_cards.md", cards, coverage, diagnostics)
            payloads = {"cards.json": json_bytes,
                        "cards.csv": (stage / "cards.csv").read_bytes(),
                        "question_cards.md": (stage / "question_cards.md").read_bytes()}
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError(f"INVALID_BUNDLE: {type(exc).__name__}: {exc}") from exc
    # Recheck after rendering as well. This detects movement observed here, but
    # does not promise protection against arbitrary concurrent filesystem edits.
    _preflight(data_dir, observations_file, out_dir)
    _publish(out_dir, payloads)
    return cards, diagnostics, coverage


def main(argv=None):
    if __package__:
        from . import question_cards as component
    else:
        import question_cards as component
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--data", default=str(Path(__file__).parent / "data"))
    parser.add_argument("--observations", default="observations.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        _, diagnostics, coverage = build_export(
            args.data, args.out, args.observations,
            load_bundle=component.load_bundle, build_cards=component.build_cards,
            write_cards_csv=component.write_cards_csv,
            write_cards_markdown=component.write_cards_markdown)
    except (ValueError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    errors = component.print_status(diagnostics, coverage)
    return 1 if args.command == "check" and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
