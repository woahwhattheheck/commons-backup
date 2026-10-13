"""Recover exact Git tree entries from retained bytes without provider writes."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
MODES = {b"40000": "tree", b"100644": "blob", b"100755": "blob",
         b"120000": "blob", b"160000": "commit"}
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 200000


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Expected an exact lowercase SHA-1")
    return value


def name(value):
    if not isinstance(value, str):
        raise ValueError("Entry name must be text")
    raw = value.encode("utf-8", "strict")
    if not raw or b"/" in raw or b"\0" in raw or raw in (b".", b".."):
        raise ValueError("Expected one immediate UTF-8 tree entry name")
    return raw


def tree_sha(raw):
    return hashlib.sha1(b"tree " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def order(item):
    key, (mode, _) = item
    return key + (b"/" if mode == b"40000" else b"")


def encode(entries):
    return b"".join(mode + b" " + key + b"\0" + bytes.fromhex(blob)
                    for key, (mode, blob) in sorted(entries.items(), key=order))


def decode(raw, expected_sha):
    if len(raw) > MAX_BYTES or tree_sha(raw) != sha(expected_sha):
        raise ValueError("Tree bytes exceed the bound or do not match the observed SHA")
    entries = {}
    pos = 0
    while pos < len(raw):
        space = raw.find(b" ", pos)
        nul = raw.find(b"\0", space + 1)
        if space < pos or nul < 0 or nul + 21 > len(raw):
            raise ValueError("Incomplete tree record")
        mode, key = raw[pos:space], raw[space + 1:nul]
        if mode not in MODES or name(key.decode("utf-8", "strict")) != key or key in entries:
            raise ValueError("Invalid mode, name or duplicate tree entry")
        entries[key] = (mode, raw[nul + 1:nul + 21].hex())
        pos = nul + 21
        if len(entries) > MAX_ENTRIES:
            raise ValueError("Tree entry bound exceeded")
    if encode(entries) != raw:
        raise ValueError("Tree records are not in canonical Git order")
    return entries


def recover(raw, base_tree_sha, target_tree_sha, patches, wanted):
    """Patches propose bytes; only the observed target SHA admits their result."""
    if not isinstance(wanted, list) or not 1 <= len(wanted) <= 1000:
        raise ValueError("Requested leaves must be a bounded nonempty list")
    if len({name(value) for value in wanted}) != len(wanted):
        raise ValueError("Duplicate requested leaf")
    entries = decode(raw, base_tree_sha)
    seen = set()
    if not isinstance(patches, list) or len(patches) > MAX_ENTRIES:
        raise ValueError("Patches must be a bounded list")
    for patch in patches:
        if not isinstance(patch, dict) or set(patch) - {"name", "sha", "mode", "delete"}:
            raise ValueError("Invalid patch fields")
        key = name(patch.get("name"))
        if key in seen:
            raise ValueError("Duplicate patch target")
        seen.add(key)
        if "delete" in patch and not isinstance(patch["delete"], bool):
            raise ValueError("delete must be boolean")
        if patch.get("delete"):
            if key not in entries or "sha" in patch or "mode" in patch:
                raise ValueError("Invalid removal proposal")
            del entries[key]
            continue
        mode = patch.get("mode")
        if mode is None:
            if key not in entries:
                raise ValueError("A new entry requires a proposed mode")
            mode = entries[key][0].decode("ascii")
        if not isinstance(mode, str) or mode.encode("ascii") not in MODES:
            raise ValueError("Invalid proposed mode")
        entries[key] = (mode.encode("ascii"), sha(patch.get("sha")))
    candidate = encode(entries)
    verified = decode(candidate, target_tree_sha)
    selected = []
    for value in wanted:
        key = name(value)
        entry = verified.get(key)
        if entry is None:
            selected.append({"name": value, "present": False})
        else:
            mode, blob = entry
            if mode not in (b"100644", b"100755"):
                raise ValueError("Requested leaf is not a regular file")
            selected.append({"name": value, "present": True, "mode": mode.decode("ascii"),
                             "type": "blob", "sha": blob})
    return {"schema": "commons.git_tree_preimage/v1", "status": "EXACT_TREE_PREIMAGE",
            "base_tree_sha": base_tree_sha, "tree_sha": target_tree_sha,
            "git_object_sha_verified": True, "complete_tree_bytes": True,
            "entries": len(verified), "bytes": len(candidate), "patches": len(patches),
            "leaves": selected}, candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-tree", required=True)
    parser.add_argument("--base-tree-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    parser.add_argument("--patches", help="Private JSON list of immediate-entry proposals")
    parser.add_argument("--leaf", action="append", required=True)
    parser.add_argument("--output-raw-tree", help="Optional new private file; existing files refused")
    args = parser.parse_args()
    try:
        with Path(args.raw_tree).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        patches = json.loads(Path(args.patches).read_text()) if args.patches else []
        proof, candidate = recover(raw, args.base_tree_sha, args.tree_sha, patches, args.leaf)
        if args.output_raw_tree:
            with Path(args.output_raw_tree).open("xb") as stream:
                stream.write(candidate)
        print(json.dumps(proof, sort_keys=True))
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, "Tree preimage refused: " + str(error) + "\n")


if __name__ == "__main__":
    main()
