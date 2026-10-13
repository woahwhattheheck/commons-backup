#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("seeddomain", HERE / "seed_domain_provenance.py")
MOD = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None:
    raise RuntimeError("no loader")
SPEC.loader.exec_module(MOD)

SSPEC = importlib.util.spec_from_file_location("seedstream_fixture", HERE / "seed_stream_identifiability.py")
SS = importlib.util.module_from_spec(SSPEC)
if SSPEC.loader is None:
    raise RuntimeError("no seedstream loader")
SSPEC.loader.exec_module(SS)


def check(value, message="check failed"):
    if not value:
        raise AssertionError(message)


def raises(fragment, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except MOD.ProvenanceError as exc:
        check(fragment in str(exc), (fragment, str(exc)))
    else:
        raise AssertionError(f"expected ProvenanceError containing {fragment!r}")


def manifest(seeds):
    td = tempfile.TemporaryDirectory()
    path = Path(td.name) / "panel.json"
    sha = MOD.write_manifest(path, seeds)
    return td, path, sha


def test_validate_seed_set_strict():
    check(MOD.validate_seed_set([1, -2, 3]) == (1, -2, 3))
    raises("plain integer", MOD.validate_seed_set, [True])
    raises("plain integer", MOD.validate_seed_set, [1.0])
    raises("unique", MOD.validate_seed_set, [1, 1])
    raises("non-empty", MOD.validate_seed_set, [])


def test_manifest_roundtrip_and_authority():
    td, path, sha = manifest([1, 7, 255])
    try:
        bound = MOD.bind_panel_manifest(path, sha)
        check(bound["seeds"] == (1, 7, 255))
        check(bound["domain_kind"] == "BYTE_BOUND_DECLARED_OFFLINE_PANEL_SET_ONLY")
        check(bound["panel_precommit_proved"] is False)
        check(bound["panel_origin_authenticated"] is False)
        check(bound["finite_domain_authority_proved"] is False)
        check(bound["hosted_seed_domain_proved"] is False)
        check(bound["global_identifiability_proved"] is False)
    finally:
        td.cleanup()


def test_manifest_digest_tamper_refuses():
    td, path, sha = manifest([1, 7])
    try:
        path.write_text(path.read_text() + " ")
        raises("SHA-256 mismatch", MOD.bind_panel_manifest, path, sha)
    finally:
        td.cleanup()


def test_manifest_duplicate_json_key_refuses():
    td = tempfile.TemporaryDirectory(); path = Path(td.name) / "panel.json"
    raw = (b'{"schema":"titan.v4.byte-bound-offline-seed-panel/v1",'
           b'"seeds":[1],"seeds":[2],'
           b'"evaluator_git_blob":"' + MOD.EVALUATOR_GIT_BLOB.encode() + b'",'
           b'"engine_git_blob":"' + MOD.ENGINE_GIT_BLOB.encode() + b'",'
           b'"seedstream_git_blob":"' + MOD.SEEDSTREAM_GIT_BLOB.encode() + b'"}')
    path.write_bytes(raw); sha = hashlib.sha256(raw).hexdigest()
    try: raises("duplicate JSON key", MOD.bind_panel_manifest, path, sha)
    finally: td.cleanup()


def test_manifest_wrong_evaluator_refuses():
    td, path, _ = manifest([1])
    try:
        obj = json.loads(path.read_text()); obj["evaluator_git_blob"] = "0"*40
        raw = (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(raw); sha = hashlib.sha256(raw).hexdigest()
        raises("evaluator blob", MOD.bind_panel_manifest, path, sha)
    finally: td.cleanup()


def test_panel_filter_seed1_collapse():
    td, path, sha = manifest([1, 7, 255, 4095])
    try:
        result = MOD.filter_byte_bound_panel(SS.synthetic_history(1, days=3), path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
        check(result["candidates"] == [1])
        check(result["verdict"] == "DECLARED_PANEL_SET_UNIQUE_NOT_GLOBAL")
        check(result["global_identifiability_proved"] is False)
        check(result["production_seed_cracker_authorized"] is False)
    finally: td.cleanup()


def test_panel_filter_ambiguous_stays_set():
    td, path, sha = manifest([0, 2, 3, 4])
    try:
        result = MOD.filter_byte_bound_panel(SS.synthetic_history(0, days=1), path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
        check(0 in result["candidates"])
        check(result["candidate_count"] >= 1)
        if result["candidate_count"] > 1:
            check(result["verdict"] == "AMBIGUOUS_IN_DECLARED_PANEL_SET")
    finally: td.cleanup()


def test_panel_filter_no_match_explicit():
    td, path, sha = manifest([2])
    try:
        result = MOD.filter_byte_bound_panel(SS.synthetic_history(1, days=3), path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
        check(result["verdict"] == "NO_MATCH_IN_DECLARED_PANEL_SET")
    finally: td.cleanup()


def test_filter_rebinds_manifest_digest_every_call():
    td, path, sha = manifest([1, 7])
    try:
        path.write_text(path.read_text().replace("[1,7]", "[1,8]"))
        raises("SHA-256 mismatch", MOD.filter_byte_bound_panel, SS.synthetic_history(1, days=1), path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
    finally: td.cleanup()


def test_filter_rejects_bool_seed_from_bound_bytes():
    td, path, _ = manifest([1, 7])
    try:
        obj=json.loads(path.read_text()); obj["seeds"]=[1, True]
        raw=(json.dumps(obj,sort_keys=True,separators=(",", ":"))+"\n").encode(); path.write_bytes(raw)
        raises("plain integer", MOD.filter_byte_bound_panel, SS.synthetic_history(1, days=1), path, hashlib.sha256(raw).hexdigest(), seedstream_path=HERE / "seed_stream_identifiability.py")
    finally: td.cleanup()


def test_panel_consensus_no_guess_when_ambiguous():
    # Search a small panel for two seeds sharing day-0 public signature with seed 1.
    h = SS.synthetic_history(1, days=2)
    observed = SS.normalize_evidence(h[0])
    peers = [seed for seed in range(2, 500) if SS.signature(seed, observed) == (observed["weed_bits"], observed["appended_shop"])]
    check(peers, "need at least one day-0 collision")
    td, path, sha = manifest([1, peers[0]])
    try:
        filtered = MOD.filter_byte_bound_panel(h[:1], path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
        check(filtered["candidate_count"] == 2)
        row = SS.normalize_evidence(h[1])
        forecast = MOD.consensus_forecast_for_panel(h[:1], path, sha, day=1, empty_counts=row["empty_counts"], shops_before=row["shops_before"], seedstream_path=HERE / "seed_stream_identifiability.py")
        check(forecast["single_seed_guess_used"] is False)
        check(forecast["authority"] == "BYTE_BOUND_DECLARED_OFFLINE_PANEL_CONSENSUS_ONLY")
        check(forecast["global_identifiability_proved"] is False)
    finally: td.cleanup()


def test_panel_consensus_exact_after_unique():
    h = SS.synthetic_history(1, days=4)
    td, path, sha = manifest([1, 7, 255])
    try:
        filtered = MOD.filter_byte_bound_panel(h[:3], path, sha, seedstream_path=HERE / "seed_stream_identifiability.py")
        check(filtered["candidates"] == [1])
        row = SS.normalize_evidence(h[3])
        forecast = MOD.consensus_forecast_for_panel(h[:3], path, sha, day=3, empty_counts=row["empty_counts"], shops_before=row["shops_before"], seedstream_path=HERE / "seed_stream_identifiability.py")
        check((tuple(forecast["weed_bits"]), forecast["shop"]) == (row["weed_bits"], row["appended_shop"]))
        check(forecast["hosted_seed_domain_proved"] is False)
    finally: td.cleanup()


def test_seedstream_exec_uses_captured_bytes_without_reopen():
    td = tempfile.TemporaryDirectory()
    path = Path(td.name) / "seedstream.py"
    path.write_bytes((HERE / "seed_stream_identifiability.py").read_bytes())
    original = MOD._read_bound
    try:
        def capture_then_poison(target, expected, label):
            raw, blob = original(target, expected, label)
            Path(target).write_text("raise RuntimeError('reopened poisoned path')\n")
            return raw, blob
        MOD._read_bound = capture_then_poison
        loaded = MOD._load_seedstream(path)
        check(callable(loaded.signature))
        check(callable(loaded.consensus_forecast))
    finally:
        MOD._read_bound = original
        td.cleanup()


def test_source_contract_rejects_mutated_engine_if_checkout_present():
    paths = [MOD.DEFAULT_UTILS, MOD.DEFAULT_ENGINE, MOD.DEFAULT_ENGINE_CONFIG, MOD.DEFAULT_EVALUATOR, MOD.DEFAULT_SEEDSTREAM]
    if all(path.exists() for path in paths):
        td = tempfile.TemporaryDirectory()
        bad = Path(td.name) / "kaggriculture.py"
        try:
            bad.write_bytes(MOD.DEFAULT_ENGINE.read_bytes() + b"\n# drift\n")
            raises("official engine git blob mismatch", MOD.authenticate_source_contract, engine_path=bad)
        finally:
            td.cleanup()


def test_source_contract_if_checkout_present():
    paths = [MOD.DEFAULT_UTILS, MOD.DEFAULT_ENGINE, MOD.DEFAULT_ENGINE_CONFIG, MOD.DEFAULT_EVALUATOR, MOD.DEFAULT_SEEDSTREAM]
    if all(path.exists() for path in paths):
        report = MOD.authenticate_source_contract()
        check(report["source_blobs"]["engine"] == MOD.ENGINE_GIT_BLOB)
        check(report["implicit_fallback"]["start"] == 0)
        check(report["implicit_fallback"]["stop_exclusive"] == 2**31)
        check(report["explicit_config"]["complete_by_pinned_source"] is False)
        check(report["offline_evaluator"]["agent_seed_visibility"] is False)
        check(report["offline_evaluator"]["byte_binding_alone_proves_precommit"] is False)


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"PASS {len(tests)}/{len(tests)} seed-domain-provenance tests")


if __name__ == "__main__":
    main()
