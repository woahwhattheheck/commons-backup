"""Build a synthetic import-impact demonstration from the actual canonical mapper.

The output directory must not exist. The manifest is written last; a failed
write can leave an incomplete directory, never a claimed complete manifest.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

try:
    from .lodestone_adapter import load_module
except ImportError:
    from lodestone_adapter import load_module

HERE = Path(__file__).resolve().parent


def documents() -> tuple[dict, dict]:
    def row(kind, ident, namespace="register-a"):
        return {"namespace": namespace, "kind": kind, "id": ident, "revision": "r1",
                "synthetic": True, "payload": {"note": "Fictional " + kind + "; not a University finding"},
                "source_locators": ["synthetic-import-demo/" + namespace + "/" + kind + "/" + ident]}
    source = row("source", "SRC-1")
    observation = row("observation", "OBS-1")
    finding = row("finding", "FND-1")
    recommendation = row("recommendation", "REC-1")
    def select(record):
        return {key: record[key] for key in ("namespace", "kind", "id", "revision")}
    def link(name, origin, target):
        return {"link_id": name, "relation": "synthetic_demo_reference",
                "from": select(origin), "to": target,
                "note": "A declaration for demonstrating identity resolution, not support authority."}
    links = [link("qualified-source-stays-exact", finding, select(source)),
             link("same-label-needs-origin", observation, {"kind": "source", "id": "SRC-1"}),
             link("new-service-closes-gap", recommendation, select(row("service", "SVC-1", "services"))),
             link("missing-source-stays-visible", finding, {**select(source), "id": "NOT-SUPPLIED"})]
    before = {"schema": "uiowa.identity-map.v1", "synthetic_demo": True,
              "records": [source, observation, finding, recommendation], "links": links}
    after = deepcopy(before)
    after["records"] += [row("source", "SRC-1", "register-b"), row("service", "SVC-1", "services")]
    return before, after


def build(mapper_path: Path, expected_blob: str | None = None) -> tuple[dict[str, bytes], dict]:
    mapper, mapper_blob = load_module(mapper_path, "cirrus_import_demo_mapper", expected_blob)
    impact, impact_blob = load_module(HERE / "import_impact.py", "cirrus_import_impact")
    before_input, after_input = documents()
    before, after = mapper.reconcile(before_input), mapper.reconcile(after_input)
    comparison = impact.compare(before, after)
    def encode(value):
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    files = {"snapshot-before.json": encode(before), "snapshot-after.json": encode(after),
             "import-impact.json": encode(comparison),
             "import-impact.html": impact.render_html(comparison).encode("utf-8")}
    manifest = {"schema": "uiowa.identity-import-demo.v1", "synthetic": True,
                "assessment_authority": False, "mapper_git_blob_sha": mapper_blob,
                "impact_git_blob_sha": impact_blob, "expected_source_pin_checked": expected_blob is not None,
                "summary": comparison["summary"],
                "files": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                          for name, raw in sorted(files.items())}}
    files["manifest.json"] = encode(manifest)
    return files, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapper", type=Path, default=HERE.parent / "uiowa_rfq_18649_identity_map" / "identity_map.py")
    parser.add_argument("--expect-blob")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        files, manifest = build(args.mapper, args.expect_blob)
        args.output_dir.mkdir(parents=False, exist_ok=False)
        for name, raw in files.items():
            with (args.output_dir / name).open("xb") as stream:
                stream.write(raw)
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    except (OSError, ValueError, TypeError, ImportError, AttributeError) as exc:
        print("identity-import-demo: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
