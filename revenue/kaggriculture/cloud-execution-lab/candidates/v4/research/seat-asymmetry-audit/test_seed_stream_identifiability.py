#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("seedstream", HERE / "seed_stream_identifiability.py")
MOD = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None: raise RuntimeError("no loader")
SPEC.loader.exec_module(MOD)

def check(v, m="check failed"):
    if not v: raise AssertionError(m)

def raises(fragment, fn, *a, **kw):
    try: fn(*a, **kw)
    except MOD.EvidenceError as exc: check(fragment in str(exc), (fragment, str(exc)))
    else: raise AssertionError(f"expected {fragment!r}")

def farm(empty=None, post=None):
    t=[["LOCKED","LOCKED"],["LOCKED","LOCKED"]]
    if empty is not None:
        x,y=empty; t[y][x]=post
    return {"tiles":t}

def test_engine_contract_if_checkout_present():
    if MOD.DEFAULT_ENGINE.exists():
        ident=MOD.authenticate_engine(MOD.DEFAULT_ENGINE)
        check(ident["git_blob"] == MOD.ENGINE_GIT_BLOB)

def test_public_snapshot_bits():
    row=MOD.evidence_from_public_snapshots(day=2,
        farms_before=[farm((0,0),None),farm((1,1),None)],
        farms_after=[farm((0,0),{"kind":"WEED"}),farm((1,1),None)],
        shops_before=[],shops_after=["BAKERY"],board_size=2)
    check(row["empty_counts"]==(1,1)); check(row["weed_bits"]==(True,False)); check(row["appended_shop"]=="BAKERY")

def test_public_snapshot_rejects_nonweed_transition():
    raises("unexplained empty-tile transition", MOD.evidence_from_public_snapshots,
        day=0,farms_before=[farm((0,0),None),farm(None)],
        farms_after=[farm((0,0),{"kind":"PLANT"}),farm(None)],shops_before=[],shops_after=[],board_size=2)

def test_unlock_requires_append():
    raises("expected exactly one public shop append", MOD.normalize_evidence,
        {"day":2,"empty_counts":[0,0],"weed_bits":[],"shops_before":[],"shops_after":[]})

def test_offschedule_append_refuses():
    raises("outside authenticated draw schedule", MOD.normalize_evidence,
        {"day":0,"empty_counts":[0,0],"weed_bits":[],"shops_before":[],"shops_after":["BAKERY"]})

def test_cap_suppresses_draw():
    x=["BAKERY"]*8; row=MOD.normalize_evidence({"day":2,"empty_counts":[0,0],"weed_bits":[],"shops_before":x,"shops_after":x})
    check(row["appended_shop"] is None)

def test_bool_bits_strict():
    raises("literal booleans", MOD.normalize_evidence,
        {"day":0,"empty_counts":[1,0],"weed_bits":[0],"shops_before":[],"shops_after":[]})

def test_seed1_12bit_collapse():
    r=MOD.candidate_seeds_history(MOD.synthetic_history(1,days=3),seed_start=0,seed_stop=4096)
    check([x["candidate_count"] for x in r["survivor_counts"]]==[3190,15,1]); check(r["candidates"]==[1]); check(r["verdict"]=="BOUNDED_UNIQUE_NOT_GLOBAL")

def test_seed1_16bit_collapse():
    r=MOD.candidate_seeds_history(MOD.synthetic_history(1,days=3),seed_start=0,seed_stop=65536)
    check([x["candidate_count"] for x in r["survivor_counts"]]==[51083,205,1]); check(r["candidates"]==[1])

def test_hard_seed_remains_ambiguous():
    r=MOD.candidate_seeds_history(MOD.synthetic_history(255,days=6),seed_start=0,seed_stop=4096)
    check([x["candidate_count"] for x in r["survivor_counts"]]==[3190,2500,237,194,152,28]); check(255 in r["candidates"]); check(r["production_seed_cracker_authorized"] is False)

def test_reverse_history_refuses():
    h=MOD.synthetic_history(1,days=2)
    raises("contiguous", MOD.candidate_seeds_history,[h[1],h[0]],seed_start=0,seed_stop=16)

def test_skipped_day_refuses():
    h=MOD.synthetic_history(1,days=3)
    raises("contiguous", MOD.candidate_seeds_history,[h[0],h[2]],seed_start=0,seed_stop=16)

def test_shop_splice_refuses():
    h=MOD.synthetic_history(1,days=4); h[3]=dict(h[3]); h[3]["shops_before"]=[]
    raises("shop history changed", MOD.candidate_seeds_history,h,seed_start=0,seed_stop=16)

def test_wrong_shop_order_refuses():
    raises("authenticated sorted engine shop order", MOD.synthetic_history,1,days=1,shops=tuple(reversed(MOD.SHOP_NAMES)))

def test_no_match_explicit():
    r=MOD.candidate_seeds_history(MOD.synthetic_history(0,days=1),seed_start=1,seed_stop=2)
    check(r["verdict"]=="NO_MATCH_IN_BOUNDED_DOMAIN")

def test_consensus_refuses_guess():
    h=MOD.synthetic_history(1,days=4); r=MOD.candidate_seeds_history(h[:2],seed_start=0,seed_stop=4096)
    f=MOD.consensus_forecast(r["candidates"],day=2,empty_counts=h[2]["empty_counts"],shops_before=h[2]["shops_before"])
    check(r["candidate_count"]==15); check(f["full_public_signature_agrees"] is False); check(f["single_seed_guess_used"] is False)

def test_consensus_exact_after_bounded_unique():
    h=MOD.synthetic_history(1,days=4); r=MOD.candidate_seeds_history(h[:3],seed_start=0,seed_stop=4096)
    row=MOD.normalize_evidence(h[3]); f=MOD.consensus_forecast(r["candidates"],day=3,empty_counts=row["empty_counts"],shops_before=row["shops_before"])
    check(r["candidates"]==[1]); check((tuple(f["weed_bits"]),f["shop"])==(row["weed_bits"],row["appended_shop"])); check(f["global_identifiability_proved"] is False)

def test_duplicate_candidates_refuse():
    raises("unique", MOD.consensus_forecast,[1,1],day=0,empty_counts=[25,25],shops_before=[])

def test_run_non_authority():
    report=MOD.run(seed_start=0,seed_stop=4096,history=MOD.synthetic_history(1,days=3))
    check(report["bounded_search"]["candidates"]==[1]); check(report["decision_authority"] is False); check(report["runtime_mutation_authority"] is False); check(report["global_identifiability_proved"] is False)

def main():
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests: t()
    print(f"PASS {len(tests)}/{len(tests)} seed-stream-identifiability tests")
if __name__=="__main__": main()
