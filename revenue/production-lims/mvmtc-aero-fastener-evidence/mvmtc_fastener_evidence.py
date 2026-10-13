"""Deterministic synthetic/read-only MVMTC fastener and additive-coupon evidence shadow."""
from __future__ import annotations

import copy, hashlib, json, re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

DEMAND_ID = "mvmtc-aero-fastener-evidence-lims-01"
PREFIX = "MVMTC-AERO-FASTENER-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "MISSING_PO_QUOTE_LINK", "DUPLICATE_CONTAINER", "METHOD_OUT_OF_SCOPE",
    "CHEMISTRY_MATERIAL_MISMATCH", "QC_FAIL",
)
METHOD_SPECS = (
    ("FASTENER_TENSILE", "A2LA-SIM-FASTENER", "CARBON_STEEL", "ASTM-F606M", "R3", "MPa"),
    ("FASTENER_HARDNESS", "A2LA-SIM-FASTENER", "ALLOY_STEEL", "ASTM-E18", "R2", "HRC"),
    ("CHEMISTRY", "A2LA-SIM-CHEMISTRY", "NICKEL_ALLOY", "ASTM-E1086", "R4", "mass_pct"),
    ("METALLOGRAPHY", "A2LA-SIM-METALLOGRAPHY", "TITANIUM_ALLOY", "ASTM-E3", "R2", "um"),
    ("ADDITIVE_COUPON_TENSILE", "A2LA-SIM-ADDITIVE", "TI6AL4V", "ASTM-E8", "R5", "MPa"),
)
RESERVED_REVIEWERS = {
    "", "auto", "automatic", "automation", "bot", "system", "scheduler", "agent",
    "ai", "service", "worker", "pipeline", "anonymous", "unknown",
}

class IntegrityError(ValueError):
    pass

def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha(v):
    return hashlib.sha256(v.encode("utf-8")).hexdigest()

def record_hash(r):
    return sha(canonical(r))

def manifest_envelope(m):
    keys = (
        "demand_id", "fixture_version", "dataset_sha256", "expanded_records_sha256",
        "record_count", "expected_ready", "expected_hold", "expected_hold_codes",
        "allowed_methods", "restricted_payload_fields",
    )
    return {k: m[k] for k in keys}

def verify_manifest_signature(m):
    if m.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature algorithm")
    if m.get("signature") != sha(PREFIX + canonical(manifest_envelope(m))):
        raise IntegrityError("manifest content-envelope signature mismatch")

def lineage_hashes(r):
    source = {k: r[k] for k in ("lot_id", "quote_id", "po_id", "container_id", "source_documents")}
    scope_method = {k: r[k] for k in ("route", "scope_id", "material_family", "method_id", "method_version")}
    specimen = {k: r[k] for k in ("lot_id", "container_id", "specimen_id", "material_family")}
    result = {k: r[k] for k in ("raw_value", "unit")}
    return {
        "source_sha256": sha(canonical(source)),
        "scope_method_sha256": sha(canonical(scope_method)),
        "specimen_sha256": sha(canonical(specimen)),
        "raw_value_unit_sha256": sha(canonical(result)),
    }

def rows_from_generator(compact):
    if compact.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    g = compact.get("generator")
    if not isinstance(g, dict) or (g.get("record_count"), g.get("clean_count")) != (100, 75):
        raise IntegrityError("fixture generator dimensions mismatch")
    holds = {}
    for seg in g.get("hold_segments", []):
        code, start, count = seg.get("code"), seg.get("start"), seg.get("count")
        if code not in HOLD_CODES or not isinstance(start, int) or not isinstance(count, int):
            raise IntegrityError("invalid HOLD segment")
        for off in range(count):
            n = start + off
            if n in holds or not 1 <= n <= 100:
                raise IntegrityError("overlapping or out-of-range HOLD segment")
            dup = None
            if code == "DUPLICATE_CONTAINER":
                ds = seg.get("duplicate_start")
                if not isinstance(ds, int):
                    raise IntegrityError("duplicate segment missing duplicate_start")
                dup = ds + off
            holds[n] = (code, dup)
    if set(holds) != set(range(76, 101)):
        raise IntegrityError("HOLD segments must cover exactly records 76..100")
    out = []
    for n in range(1, 101):
        hold, dup = holds.get(n, (None, None))
        identity = dup if dup is not None else n
        out.append([n, (identity - 1) % len(METHOD_SPECS), hold, dup])
    return out

def expand_row(row):
    if len(row) != 4:
        raise IntegrityError("fixture row width mismatch")
    n, idx, truth, dup = row
    if not isinstance(n, int) or not 1 <= n <= 100:
        raise IntegrityError("fixture row number out of range")
    try:
        route, scope_id, material, method_id, version, unit = METHOD_SPECS[idx]
    except (IndexError, TypeError):
        raise IntegrityError("fixture method index out of range") from None
    quote_id, po_id = f"MVMTC-Q-{n:04d}", f"MVMTC-PO-{n:04d}"
    container_n = dup if dup is not None else n
    if truth == "MISSING_PO_QUOTE_LINK":
        mode = (n - 76) % 3
        if mode in (0, 2): quote_id = ""
        if mode in (1, 2): po_id = ""
    elif truth == "METHOD_OUT_OF_SCOPE":
        scope_id, version = "OUT-OF-SCOPE-SIM", "UNAPPROVED"
    elif truth == "CHEMISTRY_MATERIAL_MISMATCH":
        material = "UNMATCHED_SYNTHETIC_MATERIAL"
    qc_ok = truth != "QC_FAIL"
    if unit == "HRC": raw = round(20 + (n % 30) * .5, 4)
    elif unit == "mass_pct": raw = round(.1 + (n % 17) * .03125, 6)
    elif unit == "um": raw = round(2.5 + (n % 11) * .2, 5)
    else: raw = round(350 + n * 2.75, 5)
    r = {
        "lot_id": f"MVMTC-LOT-{n:04d}", "quote_id": quote_id, "po_id": po_id,
        "container_id": f"MVMTC-C-{container_n:04d}", "specimen_id": f"MVMTC-S-{n:04d}",
        "route": route, "scope_id": scope_id, "material_family": material,
        "method_id": method_id, "method_version": version, "raw_value": raw, "unit": unit,
        "source_documents": [f"QUOTE:{n:04d}", f"PO:{n:04d}", f"COC:{n:04d}"],
        "qc_ok": qc_ok,
    }
    r.update(lineage_hashes(r)); r["truth_hold"] = truth
    return r

def verify_records(records, manifest):
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID or len(records) != manifest.get("record_count"):
        raise IntegrityError("manifest identity/count mismatch")
    ids = [r["lot_id"] for r in records]
    if len(ids) != len(set(ids)): raise IntegrityError("duplicate lot_id")
    if sha(canonical(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record-set hash mismatch")
    actual = Counter(r["truth_hold"] for r in records if r["truth_hold"] is not None)
    if actual != Counter(manifest["expected_hold_codes"]): raise IntegrityError("truth-set hold distribution mismatch")
    if len(records) - sum(actual.values()) != manifest["expected_ready"]: raise IntegrityError("truth-set ready count mismatch")
    restricted = set(manifest["restricted_payload_fields"])
    for r in records:
        if restricted.intersection(r): raise IntegrityError("restricted payload field present")
        for k, v in lineage_hashes(r).items():
            if r.get(k) != v: raise IntegrityError(f"lineage hash mismatch: {r['lot_id']} {k}")

def load_fixture(fixture_path=None, manifest_path=None):
    base = Path(__file__).resolve().parent / "fixtures"
    fp = Path(fixture_path) if fixture_path else base / "mvmtc_100_lots.json"
    mp = Path(manifest_path) if manifest_path else base / "manifest.json"
    text = fp.read_text(encoding="utf-8"); manifest = json.loads(mp.read_text(encoding="utf-8"))
    if sha(text) != manifest.get("dataset_sha256"): raise IntegrityError("dataset file hash mismatch")
    compact = json.loads(text)
    if compact.get("fixture_version") != manifest.get("fixture_version"): raise IntegrityError("fixture version mismatch")
    records = [expand_row(row) for row in rows_from_generator(compact)]
    verify_records(records, manifest)
    return records, manifest

def classify(r, seen, allowed):
    if not r["quote_id"] or not r["po_id"]: return "MISSING_PO_QUOTE_LINK"
    if r["container_id"] in seen: return "DUPLICATE_CONTAINER"
    c = allowed.get(r["route"])
    if c is None or any(r[k] != c[k] for k in ("scope_id", "method_id", "method_version", "unit")):
        return "METHOD_OUT_OF_SCOPE"
    if r["material_family"] != c["material_family"]: return "CHEMISTRY_MATERIAL_MISMATCH"
    if not r["qc_ok"]: return "QC_FAIL"
    return None

def _named_human(reviewer):
    if not isinstance(reviewer, str):
        raise ValueError("named human reviewer required")
    name = " ".join(reviewer.strip().split())
    tokens = re.findall(r"[^\W\d_]+", name.casefold())
    if len(tokens) < 2 or any(token in RESERVED_REVIEWERS for token in tokens):
        raise ValueError("named human reviewer required")
    return name

class MvmtcEvidenceShadow:
    def __init__(self, authoritative_state=None):
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._auth = sha(canonical(self.authoritative_state))
        self.lots, self.jobs, self.worksheets, self.evidence_packs, self.holds = {}, {}, {}, {}, {}
        self.events, self._seen_lots = [], set()
    def authoritative_fingerprint(self):
        current = sha(canonical(self.authoritative_state))
        if current != self._auth: raise IntegrityError("authoritative state changed inside read-only shadow")
        return current
    def state_digest(self):
        return sha(canonical({
            "lots": self.lots, "jobs": self.jobs, "worksheets": self.worksheets,
            "evidence_packs": self.evidence_packs, "holds": self.holds,
            "events": self.events, "seen_lots": sorted(self._seen_lots),
        }))
    def replay(self, records, manifest):
        verify_records(records, manifest); self.authoritative_fingerprint()
        seen = {x["container_id"] for x in self.lots.values()}
        ready = hold = replayed = 0; counts = Counter(); added = Counter(); outcomes = []
        for r in records:
            lid = r["lot_id"]
            if lid in self._seen_lots:
                replayed += 1; outcomes.append({"lot_id": lid, "status": "IDEMPOTENT_REPLAY", "record_sha256": record_hash(r)})
                continue
            code = classify(r, seen, manifest["allowed_methods"])
            if code != r["truth_hold"]: raise IntegrityError(f"truth/classifier mismatch for {lid}")
            self._seen_lots.add(lid)
            if code:
                hold += 1; counts[code] += 1
                self.holds[lid] = {"lot_id": lid, "hold_code": code, "record_sha256": record_hash(r), "worksheet_created": False, "evidence_pack_created": False}
                self.events.append({"lot_id": lid, "event": "HOLD", "hold_code": code, "record_sha256": record_hash(r)})
                added.update(holds=1, events=1); outcomes.append({"lot_id": lid, "status": "HOLD", "hold_code": code}); continue
            ready += 1; seen.add(r["container_id"])
            lin = {k: r[k] for k in ("source_sha256", "scope_method_sha256", "specimen_sha256", "raw_value_unit_sha256")}
            self.lots[lid] = {"lot_id": lid, "container_id": r["container_id"], "specimen_id": r["specimen_id"], "status": "READY", **lin}
            self.jobs[lid] = {"lot_id": lid, "route": r["route"], "scope_id": r["scope_id"], "method_id": r["method_id"], "method_version": r["method_version"], "status": "SIMULATED_COMPLETE", **lin}
            self.worksheets[lid] = {"lot_id": lid, "specimen_id": r["specimen_id"], "raw_value": r["raw_value"], "unit": r["unit"], "qc_ok": True, "status": "QC_ACCEPTED_FOR_REVIEW", **lin}
            self.evidence_packs[lid] = {"lot_id": lid, "status": "STAGED_HUMAN_REVIEW", "released_by": None, "release_event_sha256": None, **lin}
            self.events.append({"lot_id": lid, "event": "STAGED_HUMAN_REVIEW", "record_sha256": record_hash(r), **lin})
            added.update(lots=1, jobs=1, worksheets=1, evidence_packs=1, events=1); outcomes.append({"lot_id": lid, "status": "READY", "hold_code": None})
        self.authoritative_fingerprint()
        return SimpleNamespace(
            ready=ready, hold=hold, replayed=replayed, hold_counts=dict(sorted(counts.items())),
            lots_added=added["lots"], jobs_added=added["jobs"], worksheets_added=added["worksheets"],
            evidence_packs_added=added["evidence_packs"], holds_added=added["holds"], events_added=added["events"],
            state_digest=self.state_digest(), outcomes=outcomes,
        )
    def release_evidence_pack(self, lot_id, reviewer):
        name = _named_human(reviewer)
        pack = self.evidence_packs.get(lot_id)
        if pack is None: raise KeyError(lot_id)
        if pack["status"] != "STAGED_HUMAN_REVIEW": raise ValueError("evidence pack is not awaiting human review")
        payload = {"lot_id": lot_id, "event": "HUMAN_RELEASE", "reviewer": name, "prior_state_digest": self.state_digest()}
        event_sha = sha(canonical(payload)); pack["status"] = "RELEASED_HUMAN_REVIEW"; pack["released_by"] = name; pack["release_event_sha256"] = event_sha
        self.events.append({**payload, "event_sha256": event_sha}); return copy.deepcopy(pack)

def run_default():
    records, manifest = load_fixture(); shadow = MvmtcEvidenceShadow({"mode": "external-authoritative-read-only"})
    first = shadow.replay(records, manifest); before = first.state_digest; second = shadow.replay(records, manifest)
    return {
        "demand_id": DEMAND_ID, "ready": first.ready, "hold": first.hold, "hold_counts": first.hold_counts,
        "worksheets": len(shadow.worksheets), "staged_evidence_packs": sum(p["status"] == "STAGED_HUMAN_REVIEW" for p in shadow.evidence_packs.values()),
        "replay": {"replayed": second.replayed, "lots_added": second.lots_added, "jobs_added": second.jobs_added, "worksheets_added": second.worksheets_added, "evidence_packs_added": second.evidence_packs_added, "holds_added": second.holds_added, "events_added": second.events_added, "state_unchanged": before == second.state_digest},
        "release_policy": "NAMED_HUMAN_ONLY", "production_writes": 0, "controlled_payloads": 0,
    }

def main():
    print(json.dumps(run_default(), sort_keys=True, indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
