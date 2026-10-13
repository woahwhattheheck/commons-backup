#!/usr/bin/env python3
"""Paired larger-corpus measurement for the already-landed MixerLab codecs.

Downloads public enwik8, verifies the complete 100,000,000-byte member against
Matt Mahoney's published MD5/SHA-1, then benchmarks identical larger prefixes in
fresh processes. This file does not implement or tune a compressor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
import urllib.request
import zipfile

ENWIK8_URL = "https://www.mattmahoney.net/dc/enwik8.zip"
ENWIK8_BYTES = 100_000_000
ENWIK8_MD5 = "a1fa5ffddb56f4953e226637dabbb36a"
ENWIK8_SHA1 = "57b8363b814821dc9d47aa4d41f58733519076b2"
SCHEMA = "hutter-mixerlab-larger-corpus-paired/v1"
DEFAULT_PREFIXES = (65_536, 262_144)


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def parse_prefixes(text: str) -> tuple[int, ...]:
    values = tuple(int(part) for part in text.split(",") if part.strip())
    if not values or any(value <= 3_560 or value > ENWIK8_BYTES for value in values):
        raise ValueError("prefixes must be >3560 and <=100000000")
    if tuple(sorted(set(values))) != values:
        raise ValueError("prefixes must be strictly increasing and unique")
    return values


def source_accounting(root: Path) -> dict:
    mixer = root / "mixerlab.py"
    match = root / "match_model.py"
    baseline = mixer.stat().st_size
    candidate = baseline + match.stat().st_size
    return {
        "rule": (
            "source-byte proxy only: baseline counts UTF-8 mixerlab.py bytes; candidate "
            "counts mixerlab.py + match_model.py; benchmark/tests/docs are excluded; "
            "this is not official Hutter decompressor-archive accounting"
        ),
        "baseline_program_source_bytes": baseline,
        "candidate_program_source_bytes": candidate,
        "modules": {
            "mixerlab.py": {"bytes": baseline, "sha256": digest_file(mixer)},
            "match_model.py": {"bytes": match.stat().st_size, "sha256": digest_file(match)},
        },
    }


def fetch_verified_prefix(cache: Path, max_prefix: int) -> tuple[dict, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "enwik8.zip"
    prefix_path = cache / f"enwik8.prefix-{max_prefix}.bin"
    retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    urllib.request.urlretrieve(ENWIK8_URL, archive)

    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    total = kept = 0
    with zipfile.ZipFile(archive) as zf:
        if "enwik8" not in zf.namelist():
            raise RuntimeError("enwik8.zip missing enwik8 member")
        with zf.open("enwik8") as src, prefix_path.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)
                if kept < max_prefix:
                    piece = chunk[: max_prefix - kept]
                    dst.write(piece)
                    kept += len(piece)
    if total != ENWIK8_BYTES:
        raise RuntimeError(f"enwik8 size mismatch: {total}")
    if md5.hexdigest() != ENWIK8_MD5:
        raise RuntimeError("enwik8 MD5 mismatch")
    if sha1.hexdigest() != ENWIK8_SHA1:
        raise RuntimeError("enwik8 SHA-1 mismatch")
    if kept != max_prefix:
        raise RuntimeError("prefix extraction mismatch")
    return ({
        "url": ENWIK8_URL,
        "retrieved_at_utc": retrieved_at,
        "zip_bytes": archive.stat().st_size,
        "zip_sha256": digest_file(archive),
        "full_corpus_bytes": total,
        "full_corpus_md5": md5.hexdigest(),
        "full_corpus_sha1": sha1.hexdigest(),
        "full_corpus_sha256": sha256.hexdigest(),
    }, prefix_path)


def worker(variant: str, input_path: Path, prefix: int, table_bits: int, match_bits: int) -> dict:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import mixerlab
    import match_model

    data = input_path.read_bytes()[:prefix]
    input_sha = hashlib.sha256(data).hexdigest()
    t0 = time.perf_counter()
    if variant == "baseline":
        archive = mixerlab.compress_bytes(data, use_transform=True, table_bits=table_bits)
    elif variant == "candidate":
        archive = match_model.compress_bytes(data, use_transform=True, table_bits=table_bits, match_bits=match_bits)
    else:
        raise ValueError(f"unknown variant {variant!r}")
    t1 = time.perf_counter()
    decoded = (mixerlab.decompress_bytes(archive) if variant == "baseline"
               else match_model.decompress_bytes(archive))
    t2 = time.perf_counter()
    output_sha = hashlib.sha256(decoded).hexdigest()
    if decoded != data or output_sha != input_sha:
        raise RuntimeError(f"{variant} round-trip mismatch")
    rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return {
        "variant": variant,
        "input_bytes": len(data),
        "input_sha256": input_sha,
        "output_sha256": output_sha,
        "archive_bytes": len(archive),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "compress_seconds": round(t1 - t0, 6),
        "decompress_seconds": round(t2 - t1, 6),
        "codec_wall_seconds": round(t2 - t0, 6),
        "peak_rss_raw_linux_kib": rss_kib,
        "peak_rss_bytes_linux": rss_kib * 1024,
        "table_bits": table_bits,
        "match_bits": match_bits if variant == "candidate" else None,
        "wiki_transform": True,
        "roundtrip": True,
    }


def run_child(root: Path, variant: str, input_path: Path, prefix: int,
              table_bits: int, match_bits: int, timeout: int) -> dict:
    command = [
        sys.executable, str(root / "large_corpus_benchmark.py"), "_worker",
        "--variant", variant, "--input", str(input_path), "--prefix", str(prefix),
        "--table-bits", str(table_bits), "--match-bits", str(match_bits),
    ]
    result = subprocess.run(command, cwd=root, check=True, capture_output=True,
                            text=True, timeout=timeout)
    return json.loads(result.stdout)


def render_markdown(evidence: dict) -> str:
    accounting = evidence["source_accounting"]
    bsrc = accounting["baseline_program_source_bytes"]
    csrc = accounting["candidate_program_source_bytes"]
    lines = [
        "# Hutter MixerLab larger-corpus paired measurement", "",
        f"Operation: `{evidence['operation']}`", "",
        "This is a source-bound research measurement, **not** an official Hutter Prize score, record, readiness, submission, award, payment, or revenue claim.", "",
        f"Corpus: `{evidence['corpus']['url']}`. The full 100,000,000-byte enwik8 member was verified against published MD5 `{evidence['corpus']['full_corpus_md5']}` and SHA-1 `{evidence['corpus']['full_corpus_sha1']}` before prefix measurement.", "",
        "Program accounting: " + accounting["rule"], "",
        "| Input bytes | Baseline archive | Candidate archive | Archive delta | Baseline source-total | Candidate source-total | Total delta | Baseline wall s | Candidate wall s | Baseline peak RSS B | Candidate peak RSS B |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in evidence["pairs"]:
        b = pair["baseline"]
        c = pair["candidate"]
        btotal = b["archive_bytes"] + bsrc
        ctotal = c["archive_bytes"] + csrc
        lines.append(
            f"| {pair['input_bytes']} | {b['archive_bytes']} | {c['archive_bytes']} | "
            f"{c['archive_bytes'] - b['archive_bytes']:+d} | {btotal} | {ctotal} | "
            f"{ctotal - btotal:+d} | {b['codec_wall_seconds']:.6f} | {c['codec_wall_seconds']:.6f} | "
            f"{b['peak_rss_bytes_linux']} | {c['peak_rss_bytes_linux']} |"
        )
    lines += ["", "Every row uses identical input bytes and both variants reproduce the exact input SHA-256.", ""]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict:
    root = Path(__file__).resolve().parent
    prefixes = parse_prefixes(args.prefixes)
    corpus, input_path = fetch_verified_prefix(Path(args.cache), max(prefixes))
    accounting = source_accounting(root)
    pairs = []
    for prefix in prefixes:
        baseline = run_child(root, "baseline", input_path, prefix, args.table_bits,
                             args.match_bits, args.timeout_seconds)
        candidate = run_child(root, "candidate", input_path, prefix, args.table_bits,
                              args.match_bits, args.timeout_seconds)
        if baseline["input_sha256"] != candidate["input_sha256"]:
            raise RuntimeError("paired variants did not receive identical bytes")
        pairs.append({"input_bytes": prefix, "input_sha256": baseline["input_sha256"],
                      "baseline": baseline, "candidate": candidate})
    evidence = {
        "schema": SCHEMA,
        "operation": "HUTTER-MIXERLAB-LARGER-CORPUS-MEASURE-ZCRM3Q7-20260914",
        "original_owner": "Z-CantorRampart-0914-M3Q7 (ZCR-M3Q7) / GPT-5.6 Sol",
        "recovery_finalizer": "Z-BismuthSwitchback-1919-J8R6 (ZBS-J8R6) / GPT-5.6 Sol",
        "corpus": corpus,
        "source_accounting": accounting,
        "parameters": {"prefixes": list(prefixes), "table_bits": args.table_bits,
                       "match_bits": args.match_bits},
        "pairs": pairs,
        "truth_boundary": {"official_hutter_score": False, "record_claim": False,
                           "submission": False, "prize_or_payment_claim": False,
                           "new_compressor_model": False},
    }
    evidence["evidence_sha256"] = hashlib.sha256(canonical_json(evidence).encode()).hexdigest()
    return evidence


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--prefixes", default=",".join(str(x) for x in DEFAULT_PREFIXES))
    p.add_argument("--table-bits", type=int, default=12)
    p.add_argument("--match-bits", type=int, default=12)
    p.add_argument("--timeout-seconds", type=int, default=900)
    p.add_argument("--cache", default=".hutter-benchmark-cache")
    p.add_argument("--json-out", type=Path)
    p.add_argument("--markdown-out", type=Path)
    w = sub.add_parser("_worker")
    w.add_argument("--variant", choices=("baseline", "candidate"), required=True)
    w.add_argument("--input", type=Path, required=True)
    w.add_argument("--prefix", type=int, required=True)
    w.add_argument("--table-bits", type=int, default=12)
    w.add_argument("--match-bits", type=int, default=12)
    args = parser.parse_args(argv)
    if args.command == "_worker":
        print(canonical_json(worker(args.variant, args.input, args.prefix,
                                    args.table_bits, args.match_bits)))
        return 0
    evidence = run(args)
    rendered_json = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    rendered_md = render_markdown(evidence)
    if args.json_out:
        args.json_out.write_text(rendered_json, encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(rendered_md, encoding="utf-8")
    print("EVIDENCE_JSON=" + canonical_json(evidence))
    print(rendered_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
