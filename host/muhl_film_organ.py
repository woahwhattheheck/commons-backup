#!/usr/bin/env python3
"""Validate the in-tree Muhlnickel film-organ reference without executing a film.

This host reads repository evidence only. It never walks gates, renders frames,
writes titan, invents a mouth/destination, fires 337, pulses 78, lights 7913,
injects DC, or invokes an encoder.

  python3 host/muhl_film_organ.py
  python3 host/muhl_film_organ.py --root .
  python3 host/muhl_film_organ.py --self-test
  python3 host/muhl_film_organ.py --go  # explicit refusal; no mutation
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "MUHL_FILM_ORGAN.json")
DEFAULT_CARD = os.path.join("ground", "MUHL_FILM_ORGAN.md")
DEFAULT_SOURCE = os.path.join("ground", "muhl_film_organ", "source.json")
DEFAULT_REEL = os.path.join("muhl", "docs", "FILM_REEL.pfc")
DEFAULT_DOOR = "film.html"
EXPECTED_BYTES = 2498592
EXPECTED_MAGIC = b"PFCGAME1"
EXPECTED_SHA256 = "27d8371e8968ed6bccc0fd27400e35e78fb7e7da87f7c472b175ba08a6901e88"
EXPECTED_LIVE_CELLS = 1212
EXPECTED_FINAL_STATE = 1936723975
EXPECTED_PREFIX_BITS = "0000000000001011100000001011011010000000000000010000100000011000"
REQUIRED_FILES = (
    DEFAULT_CATALOG,
    DEFAULT_CARD,
    DEFAULT_SOURCE,
    DEFAULT_REEL,
    DEFAULT_DOOR,
    os.path.join("host", "muhl_film_organ.py"),
    "test_muhl_film_organ.py",
)


def _read(root, rel, binary=False):
    path = os.path.join(root, rel)
    try:
        if binary:
            with open(path, "rb") as handle:
                return handle.read()
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return b"" if binary else ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_json(text):
    try:
        value = json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _is_exact_int(value):
    return type(value) is int


def lcg_reference(source):
    if not isinstance(source, dict) or not source:
        return {"state": "UNMEASURED", "note": "source fixture was not read"}
    grid = source.get("grid")
    lcg = source.get("lcg")
    if (
        not isinstance(grid, list)
        or len(grid) != 2
        or not all(_is_exact_int(value) for value in grid)
        or not isinstance(lcg, dict)
    ):
        return {"state": "NOT_LANDED", "note": "source fixture fields are incomplete"}
    numeric = (
        source.get("cells"),
        lcg.get("a"),
        lcg.get("c"),
        lcg.get("m"),
        lcg.get("seed"),
        source.get("density_num"),
        source.get("density_den"),
        source.get("feature_length_pulses_declared"),
        source.get("fps"),
        source.get("runtime_s_declared"),
    )
    if not all(_is_exact_int(value) for value in numeric):
        return {"state": "NOT_LANDED", "note": "source numeric fields must be exact JSON integers"}
    width, height = grid
    (
        cells,
        a,
        c,
        modulus,
        state,
        density_num,
        density_den,
        feature_length,
        fps,
        runtime_s,
    ) = numeric
    if source.get("prng") != "lcg" or (width, height, cells) != (64, 64, 4096):
        return {"state": "NOT_LANDED", "note": "source must be the declared 64x64 LCG fixture"}
    if (a, c, modulus, state, density_num, density_den) != (
        1664525,
        1013904223,
        4294967296,
        7,
        30,
        100,
    ):
        return {"state": "NOT_LANDED", "note": "LCG or density differs from the declared source"}
    bits = []
    for _ in range(cells):
        state = (a * state + c) % modulus
        bits.append("1" if state % density_den < density_num else "0")
    bit_text = "".join(bits)
    return {
        "state": "REFERENCE_SOURCE_VERIFIED",
        "cells": cells,
        "live_cells": bit_text.count("1"),
        "final_state": state,
        "prefix_bits": bit_text[:64],
        "feature_length_pulses_declared": feature_length,
        "fps": fps,
        "runtime_s_declared": runtime_s,
    }


def measure_reel(path):
    try:
        size = os.path.getsize(path)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            magic = handle.read(len(EXPECTED_MAGIC))
            digest.update(magic)
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return {"state": "UNMEASURED", "note": str(exc)}
    return {
        "state": "REFERENCE_REEL_VERIFIED",
        "bytes": size,
        "magic": magic.decode("ascii", errors="replace"),
        "sha256": digest.hexdigest(),
    }


def measure_root(root):
    root = os.path.abspath(root)
    catalog = load_json(_read(root, DEFAULT_CATALOG))
    source = load_json(_read(root, DEFAULT_SOURCE))
    door = _read(root, DEFAULT_DOOR)
    card = _read(root, DEFAULT_CARD)
    return {
        "measured": True,
        "misses": [rel for rel in REQUIRED_FILES if not _exists(root, rel)],
        "catalog": catalog,
        "source": source,
        "source_measure": lcg_reference(source),
        "reel": measure_reel(os.path.join(root, DEFAULT_REEL)),
        "door": door,
        "card": card,
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {"state": "UNMEASURED", "note": "film-organ tree was not read"}
    if row.get("misses"):
        return {"state": "NOT_LANDED", "note": "missing path(s): " + ", ".join(row["misses"])}

    catalog = row.get("catalog")
    source = row.get("source")
    reel = row.get("reel")
    if not isinstance(catalog, dict) or not isinstance(source, dict) or not isinstance(reel, dict):
        return {"state": "NOT_LANDED", "note": "catalog, source, and measured reel must be objects"}

    expected_catalog = {
        "kind": "MUHL_FILM_ORGAN_REFERENCE",
        "state": "REFERENCE_ONLY",
        "reference_organ": DEFAULT_REEL.replace(os.sep, "/"),
        "source_fixture": DEFAULT_SOURCE.replace(os.sep, "/"),
        "public_surface": DEFAULT_DOOR.replace(os.sep, "/"),
        "card": DEFAULT_CARD.replace(os.sep, "/"),
        "instrument": os.path.join("host", "muhl_film_organ.py").replace(os.sep, "/"),
    }
    for key, expected in expected_catalog.items():
        if catalog.get(key) != expected:
            return {"state": "NOT_LANDED", "note": "catalog declaration differs: " + key}

    catalog_reel = catalog.get("reel")
    if not isinstance(catalog_reel, dict):
        return {"state": "NOT_LANDED", "note": "catalog reel declaration must be an object"}
    expected_reel = {
        "bytes": EXPECTED_BYTES,
        "magic": EXPECTED_MAGIC.decode("ascii"),
        "sha256": EXPECTED_SHA256,
    }
    if any(reel.get(key) != value for key, value in expected_reel.items()):
        return {"state": "NOT_LANDED", "note": "measured reel bytes, magic, or sha256 differ"}
    if any(catalog_reel.get(key) != reel.get(key) for key in expected_reel):
        return {"state": "NOT_LANDED", "note": "catalog reel is not bound to measured reel bytes"}

    source_measure = lcg_reference(source)
    if (
        source_measure.get("state") != "REFERENCE_SOURCE_VERIFIED"
        or source_measure.get("live_cells") != EXPECTED_LIVE_CELLS
        or source_measure.get("final_state") != EXPECTED_FINAL_STATE
        or source_measure.get("prefix_bits") != EXPECTED_PREFIX_BITS
    ):
        return {"state": "NOT_LANDED", "note": "deterministic LCG source differs"}

    expected_source = {
        "kind": "MUHL_FILM_SOURCE",
        "organ": DEFAULT_REEL.replace(os.sep, "/"),
        "expected_live_cells": EXPECTED_LIVE_CELLS,
        "expected_final_state": EXPECTED_FINAL_STATE,
        "expected_prefix_bits": EXPECTED_PREFIX_BITS,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            return {"state": "NOT_LANDED", "note": "source declaration differs: " + key}

    if (
        not _is_exact_int(source.get("feature_length_pulses_declared"))
        or source.get("feature_length_pulses_declared") != 129600
        or source_measure.get("feature_length_pulses_declared") != 129600
        or source_measure.get("fps") != 24
        or source_measure.get("runtime_s_declared") != 5400
        or source_measure.get("fps") * source_measure.get("runtime_s_declared") != 129600
    ):
        return {"state": "NOT_LANDED", "note": "129600 must equal exact fps times declared runtime"}

    if (
        not _is_exact_int(catalog.get("feature_length_pulses_declared"))
        or catalog.get("feature_length_pulses_declared") != 129600
        or not _is_exact_int(catalog.get("executed_pulses"))
        or catalog.get("executed_pulses") != 0
    ):
        return {"state": "NOT_LANDED", "note": "catalog pulse declarations differ"}

    catalog_false = (
        "movie_executed",
        "byte_exact_feature_run",
        "host_inference",
        "host_gate_walk",
        "host_frame_simulation",
        "invented_dest",
        "invented_mouth",
        "fire_337",
        "pulse_78",
        "light_7913",
        "dc_injected",
        "private_owner_media",
        "pirated_mp4",
        "mp4",
        "ffmpeg",
    )
    if any(catalog.get(key) is not False for key in catalog_false):
        return {"state": "NOT_LANDED", "note": "catalog fabricates execution or a prohibited action"}
    if catalog.get("titan") != "NOT_WRITTEN" or catalog.get("no_auth") is not True or catalog.get("no_gate") is not True:
        return {"state": "NOT_LANDED", "note": "reference boundary or open door differs"}

    source_false = (
        "movie_executed",
        "byte_exact_feature_run",
        "host_frame_simulation",
        "invented_dest",
        "invented_mouth",
        "fire_337",
        "pulse_78",
        "light_7913",
        "dc_injected",
        "mp4",
        "ffmpeg",
    )
    if (
        any(source.get(key) is not False for key in source_false)
        or not _is_exact_int(source.get("executed_pulses"))
        or source.get("executed_pulses") != 0
        or source.get("titan") != "NOT_WRITTEN"
    ):
        return {"state": "NOT_LANDED", "note": "source fixture fabricates execution or a prohibited action"}

    required_text = (
        "REFERENCE VISOR",
        "MOVIE_EXECUTED: NO",
        "129,600 pulses were not executed",
        "No invented mouth or destination",
        "PFCGAME1",
        EXPECTED_SHA256,
    )
    for surface_name in ("door", "card"):
        surface = row.get(surface_name)
        if not isinstance(surface, str) or any(text not in surface for text in required_text):
            return {"state": "NOT_LANDED", "note": surface_name + " omits the execution boundary"}

    return {
        "state": "SPEC_INTEGRATED",
        "movie_executed": False,
        "executed_pulses": 0,
        "note": "Reel and deterministic source verified. This is a reference visor, not a feature-length execution.",
    }


def self_test():
    source = {
        "grid": [64, 64],
        "cells": 4096,
        "prng": "lcg",
        "lcg": {"a": 1664525, "c": 1013904223, "m": 4294967296, "seed": 7},
        "density_num": 30,
        "density_den": 100,
        "feature_length_pulses_declared": 129600,
        "fps": 24,
        "runtime_s_declared": 5400,
    }
    result = lcg_reference(source)
    assert result["state"] == "REFERENCE_SOURCE_VERIFIED", result
    assert result["live_cells"] == EXPECTED_LIVE_CELLS, result
    assert result["final_state"] == EXPECTED_FINAL_STATE, result
    assert result["prefix_bits"] == EXPECTED_PREFIX_BITS, result
    assert result["fps"] * result["runtime_s_declared"] == 129600, result
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the Muhlnickel film-organ reference")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--go", action="store_true", help="explicitly refused; this validator never pulses an organ")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    if args.go:
        print(json.dumps({
            "state": "REFUSED",
            "movie_executed": False,
            "executed_pulses": 0,
            "note": "--go is inert here; no organ pulse, titan write, mouth, destination, or frame was produced.",
        }, indent=2, sort_keys=True))
        return 1
    row = measure_root(args.root)
    verdict = classify(row)
    public_row = dict(row)
    public_row.pop("door", None)
    public_row.pop("card", None)
    print(json.dumps({"verdict": verdict, "row": public_row}, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "SPEC_INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
