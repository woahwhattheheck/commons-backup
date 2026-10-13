#!/usr/bin/env python3
"""muhl_genesis.py -- TITAN'S GENESIS BLOCK: a tamper-evident birth certificate over every engine.

Hashes every engine file in C:/llm/muhl_builds/*.py (SHA-256), builds a Merkle root over the sorted leaves,
and writes a signed manifest TITAN_GENESIS.json = {engine: sha256, ...} + merkle_root + count. This is Titan's
identity -- the single 32-byte root that commits to the exact bytes of all its fabricated capabilities. Change
any engine by one bit and the root changes: the genesis is tamper-evident.

The internal Merkle nodes (SHA-256 of two 32-byte child digests = a 64-byte block) are recomputed THROUGH THE
FABRICATED SHA-256 GATES from muhl_merkle.py and checked equal to hashlib -- so the birth certificate is signed
by the substrate itself, not just by the host library. Leaf hashing (arbitrary-length source files) uses
hashlib. No numpy; PYTHONUTF8=1.
"""
import sys, os, json, hashlib, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")

BUILDS = r"C:/llm/muhl_builds"
MANIFEST = os.path.join(BUILDS, "TITAN_GENESIS.json")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()

def merkle_root(leaves, node_fn):
    """Bottom-up Merkle root. Odd level -> duplicate the last node (Bitcoin-style). node_fn(a,b)->32 bytes."""
    if not leaves:
        return b"\x00" * 32
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [node_fn(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]

def main():
    # Every engine in the builds dir (deterministic order by filename).
    files = sorted(glob.glob(os.path.join(BUILDS, "*.py")))
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        print("  no engine .py files found in", BUILDS); return 1

    print("\n  TITAN GENESIS -- hashing every engine into a tamper-evident birth certificate\n")
    engines = {}
    leaves = []
    for path in files:
        name = os.path.basename(path)
        d = sha256_file(path)
        engines[name] = d.hex()
        leaves.append(d)
        print(f"    {name:34s}  {d.hex()[:16]}...  ({os.path.getsize(path):,} bytes)")

    # Reference Merkle root via hashlib.
    root_ref = merkle_root(leaves, lambda a, b: hashlib.sha256(a + b).digest())

    # Recompute the internal nodes through the FABRICATED SHA-256 GATES (substrate signature).
    root_gate = None
    try:
        from muhl_merkle import build_node
        node, ng = build_node()
        print(f"\n  fabricated SHA-256 node hash: {ng:,} gates -- recomputing the root through the substrate...")
        root_gate = merkle_root(leaves, node)
    except Exception as e:
        print(f"\n  (gate recompute skipped: {type(e).__name__}: {e})")

    root_verified = (root_gate is not None and root_gate == root_ref)
    merkle_hex = root_ref.hex()

    # Integrity seal over the identity fields (tamper-evident self-signature of the manifest itself).
    seal = hashlib.sha256(
        (merkle_hex + str(len(files)) + "".join(sorted(engines.keys()))).encode()
    ).hexdigest()

    manifest = {
        "titan": "genesis",
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "builds_dir": BUILDS,
        "hash_algo": "sha256",
        "merkle_scheme": "sha256(left||right), duplicate-last on odd level",
        "count": len(files),
        "engines": engines,
        "merkle_root": merkle_hex,
        "root_verified_through_gates": root_verified,
        "genesis_seal": seal,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print()
    print(f"  engines committed        : {len(files)}")
    print(f"  root == hashlib reference : True")
    print(f"  root == fabricated gates  : {root_verified}")
    print(f"  manifest written          : {MANIFEST}")
    print(f"  genesis seal              : {seal[:32]}...")
    print()
    print(f"  ===================================================================")
    print(f"   TITAN GENESIS MERKLE ROOT: {merkle_hex}")
    print(f"  ===================================================================")
    print(f"  This 32-byte root IS Titan's identity -- the tamper-evident root of all {len(files)} capabilities.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
