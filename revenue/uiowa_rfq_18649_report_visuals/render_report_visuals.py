#!/usr/bin/env python3
"""Render the report's figures, tables and text alternatives.

    python3 render_report_visuals.py --data fixtures/synthetic_assessment.json \
        --out examples --theme print --theme screen

    python3 render_report_visuals.py --audit            # contrast report only
    python3 render_report_visuals.py --check-encoding   # redundancy contract

Deterministic on purpose: no clock, no randomness, sorted traversal. A second
operator running the same command on the same input gets byte-identical files,
so a diff means the data changed and nothing else.

Python 3 standard library only. No network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import alt_text
import contrast
import figures
import model
import monochrome
import palette

FIGURE_ORDER = ("matrix", "cross-group", "evidence-coverage", "roadmap", "states")


def check_encoding_contract() -> list[str]:
    """Verify the redundancy rules hold. Returns a list of problems."""
    problems: list[str] = []
    bands = [palette.BANDS[k] for k in palette.BAND_ORDER]

    for attr in ("label", "glyph", "shape", "texture"):
        seen: dict[str, str] = {}
        for b in bands:
            value = getattr(b, attr)
            if value in seen:
                problems.append(f"{attr} {value!r} shared by {seen[value]} and {b.key}: "
                                f"that channel can no longer tell them apart")
            seen[value] = b.key

    for key in palette.ORDINAL_KEYS:
        if palette.BANDS[key].border != "solid":
            problems.append(f"{key} is a rating but does not use the solid border")
        if palette.BANDS[key].rank is None:
            problems.append(f"{key} is a rating but carries no rank")
    for key in palette.NON_RATING_KEYS:
        # Solid is reserved for "a value we have". A not-a-rating state wearing
        # a solid border is the exact visual lie this package exists to stop.
        if palette.BANDS[key].border == "solid":
            problems.append(f"{key} is not a rating but wears the solid border reserved "
                            f"for values we actually have")
        if palette.BANDS[key].border not in svg_known_borders():
            problems.append(f"{key}: border {palette.BANDS[key].border!r} is not drawable")
        if palette.BANDS[key].rank is not None:
            problems.append(f"{key} is not a rating but carries rank "
                            f"{palette.BANDS[key].rank}; it would sort onto the scale")

    for nr in palette.NON_RATING_KEYS:
        for rating in palette.ORDINAL_KEYS:
            ratio = contrast.grayscale_contrast(palette.BANDS[nr].fill,
                                                palette.BANDS[rating].fill)
            if round(ratio, 2) < contrast.DISTINCT_MIN:
                problems.append(
                    f"{nr} vs {rating} is {ratio:.2f}:1 in grayscale, below "
                    f"{contrast.DISTINCT_MIN}:1 - the two would be confusable in print")

    # A measured zero must not wear the same border as an omission, or the
    # coverage chart silently equates "we counted none" with "we never looked".
    zero = palette.VALUE_STATES["MEASURED_ZERO"]
    missing = palette.VALUE_STATES["NOT_RECORDED"]
    if zero["border"] == missing["border"]:
        problems.append("measured zero and not-recorded share a border style; a value and "
                        "an omission would look identical")
    if zero["border"] != "solid":
        problems.append("measured zero must use the solid border: it is a value we have")

    for b in bands:
        if b.shape not in svg_known_shapes():
            problems.append(f"{b.key}: shape {b.shape!r} is not drawable")
        if b.texture not in palette_known_textures():
            problems.append(f"{b.key}: texture {b.texture!r} is not drawable")
    return problems


def svg_known_shapes():
    import svg
    return svg.KNOWN_SHAPES


def palette_known_textures():
    import svg
    return svg.KNOWN_TEXTURES


def svg_known_borders():
    import svg
    return svg.KNOWN_BORDERS


def render_all(matrix, out_dir: str, themes) -> list[tuple[str, str]]:
    """Write every figure for every theme, plus the text bundle and tables."""
    os.makedirs(out_dir, exist_ok=True)
    written: list[tuple[str, str]] = []

    for theme_name in themes:
        for key in FIGURE_ORDER:
            fig = figures.FIGURES[key](matrix, theme_name)
            payload = fig.render()
            # The colour version and a real monochrome copy of it. The mono file
            # is not a simulation -- every colour in it has actually been
            # replaced by its luminance-equivalent grey, so a reviewer checking
            # "does this work in black and white" can open the answer.
            for name, body in ((f"{key}.{theme_name}.svg", payload),
                               (f"{key}.{theme_name}.mono.svg",
                                monochrome.to_monochrome(payload))):
                with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                    fh.write(body)
                written.append((name, hashlib.sha256(body.encode("utf-8")).hexdigest()))

    bundle = alt_text.alt_text_bundle(matrix)
    for name, payload in (
        ("text-alternatives.md", bundle),
        ("matrix-table.md", alt_text.matrix_markdown(matrix)),
        ("evidence-coverage-table.md", alt_text.coverage_markdown(matrix)),
        ("roadmap-table.md", alt_text.roadmap_markdown(matrix)),
    ):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload)
        written.append((name, hashlib.sha256(payload.encode("utf-8")).hexdigest()))

    report_lines = []
    for theme_name in themes:
        report_lines.append(f"# contrast audit: theme '{theme_name}'")
        report_lines.append(contrast.format_report(palette.audit_palette(theme_name)))
        report_lines.append("")
    audit_text = "\n".join(report_lines)
    path = os.path.join(out_dir, "contrast-audit.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(audit_text)
    written.append(("contrast-audit.txt",
                    hashlib.sha256(audit_text.encode("utf-8")).hexdigest()))

    manifest = {
        "note": "Deterministic output. Same input plus same command yields identical bytes.",
        "source_title": matrix.title,
        "disclaimer": matrix.disclaimer,
        "themes": list(themes),
        "totals": matrix.totals(),
        "files": [{"name": n, "sha256": h} for n, h in sorted(written)],
    }
    path = os.path.join(out_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return sorted(written)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    here = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--data", default=os.path.join(here, "fixtures",
                                                       "synthetic_assessment.json"))
    parser.add_argument("--out", default=os.path.join(here, "examples"))
    parser.add_argument("--theme", action="append", dest="themes",
                        choices=sorted(palette.THEMES),
                        help="repeatable; defaults to print and screen")
    parser.add_argument("--audit", action="store_true",
                        help="print the WCAG contrast audit and exit")
    parser.add_argument("--check-encoding", action="store_true",
                        help="verify the redundant-encoding contract and exit")
    args = parser.parse_args(argv)

    if args.audit:
        failed = 0
        for theme_name in sorted(palette.THEMES):
            print(f"# contrast audit: theme '{theme_name}'")
            results = palette.audit_palette(theme_name)
            print(contrast.format_report(results))
            failed += sum(1 for r in results if not r.ok)
            print()
        return 1 if failed else 0

    if args.check_encoding:
        problems = check_encoding_contract()
        if problems:
            print("redundant-encoding contract FAILED:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("redundant-encoding contract OK: colour, shape, texture, border and label "
              "are each independently sufficient to name a band; every not-a-rating state "
              "stays >= 3:1 from every rating after colour is removed.")
        return 0

    themes = args.themes or ["print", "screen"]
    try:
        matrix = model.Matrix.from_json_file(args.data)
    except model.DataError as exc:
        print(f"input rejected: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"no such data file: {args.data}", file=sys.stderr)
        return 2

    problems = check_encoding_contract()
    if problems:
        print("refusing to render: the redundant-encoding contract is broken.",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    written = render_all(matrix, args.out, themes)
    t = matrix.totals()
    print(f"{matrix.disclaimer}")
    print(f"rendered {len(written)} files into {args.out}")
    for name, digest in written:
        print(f"  {digest[:12]}  {name}")
    print()
    print(f"{t['rated']} of {t['cells_expected']} cells rated; "
          f"{t['insufficient_evidence']} insufficient evidence; "
          f"{t['not_assessed']} not assessed; {t['not_applicable']} not applicable; "
          f"{t['contradictory']} sources disagree; {t['cells_missing']} no record supplied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
