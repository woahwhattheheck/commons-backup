#!/usr/bin/env python3
"""Transfer selected UIOWA synthetic CLI assets using the existing operator runner."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

from preflight import load_manifest, repo_root_from, validate

LANE = "revenue/uiowa_rfq_18649_operator_handoff"
PORTABILITY = "revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py"
MANIFEST = "SAMPLE-BUNDLE.json"
GUIDE = "START-HERE.md"
SCHEMA = "uiowa.sample-bundle.v1"


def primitives():
    """Reuse the original portability author's source/byte primitives unchanged."""
    path = repo_root_from() / PORTABILITY
    spec = importlib.util.spec_from_file_location("uiowa100_bundle_portability", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load portability helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_files(root: Path, selected: list[str], helper):
    manifest = load_manifest(root / LANE / "operator_manifest.json")
    closure = helper.strict_json(helper.read_member(root, f"{LANE}/bundle_inputs.json"))
    if closure.get("schema") != "uiowa.sample-bundle-inputs.v1":
        raise ValueError("unsupported bundle input map")
    assets = {a["asset_id"]: a for a in manifest["assets"] if a.get("sample_commands")}
    selected = sorted(set(selected or assets))
    if not selected or set(selected) - assets.keys():
        raise ValueError("--asset must name an executable operator-manifest asset")
    result = validate(manifest, root, set(selected))
    if not result["ok"]:
        raise ValueError("; ".join(result["errors"]))
    seeds = {PORTABILITY, *(f"{LANE}/{p}" for p in (
        "bundle.py", "bundle_inputs.json", "operator_manifest.json", "preflight.py",
        "sample_run.py", "100-operator-guide.md", "RUN_EVIDENCE_CONTRACT.md"))}
    for name in selected:
        asset, inputs = assets[name], closure["assets"].get(name)
        if not inputs or any(inputs.get(k) != asset[k] for k in ("working_dir", "sample_commands")):
            raise ValueError(f"{name}: command changed; update its explicit bundle input map")
        workdir = asset["working_dir"]
        seeds.add(asset["path"])
        seeds.update(f"{workdir}/{c[0]}" for c in asset["sample_commands"])
        seeds.update(f"{workdir}/{p}" for p in inputs["files"])
    files = helper.source_closure(root, tuple(sorted(seeds)))
    files[GUIDE] = guide(selected).encode("utf-8")
    return selected, files


def guide(selected):
    return f"""# UIOWA synthetic CLI sample kit

Selected assets: {', '.join(selected)}.

This archive contains the unchanged existing assessment tools, their explicitly
named synthetic inputs and flat local Python source closure. It uses the existing
UIOWA-100 preflight and sample runner. Original component attribution is retained.
Use Python 3.10+ on Linux cloud compute; no pip install or network is needed.
Native Windows/macOS and browser operation are not established by this bundle.

From this extracted directory, choose a fresh output directory outside the kit:

```sh
python3 {LANE}/bundle.py verify --root .
python3 {LANE}/bundle.py run --root . --out /tmp/uiowa-transferred-sample
```

The run command verifies the package bytes, then invokes the original sample runner
with exactly the selected assets. It preserves real exit codes, output hashes,
failure diagnostics and the distinction between PLANNED and executed work.
Read sample-run-receipt.json in the chosen output directory and the generated
reports. The handoff and outcome-measurement renderers write their complete
Markdown reports to output files. Remaining stdout-only validation messages are
retained as bounded excerpts in the existing receipt.

All data is fictional preparation, never University findings or completed work.
The public compiler retains UNTRUSTED_INSPECTION and its current authority ceiling.
Professional judgment, actual records, accepted scope and final delivery remain
engagement inputs. The six-stage guide is included for context; reference assets
outside this selected CLI package and an interactive workbench are not included.

SAMPLE-BUNDLE.json identifies actual file bytes and selected assets. Its revision
is an operator-supplied source label, not authenticated provenance. Keep the archive
digest independently when transferring. Byte verification is not a security audit
or validation of assessment meanings. Use only a trusted source kit; executing its
Python files is ordinary code execution, not a sandbox.
"""


def pack(root, output, revision, selected, helper):
    selected, files = selected_files(root, selected, helper)
    manifest = helper.source_manifest(files, revision)
    manifest.update(schema=SCHEMA, selected_assets=selected,
                    scope="selected synthetic operator CLI assets; not full engagement completion")
    members = {**files, MANIFEST: helper.canonical(manifest)}
    # Existing destinations survive; ZIP member order and timestamps are stable.
    with output.open("xb") as destination:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, raw in sorted(members.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, raw)
    return {"state": "PACKAGED", "selected_assets": selected, "files": len(files),
            "archive_sha256": helper.digest(output.read_bytes()), "archive": str(output)}


def verify(root, helper):
    manifest = helper.strict_json(helper.read_member(root, MANIFEST))
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or manifest.get("synthetic_only") is not True:
        raise ValueError("unsupported synthetic sample-bundle manifest")
    selected = manifest.get("selected_assets")
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) for x in selected):
        raise ValueError("bundle must record its selected assets")
    actual_selection, files = selected_files(root, selected, helper)
    if actual_selection != selected:
        raise ValueError("bundle selection must be sorted and unique")
    actual = helper.source_manifest(files, manifest.get("source_revision", ""))
    if actual["files"] != manifest.get("files"):
        raise ValueError("bundle source/input inventory or file bytes changed")
    if helper.read_member(root, GUIDE) != files[GUIDE]:
        raise ValueError("bundle start guide changed")
    return {"state": "BYTE_INTEGRITY_VERIFIED", "selected_assets": selected,
            "files": len(files), "source_revision": manifest["source_revision"],
            "source_authenticity_established": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pack", "verify", "run"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=repo_root_from())
        if name == "pack":
            command.add_argument("--asset", action="append", default=[])
            command.add_argument("--revision", required=True)
        if name != "verify":
            command.add_argument("--out", type=Path, required=True)
        if name == "run":
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        helper = primitives()
        root = args.root.resolve()
        if args.command == "pack":
            result = pack(root, args.out, args.revision, args.asset, helper)
        else:
            result = verify(root, helper)
        print(json.dumps(result, sort_keys=True), flush=True)
        if args.command == "run":
            command = [sys.executable, str(root / LANE / "sample_run.py"), "--root", str(root),
                       "--out", str(args.out.resolve()), "--timeout", str(args.timeout)]
            for asset in result["selected_assets"]:
                command += ["--asset", asset]
            if args.dry_run:
                command += ["--dry-run"]
            return subprocess.run(command, check=False).returncode
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
