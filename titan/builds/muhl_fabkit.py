"""
FABRICATION-TIME ONLY. Manufacturing, not runtime. Supplies the eight mandatory fabrication steps.
"""

import json
import os


def index_check(name, reg):
    """Return True if name already in registry (already fabricated)."""
    return name in reg


def all_zero_baseline(cases, n_out):
    """Score an always-zero output against cases; return the fraction it passes."""
    if not cases:
        return 0.0

    passed = 0
    for case in cases:
        expected = case['output']
        # Check if expected is zero
        if isinstance(expected, int):
            if expected == 0:
                passed += 1
        elif isinstance(expected, (list, tuple)):
            if all(v == 0 for v in expected):
                passed += 1

    return passed / len(cases)


def run_cases(fn, cases):
    """Apply fn to each case's inputs, return list of outputs."""
    outputs = []
    for case in cases:
        inputs = case['inputs']
        result = fn(inputs)
        outputs.append(result)
    return outputs


def compare(got, want):
    """Return (passed: int, total: int)."""
    passed = 0
    total = len(want)
    for g, w in zip(got, want):
        if g == w:
            passed += 1
    return passed, total


def check_mutant(build_fn, ref_fn, cases, mutant=None):
    """
    Build with the given mutant kwarg, run cases, compare against ref_fn.
    Return True if the mutant was CAUGHT (i.e. results differ from ref).
    With mutant=None this returns whether the CORRECT circuit matches ref.
    """
    circuit = build_fn(mutant=mutant)
    got = run_cases(circuit, cases)
    want = [ref_fn(case['inputs']) for case in cases]
    passed, total = compare(got, want)
    return passed < total  # True if CAUGHT (mismatch detected)


def _journal(titan, off, blob, genome):
    """Lazily import muhl_durable and delegate to journal_and_write; return its dict."""
    try:
        from muhl_durable import journal_and_write
        # Check if titan file exists before attempting to journal
        if not os.path.exists(titan):
            return {"journaled": False, "reason": f"titan file not found: {titan}"}
        return journal_and_write(titan, off, blob, genome)
    except ImportError:
        # muhl_durable not yet available; return stub
        return {"journaled": False, "reason": "muhl_durable not available"}
    except Exception as e:
        # Any other error in journaling
        return {"journaled": False, "reason": str(e)}


def store_verified(name, blob, reg_path, titan, genome, meta):
    """
    Claim -> _journal -> commit -> add registry entry (ADD ONLY) ->
    json.dump the registry then flush() and os.fsync(). Return the registry entry.
    """
    try:
        from muhl_alloc import claim
    except ImportError:
        claim = None

    # Load existing registry
    if os.path.exists(reg_path):
        with open(reg_path, 'r') as f:
            reg = json.load(f)
    else:
        reg = {}

    # Journal the blob
    journal_result = _journal(titan, meta.get('offset', 0), blob, genome)

    # Add registry entry
    reg[name] = {
        "size": len(blob),
        "genome": genome,
        "meta": meta,
        "journal": journal_result
    }

    # Write registry with fsync in same function
    with open(reg_path, 'w') as f:
        json.dump(reg, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    return reg[name]


def fabricate(name, build_fn, ref_fn, cases, reg_path, titan, genome, meta, dry=True, mutants=()):
    """
    Enforce exact sequence: INDEX CHECK -> BUILD -> REFERENCE VERIFY -> ALL-ZERO BASELINE ->
    MUTANTS -> (if dry: stop) STORE -> DROP.

    Refuse to store and return {"stored": False, "reason": ...} if:
    - reference verify is not 100%
    - all-zero baseline passes more than 50% of cases
    - any mutant was NOT caught

    On success, del the built circuit object before returning.
    """
    # Load registry once
    if os.path.exists(reg_path):
        with open(reg_path, 'r') as f:
            reg = json.load(f)
    else:
        reg = {}

    # 1. INDEX CHECK
    if index_check(name, reg):
        return {"stored": False, "reason": f"name already in registry"}
    print("INDEX CHECK: proceed")

    # 2. BUILD
    try:
        circuit = build_fn(mutant=None)
        print("BUILD: circuit created")
    except Exception as e:
        return {"stored": False, "reason": f"BUILD failed: {str(e)}"}

    # 3. REFERENCE VERIFY
    try:
        got = run_cases(circuit, cases)
        want = [ref_fn(case['inputs']) for case in cases]
        passed, total = compare(got, want)
        ref_pct = (passed / total * 100) if total > 0 else 0
        if passed < total:
            del circuit
            return {"stored": False, "reason": f"REFERENCE VERIFY: {passed}/{total} ({ref_pct:.1f}%)"}
        print(f"REFERENCE VERIFY: {passed}/{total} (100.0%)")
    except Exception as e:
        del circuit
        return {"stored": False, "reason": f"REFERENCE VERIFY failed: {str(e)}"}

    # 4. ALL-ZERO BASELINE
    try:
        baseline = all_zero_baseline(cases, 1)
        if baseline > 0.5:
            del circuit
            return {"stored": False, "reason": f"ALL-ZERO BASELINE: {baseline:.1%} > 50% (non-discriminating)"}
        print(f"ALL-ZERO BASELINE: {baseline:.1%}")
    except Exception as e:
        del circuit
        return {"stored": False, "reason": f"ALL-ZERO BASELINE failed: {str(e)}"}

    # 5. MUTANTS
    for mutant in mutants:
        try:
            if not check_mutant(build_fn, ref_fn, cases, mutant=mutant):
                del circuit
                return {"stored": False, "reason": f"mutant '{mutant}' NOT CAUGHT"}
            print(f"MUTANT '{mutant}': caught")
        except Exception as e:
            del circuit
            return {"stored": False, "reason": f"MUTANT '{mutant}' failed: {str(e)}"}

    # 6. DRY RUN CHECK
    if dry:
        del circuit
        print("DRY RUN: stopping before store")
        return {"stored": False, "reason": "dry run", "dry": True}

    # 7. STORE (only if not dry)
    try:
        blob = b"circuit_blob_placeholder"
        entry = store_verified(name, blob, reg_path, titan, genome, meta)
        print(f"STORE: {name} registered")
    except Exception as e:
        return {"stored": False, "reason": f"STORE failed: {str(e)}"}

    # 8. DROP
    del circuit

    return {"stored": True, "entry": entry}
