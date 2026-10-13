#!/usr/bin/env python3
"""host/subzero_tech.py — SUBZERO PANEL 1/3 leftover.

Slack 1787645949.178889 (DEMON//REDTEAM, dispatch
demon-redteam-subzero-tech-ip-20260825-04): technical / IP /
validation inventory. Talk that lists archetypes, fabricators,
excerpts, or tests without this leftover is CLAIMED.

This leftover measures current main. It does not open titan.gguf.
It does not smash commons.mno. It does not remint the White Box
offer. It does not evaluate organs. It does not message buyers.

X = exact files in SEARCH_SPACE
Y = measured header / path / class bytes
Z = missing file / failed calibration / FINDER-FAILED
Calibration = known-present EXECUTE.md + SUBZERO_GRBN.md +
White Box offer_id must be found in the same run or the measure
is UNMEASURED. A miss prints FINDER-FAILED / FINDER-UNVERIFIED
plus the search space. Never 0.

  python3 host/subzero_tech.py
  python3 host/subzero_tech.py --root .
  python3 host/subzero_tech.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SUBZERO_TECH.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_TECH.md")
SLACK_TS = "1787645949.178889"
DISPATCH_ID = "demon-redteam-subzero-tech-ip-20260825-04"
WHITE_BOX_OFFER = "white-box-gguf-pilot-30d"
CLASSES = (
    "STRUCTURAL_ONLY",
    "CROSS_PROCESS/RUNTIME_MEASURED",
    "CUSTOMER_READY",
    "UNKNOWN",
)
TITAN_PRESENCE_PATHS = (
    "/llm/models/titan.gguf",
    r"C:\llm\models\titan.gguf",
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "subzero_tech.py"),
    os.path.join("ground", "SUBZERO_EXCERPTS.md"),
    os.path.join("ground", "SUBZERO_GRBN.md"),
    os.path.join("ground", "SUBZERO_CENSUS.md"),
    os.path.join("ground", "WORKING_BUILDS.md"),
    os.path.join("commercial.json"),
    os.path.join("excerpts", "20260823"),
    os.path.join("muhl", "desktop", "MUHL_SUBZERO_ARCHETYPES"),
    os.path.join("ground", "EXECUTE.md"),
    "titan.gguf",
    *TITAN_PRESENCE_PATHS,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "SUBZERO_GRBN.md"),
    os.path.join("commercial.json"),
)
PLUMB_ORGANS = (
    {"n": 1, "name": "muhl_hdvs", "magic": "MUHLHDVS", "n_gate": 12288, "card": "ground/SUBZERO_HDVS.md"},
    {"n": 2, "name": "muhl_sdmk", "magic": "MUHLSDMK", "n_gate": 24800, "card": "ground/SUBZERO_SDMK.md"},
    {"n": 3, "name": "muhl_hopf", "magic": "MUHLHOPF", "n_gate": 37248, "card": "ground/SUBZERO_HOPF.md"},
    {"n": 4, "name": "muhl_immn", "magic": "MUHLIMMN", "n_gate": 29951, "card": "ground/SUBZERO_IMMN.md"},
    {"n": 5, "name": "muhl_tset", "magic": "MUHLTSET", "n_gate": 23856, "card": "ground/SUBZERO_TSET.md"},
    {"n": 6, "name": "muhl_esnr", "magic": "MUHLESNR", "n_gate": 43044, "card": "ground/SUBZERO_ESNR.md"},
    {"n": 7, "name": "muhl_grbn", "magic": "MUHLGRBN", "n_gate": 8704, "card": "ground/SUBZERO_GRBN.md"},
    {"n": 8, "name": "muhl_socr", "magic": "MUHLSOCR", "n_gate": 15872, "card": "ground/SUBZERO_SOCR.md"},
    {"n": 9, "name": "muhl_stig", "magic": "MUHLSTIG", "n_gate": 15360, "card": "ground/SUBZERO_STIG.md"},
    {"n": 10, "name": "muhl_flow", "magic": "MUHLFLOW", "n_gate": 23040, "card": "ground/SUBZERO_FLOW.md"},
    {"n": 11, "name": "muhl_ispn", "magic": "MUHLISPN", "n_gate": 8784, "card": "ground/SUBZERO_ISPN.md"},
    {"n": 12, "name": "muhl_pots", "magic": "MUHLPOTS", "n_gate": 34304, "card": "ground/SUBZERO_POTS.md"},
    {"n": 13, "name": "muhl_petr", "magic": "MUHLPETR", "n_gate": 3552, "card": "ground/SUBZERO_PETR.md"},
    {"n": 14, "name": "muhl_pred", "magic": "MUHLPRED", "n_gate": 17664, "card": "ground/SUBZERO_PRED.md"},
    {"n": 15, "name": "muhl_rgcg", "magic": "MUHLRGCG", "n_gate": 7820, "card": "ground/SUBZERO_RGCG.md"},
    {"n": 16, "name": "muhl_synd", "magic": "MUHLSYND", "n_gate": 27520, "card": "ground/SUBZERO_SYND.md"},
    {"n": 17, "name": "muhl_pdap", "magic": "MUHLPDAP", "n_gate": 2656, "card": "ground/SUBZERO_PDAP.md"},
    {"n": 18, "name": "muhl_byzq", "magic": "MUHLBYZQ", "n_gate": 14880, "card": "ground/SUBZERO_BYZQ.md"},
    {"n": 19, "name": "muhl_lvin", "magic": "MUHLLVIN", "n_gate": 2368, "card": "ground/SUBZERO_LVIN.md"},
    {"n": 20, "name": "muhl_chimera_immn_hdvs", "magic": "MUHLCHIH", "n_gate": 20, "card": "ground/SUBZERO_CHIH.md"},
    {"n": 21, "name": "muhl_chimera_hopf_sdmk", "magic": "MUHLCHHS", "n_gate": 22, "card": "ground/SUBZERO_CHHS.md"},
    {"n": 22, "name": "muhl_chimera_tset_hdvs", "magic": "MUHLCHTH", "n_gate": 24, "card": "ground/SUBZERO_CHTH.md"},
    {"n": 23, "name": "muhl_chimera_grbn_socr", "magic": "MUHLCHGS", "n_gate": 20, "card": "ground/SUBZERO_CHGS.md"},
    {"n": 24, "name": "muhl_chimera_socr_stig", "magic": "MUHLCHSS", "n_gate": 18, "card": "ground/SUBZERO_CHSS.md"},
    {"n": 25, "name": "muhl_chimera_flow_stig", "magic": "MUHLCHFS", "n_gate": 18, "card": "ground/SUBZERO_CHFS.md"},
    {"n": 26, "name": "muhl_chimera_pots_dmb", "magic": "MUHLCHPD", "n_gate": 20, "card": "ground/SUBZERO_CHPD.md"},
    {"n": 27, "name": "muhl_chimera_pred_rgcg", "magic": "MUHLCHPR", "n_gate": 24, "card": "ground/SUBZERO_CHPR.md"},
    {"n": 28, "name": "muhl_chimera_lvin_synd", "magic": "MUHLCHLS", "n_gate": 22, "card": "ground/SUBZERO_CHLS.md"},
    {"n": 29, "name": "muhl_titanx_forge", "magic": "MUHLTITF", "n_gate": 180, "card": "ground/SUBZERO_TITF.md"},
    {"n": 30, "name": "muhl_titanx_mirror", "magic": "MUHLTITM", "n_gate": 240, "card": "ground/SUBZERO_TITM.md"},
    {"n": 31, "name": "muhl_titanx_commons", "magic": "MUHLTITX", "n_gate": 600, "card": "ground/SUBZERO_TITX.md"},
)
LIVE_TWELVE = (
    "muhl_palf",
    "muhl_nefg",
    "muhl_ardr",
    "muhl_vscf",
    "muhl_kegn",
    "muhl_nmpis",
    "muhl_awcg",
    "muhl_dmb",
    "muhl_cgat",
    "muhl_eal",
    "muhl_mha",
    "muhl_hpc",
)
ARCHETYPE_DIR = os.path.join("muhl", "desktop", "MUHL_SUBZERO_ARCHETYPES")
EXCERPT_DIR = os.path.join("excerpts", "20260823")


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _read_header(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            blob = handle.read(28)
            raw = handle.read()
    except OSError:
        return {"ok": False, "error": "FINDER-FAILED"}
    if len(blob) < 28:
        return {"ok": False, "error": "header shorter than 28", "bytes": len(blob)}
    magic = blob[:8].decode("ascii", "replace")
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<IIIII", blob, 8)
    full = blob + raw
    return {
        "ok": True,
        "magic": magic,
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "bytes": len(full),
        "sha256": hashlib.sha256(full).hexdigest(),
    }


def measure_titan_presence(root, isfile=os.path.isfile):
    """Measure bounded file presence without opening Titan or implying runtime."""
    paths = [os.path.join(root, "titan.gguf"), *TITAN_PRESENCE_PATHS]
    present = [path for path in paths if isfile(path)]
    return {
        "state": "PRESENT" if present else "FINDER-FAILED",
        "present_paths": present,
        "search_space": paths,
        "runtime_proof": False,
    }


def load_catalog(text):
    """Parse the SUBZERO tech catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    organs = []
    for item in data.get("organs") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if not name:
            continue
        organs.append(name)
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "white_box_offer": str(data.get("white_box_offer") or "").strip(),
        "refuse_remint_white_box": bool(data.get("refuse_remint_white_box", True)),
        "organs": organs,
        "error": "",
    }


def search_space():
    """Named search space for every miss. Never 0."""
    return list(SEARCH_SPACE)


def _runtime_receipt_ok(receipt):
    """Runtime requires a distinct cross-process receipt. Presence is not enough."""
    if not isinstance(receipt, dict):
        return False
    if receipt.get("kind") not in ("SUBZERO_RUNTIME_RECEIPT", "CROSS_PROCESS_RECEIPT"):
        return False
    if receipt.get("cross_process") is not True:
        return False
    pid = receipt.get("pid")
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    if not str(receipt.get("host") or "").strip():
        return False
    if receipt.get("login_required") or receipt.get("privileged_tier"):
        return False
    return True


def _buyer_pass_ok(receipt):
    """CUSTOMER_READY requires a bound buyer PASS. A flag is not enough."""
    if not isinstance(receipt, dict):
        return False
    if receipt.get("kind") not in ("SUBZERO_BUYER_VALIDATION", "BUYER_RECEIPT"):
        return False
    if receipt.get("status") != "PASS" or receipt.get("bound") is not True:
        return False
    if not str(receipt.get("buyer_id") or "").strip():
        return False
    if receipt.get("login_required") or receipt.get("privileged_tier"):
        return False
    return True


def classify_organ(facts):
    """One class per organ. Runtime is not inferred from a git file.

    Titan-file presence never escalates. evaluated / titan_remeasured
    flags without a distinct cross-process receipt stay STRUCTURAL_ONLY
    or UNKNOWN. CUSTOMER_READY requires a bound buyer PASS.
    """
    facts = facts or {}
    excerpt = bool(facts.get("excerpt"))
    fab = bool(facts.get("fab"))
    test = bool(facts.get("test"))
    header_ok = bool(facts.get("header_ok"))
    evaluated = bool(facts.get("evaluated"))
    customer = bool(facts.get("customer_ready"))
    titan_remeasured = bool(facts.get("titan_remeasured"))
    # Presence of titan.gguf or any checked-in file is not runtime.
    if facts.get("titan_file_present") and not _runtime_receipt_ok(facts.get("runtime_receipt")):
        titan_remeasured = False
        evaluated = False
    if (evaluated or titan_remeasured) and not _runtime_receipt_ok(facts.get("runtime_receipt")):
        evaluated = False
        titan_remeasured = False
    if customer and not _buyer_pass_ok(facts.get("buyer_receipt")):
        customer = False
    if customer and excerpt and header_ok:
        return "CUSTOMER_READY"
    if evaluated or titan_remeasured:
        return "CROSS_PROCESS/RUNTIME_MEASURED"
    if excerpt and header_ok and fab and test:
        return "STRUCTURAL_ONLY"
    if excerpt and header_ok:
        return "STRUCTURAL_ONLY"
    if fab and not excerpt:
        return "UNKNOWN"
    return "UNKNOWN"


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    organs = list(facts.get("organs") or [])
    classes = {}
    for item in organs:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        classes[name] = classify_organ(item)
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "plumb_count": int(facts.get("plumb_count") or 0),
        "excerpt_count": int(facts.get("excerpt_count") or 0),
        "fab_count": int(facts.get("fab_count") or 0),
        "test_count": int(facts.get("test_count") or 0),
        "structural_only": int(facts.get("structural_only") or 0),
        "runtime_measured": int(facts.get("runtime_measured") or 0),
        "customer_ready": int(facts.get("customer_ready") or 0),
        "unknown": int(facts.get("unknown") or 0),
        "titan_local": str(facts.get("titan_local") or "FINDER-FAILED"),
        "titan_presence_paths": list(facts.get("titan_presence_paths") or []),
        "titan_presence_search_space": list(
            facts.get("titan_presence_search_space") or []
        ),
        "titan_presence_is_runtime_proof": bool(
            facts.get("titan_presence_is_runtime_proof")
        ),
        "titan_write": str(facts.get("titan_write") or "NOT_WRITTEN"),
        "white_box_offer": str(facts.get("white_box_offer") or ""),
        "refuse_remint_white_box": bool(facts.get("refuse_remint_white_box", True)),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "missing_cards": list(facts.get("missing_cards") or []),
        "organ_classes": classes,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
        "search_space": list(facts.get("search_space") or search_space()),
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census SUBZERO artifacts."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
            "search_space": search_space(),
        }
    cal_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(cal_hits) == len(CALIBRATION)
    commercial = _read(root, "commercial.json")
    white_box = WHITE_BOX_OFFER in commercial
    titan_presence = measure_titan_presence(root)
    titan_local = titan_presence["state"]
    organs = []
    missing_cards = []
    structural_only = 0
    runtime_measured = 0
    customer_ready = 0
    unknown = 0
    excerpt_count = 0
    fab_count = 0
    test_count = 0
    for spec in PLUMB_ORGANS:
        stem = spec["name"][5:] if spec["name"].startswith("muhl_") else spec["name"]
        excerpt_rel = os.path.join(EXCERPT_DIR, spec["name"] + ".mno")
        fab_rel = os.path.join(ARCHETYPE_DIR, "muhl_fab_" + stem + ".py")
        test_rel = os.path.join(ARCHETYPE_DIR, "test_muhl_fab_" + stem + ".py")
        sidecar_rel = os.path.join(EXCERPT_DIR, stem + "_circuits.json")
        header = _read_header(root, excerpt_rel) if _exists(root, excerpt_rel) else {"ok": False}
        test_body = _read(root, test_rel)
        structural_test = (
            "Does not evaluate" in test_body
            or "never evaluates" in test_body
            or "Does not walk the organ" in test_body
            or "Structural tests" in test_body
        )
        card_ok = _exists(root, spec["card"])
        if not card_ok:
            missing_cards.append(spec["card"])
        row = {
            "n": spec["n"],
            "name": spec["name"],
            "magic": spec["magic"],
            "expected_n_gate": spec["n_gate"],
            "excerpt": _exists(root, excerpt_rel),
            "fab": _exists(root, fab_rel),
            "test": _exists(root, test_rel),
            "sidecar": _exists(root, sidecar_rel),
            "card": card_ok,
            "header_ok": (
                bool(header.get("ok"))
                and header.get("magic") == spec["magic"]
                and header.get("n_gate") == spec["n_gate"]
            ),
            "measured_n_gate": header.get("n_gate"),
            "measured_bytes": header.get("bytes"),
            "sha256": header.get("sha256") or "",
            "structural_test": structural_test,
            "evaluated": False,
            "titan_file_present": titan_local == "PRESENT",
            "titan_remeasured": False,
            "runtime_receipt": None,
            "buyer_receipt": None,
            "customer_ready": False,
        }
        if row["excerpt"]:
            excerpt_count += 1
        if row["fab"]:
            fab_count += 1
        if row["test"]:
            test_count += 1
        klass = classify_organ(row)
        row["class"] = klass
        if klass == "STRUCTURAL_ONLY":
            structural_only += 1
        elif klass == "CROSS_PROCESS/RUNTIME_MEASURED":
            runtime_measured += 1
        elif klass == "CUSTOMER_READY":
            customer_ready += 1
        else:
            unknown += 1
        organs.append(row)
    live_twelve = []
    for name in LIVE_TWELVE:
        stem = name[5:]
        fab_rel = os.path.join(ARCHETYPE_DIR, "muhl_fab_" + stem + ".py")
        excerpt_rel = os.path.join(EXCERPT_DIR, name + ".mno")
        live_twelve.append(
            {
                "name": name,
                "fab": _exists(root, fab_rel),
                "excerpt": _exists(root, excerpt_rel),
                "class": "UNKNOWN",
                "note": (
                    "public excerpt FINDER-FAILED. Prior owner-PC census "
                    "is a receipt, not this-run titan reopen. Organ not "
                    "evaluated."
                ),
            }
        )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG),
        "plumb_count": len(organs),
        "excerpt_count": excerpt_count,
        "fab_count": fab_count,
        "test_count": test_count,
        "structural_only": structural_only,
        "runtime_measured": runtime_measured,
        "customer_ready": customer_ready,
        "unknown": unknown,
        "titan_local": titan_local,
        "titan_presence_paths": titan_presence["present_paths"],
        "titan_presence_search_space": titan_presence["search_space"],
        "titan_presence_is_runtime_proof": titan_presence["runtime_proof"],
        "titan_write": catalog.get("titan") or "NOT_WRITTEN",
        "white_box_offer": WHITE_BOX_OFFER if white_box else "FINDER-FAILED",
        "refuse_remint_white_box": catalog.get("refuse_remint_white_box", True),
        "calibration_ok": calibration_ok,
        "calibration_hits": cal_hits,
        "missing_cards": missing_cards,
        "organs": organs,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "search_space": search_space(),
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["source_id"] = catalog.get("source_id") or DISPATCH_ID
    row["organs"] = organs
    row["live_twelve"] = live_twelve
    row["white_box_status"] = "PROPOSED" if white_box else "FINDER-FAILED"
    return row


def classify(row):
    """The leftover is INTEGRATED when the census names every PLUMB organ."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "SUBZERO tech catalog / tree listing not read. "
                "Absence was not stillness. Never 0."
            ),
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "calibration missed a known-present file. "
                "FINDER-UNVERIFIED. Search space: "
                + ", ".join(search_space())
                + ". Never 0."
            ),
        }
    if int(row.get("plumb_count") or 0) != 31:
        return {
            "state": "NOT_LANDED",
            "note": (
                "PLUMB organ count is not 31. FINDER-FAILED. "
                "Search space: excerpts/20260823 + "
                "muhl/desktop/MUHL_SUBZERO_ARCHETYPES. Never 0."
            ),
        }
    if not row.get("refuse_remint_white_box"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "refuse_remint_white_box is off. Do not remint "
                "white-box-gguf-pilot-30d."
            ),
        }
    if row.get("white_box_offer") != WHITE_BOX_OFFER:
        return {
            "state": "NOT_LANDED",
            "note": (
                "White Box offer_id FINDER-FAILED on commercial.json. "
                "Do not remint it. Search space includes commercial.json. "
                "Never 0."
            ),
        }
    if int(row.get("runtime_measured") or 0) != 0:
        return {
            "state": "NOT_LANDED",
            "note": (
                "this leftover claimed CROSS_PROCESS/RUNTIME_MEASURED "
                "without titan.gguf on this host. That is an overclaim. "
                "Git copies do not run."
            ),
        }
    if int(row.get("customer_ready") or 0) != 0:
        return {
            "state": "NOT_LANDED",
            "note": (
                "this leftover claimed CUSTOMER_READY for a Subzero organ. "
                "No organ SKU is paid or delivered. Do not remint White Box."
            ),
        }
    if int(row.get("structural_only") or 0) < 29:
        return {
            "state": "NOT_LANDED",
            "note": (
                "fewer than 29 PLUMB excerpts measured STRUCTURAL_ONLY. "
                "FINDER-FAILED. Search space: excerpts/20260823. Never 0."
            ),
        }
    missing = list(row.get("missing_cards") or [])
    titan_note = (
        "titan.gguf file presence was measured, but presence is not a gate "
        "walk, receiver result, or runtime proof."
        if row.get("titan_local") == "PRESENT"
        else "titan.gguf was FINDER-FAILED in the bounded presence search."
    )
    return {
        "state": "INTEGRATED",
        "note": (
            "SUBZERO PANEL 1/3 leftover is on this file. 31 PLUMB organs "
            "classified. Public excerpts are STRUCTURAL_ONLY. "
            + titan_note
            + " No organ is "
            "CUSTOMER_READY. Do not remint white-box-gguf-pilot-30d. "
            "Missing cards: "
            + (", ".join(missing) if missing else "none")
            + ". A Slack inventory is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure SUBZERO archetype / fab / excerpt / test inventory"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    try:
        with open(args.catalog, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        payload = {
            "measured": False,
            "error": str(exc),
            "state": "UNMEASURED",
            "note": "catalog missing. Absence was not stillness. Never 0.",
            "search_space": search_space(),
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    live = measure_from_rows(
        {
            "card_present": True,
            "catalog_present": True,
            "plumb_count": 31,
            "excerpt_count": 31,
            "fab_count": 31,
            "test_count": 31,
            "structural_only": 31,
            "runtime_measured": 0,
            "customer_ready": 0,
            "unknown": 0,
            "titan_local": "FINDER-FAILED",
            "titan_write": "NOT_WRITTEN",
            "white_box_offer": WHITE_BOX_OFFER,
            "refuse_remint_white_box": True,
            "calibration_ok": True,
            "calibration_hits": list(CALIBRATION),
            "missing_cards": ["ground/SUBZERO_CHPR.md", "ground/SUBZERO_CHLS.md"],
            "organs": [
                {
                    "name": "muhl_grbn",
                    "excerpt": True,
                    "fab": True,
                    "test": True,
                    "header_ok": True,
                }
            ],
        }
    )
    assert live["plumb_count"] == 31
    assert live["runtime_measured"] == 0
    assert live["customer_ready"] == 0
    assert live["organ_classes"]["muhl_grbn"] == "STRUCTURAL_ONLY"
    assert classify(live)["state"] == "INTEGRATED"
    overclaim = dict(live)
    overclaim["runtime_measured"] = 1
    assert classify(overclaim)["state"] == "NOT_LANDED"
    sold = dict(live)
    sold["customer_ready"] = 1
    assert classify(sold)["state"] == "NOT_LANDED"
    remint = dict(live)
    remint["refuse_remint_white_box"] = False
    assert classify(remint)["state"] == "NOT_LANDED"
    uncal = measure_from_rows({"plumb_count": 31, "calibration_ok": False})
    assert classify(uncal)["state"] == "UNMEASURED"
    catalog = load_catalog('{"not":"valid-shape"')
    assert catalog.get("error")
    assert classify_organ({"excerpt": True, "header_ok": True, "fab": True, "test": True}) == "STRUCTURAL_ONLY"
    assert classify_organ({"fab": True}) == "UNKNOWN"
    assert classify_organ(
        {
            "excerpt": True,
            "header_ok": True,
            "fab": True,
            "test": True,
            "titan_file_present": True,
            "titan_remeasured": True,
        }
    ) == "STRUCTURAL_ONLY"
    assert classify_organ(
        {
            "excerpt": True,
            "header_ok": True,
            "customer_ready": True,
        }
    ) == "STRUCTURAL_ONLY"
    return True


if __name__ == "__main__":
    sys.exit(main())
