"""Extract hash-pinned public Kaggriculture agents from Kaggle pull JSON.

The input JSON is downloaded in a separate network-enabled preparation step.
This program performs no network I/O and never executes notebook cells.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import zlib


SOURCES = {
    "kaito_v43": {
        "ref": "kaitofukami/103-128-fresh-public-v43-sparse-shop-hybrid",
        "author": "Kaito Fukami",
        "title": "103/128 Fresh Public | v43 Sparse Shop Hybrid",
        "version_number": 13,
        "script_version_id": 344404785,
        "notebook_sha256": "17006781a3cea5a36ac3c48cb491015d616dde847ff7302e205ed2aede931cf0",
        "assignment": "payload",
        "agent_sha256": "69f06a802b62aa08f28705dab5728eb924bb6a7c23ffe0164f65b104cc3dadf3",
        "agent_bytes": 63309,
    },
    "igor_multiroute": {
        "ref": "flexonafft/kaggriculture-multi-route-farming-agent",
        "author": "Igor Zharov",
        "title": "Kaggriculture | Multi-Route Farming Agent",
        "version_number": 84,
        "script_version_id": 343725556,
        "notebook_sha256": "50cc0b06b60f885d36b588609d6e7b165e96273625f4c57f402b9a3e13a570e6",
        "assignment": "SOURCE_B85",
        "agent_sha256": "8ac34abce129cf5c9456776c90edf7d2233b3a280bbdcf7622628825ef3669a0",
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"Notebook does not contain a literal {name} assignment")


def extract(pull_path: Path, key: str) -> tuple[bytes, dict]:
    expected = SOURCES[key]
    pull = json.loads(pull_path.read_text(encoding="utf-8"))
    metadata = pull.get("metadata", {})
    if metadata.get("ref") != expected["ref"]:
        raise ValueError(f"{key}: unexpected Kaggle ref")
    if metadata.get("currentVersionNumber") != expected["version_number"]:
        raise ValueError(f"{key}: notebook version changed; inspect and repin explicitly")
    raw_notebook = pull.get("blob", {}).get("sourceNullable")
    if not isinstance(raw_notebook, str):
        raise ValueError(f"{key}: missing notebook source")
    if digest(raw_notebook.encode()) != expected["notebook_sha256"]:
        raise ValueError(f"{key}: notebook bytes changed; inspect and repin explicitly")
    notebook = json.loads(raw_notebook)
    cells = [c.get("source", "") for c in notebook.get("cells", []) if c.get("cell_type") == "code"]
    cell = next((c for c in cells if expected["assignment"] in c), None)
    if cell is None:
        raise ValueError(f"{key}: extraction cell missing")
    packed = literal_assignment(cell, expected["assignment"])
    if not isinstance(packed, (str, bytes)):
        raise ValueError(f"{key}: encoded source is not text or bytes")
    agent = zlib.decompress(base64.b85decode(packed))
    if key == "igor_multiroute":
        agent.decode("utf-8")
    if digest(agent) != expected["agent_sha256"]:
        raise ValueError(f"{key}: extracted agent hash mismatch")
    if expected.get("agent_bytes") is not None and len(agent) != expected["agent_bytes"]:
        raise ValueError(f"{key}: extracted agent size mismatch")
    compile(agent, f"{key}.py", "exec")
    receipt = {k: expected[k] for k in ("ref", "author", "title", "version_number", "script_version_id",
                                        "notebook_sha256", "agent_sha256")}
    receipt["agent_bytes"] = len(agent)
    return agent, receipt


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.replace(path)


def prepare(inputs: dict[str, Path], output: Path) -> dict:
    receipts = {}
    for key in sorted(SOURCES):
        agent, receipt = extract(inputs[key], key)
        atomic_write(output / f"{key}.py", agent)
        receipts[key] = receipt
    manifest = {
        "schema_version": 1,
        "license": "Apache-2.0 (as recorded by the coordination source); upstream authors retain ownership",
        "agents": receipts,
    }
    atomic_write(output / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaito", type=Path, required=True, help="Kaggle pull JSON for the pinned Kaito notebook")
    parser.add_argument("--igor", type=Path, required=True, help="Kaggle pull JSON for the pinned Igor notebook")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare({"kaito_v43": args.kaito, "igor_multiroute": args.igor}, args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
