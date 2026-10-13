#!/usr/bin/env python3
"""Fail-closed V218 current-native binding/equivalence audit.

This is read-only execution/custody tooling. It does not compose, activate, or run V218.
Executable V218/router token references remain visible diagnostics but do not establish a
root-reachable installation/use seam and therefore cannot mint wiring. Config-key presence and
inert source text are likewise diagnostic only. Native semantic equivalence counts as wired only
when the sole canonical V4 composition graph carries an authenticated evidence-only registration
for the exact live semantic source chain and this checker.
"""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

TOKENS = ("r04_full_router", "v218", "movement_parity")
EXCLUDE_PARTS = {"__pycache__", ".git"}
GRAPH_REL = Path("candidates/v4/COMPOSITION.json")
V218_COMPONENT_ID = "v218-native-movement-equivalence"
V218_PACKAGE = "repairs/gameplay/v218-legal-movement"
V218_CHECKER_REL = f"{V218_PACKAGE}/check_current_native_binding.py"
V218_RECEIPT_REL = f"{V218_PACKAGE}/NATIVE-SEMANTIC-EQUIVALENCE.json"
SEMANTIC_RULES = (
    "locked_transit_matches_engine",
    "all_four_shed_corners_eligible",
    "spatial_routes_are_tile_agnostic",
)
SEMANTIC_SOURCE_KEYS = ("main", "runtime", "frozen", "scheduler", "arlene", "spatial")
CONFIG_REL = "TITAN-CONFIG.json"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _token_hits(values) -> dict[str, int]:
    hits = {tok: 0 for tok in TOKENS}
    for value in values:
        if not isinstance(value, str):
            continue
        low = value.lower()
        for tok in TOKENS:
            hits[tok] += low.count(tok.lower())
    return hits


def _scan_text(path: Path, root: Path):
    """Raw token diagnostics only; these bytes never authorize explicit wiring."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    hits = _token_hits((text,))
    if not any(hits.values()):
        return None
    return {"path": str(path.relative_to(root)), "hits": hits}


def _scan_executable_python(path: Path, root: Path):
    """Collect Python identifier/import diagnostics without treating them as wiring proof.

    Comments, docstrings and arbitrary string constants are deliberately excluded. Import/name
    hits can live in unimported modules, dead branches, dead functions, or unused imports, so this
    scan is observability only. Root-reachable installation authority must come from the
    authenticated semantic-equivalence graph path.
    """
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except (UnicodeDecodeError, OSError, SyntaxError):
        return None
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                values.append(alias.name)
                if alias.asname:
                    values.append(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                values.append(node.module)
            for alias in node.names:
                values.append(alias.name)
                if alias.asname:
                    values.append(alias.asname)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            values.append(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            values.append(node.attr)
    hits = _token_hits(values)
    if not any(hits.values()):
        return None
    return {"path": str(path.relative_to(root)), "hits": hits}


def _read(root: Path, rel: str):
    path = root / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _function_node(text: str, name: str):
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise ValueError(f"missing function: {name}")


def _exec_function(text: str, name: str, globals_dict: dict):
    node = _function_node(text, name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    env = dict(globals_dict)
    exec(compile(module, f"<v218:{name}>", "exec"), env, env)
    return env[name], ast.get_source_segment(text, node) or ""


def _native_semantic_equivalence(root: Path, config: dict) -> dict:
    """Prove the two V218 legality rules already hold on the actually-called native path."""
    rels = {
        "main": "main.py",
        "runtime": "titan_runtime.py",
        "frozen": "frozen_selected.py",
        "scheduler": "scheduler.py",
        "arlene": "reference/next-panel/vendor/arlene.py",
        "spatial": "spatial_tempo.py",
    }
    texts = {name: _read(root, rel) for name, rel in rels.items()}
    missing = [rels[name] for name, text in texts.items() if text is None]
    if missing:
        return {"equivalent": False, "reason": "missing_semantic_sources", "missing": missing}

    chain = {
        "config_frozen": config.get("consumer") == "frozen",
        "config_nonterminal": not bool(config.get("terminal_route", False)),
        "main_calls_titan": (
            "from titan_runtime import TitanAgent, Features, load" in texts["main"]
            and "return FinalPressureAgent(" in texts["main"]
        ),
        "runtime_selects_frozen": (
            "from frozen_selected import FrozenSelected" in texts["runtime"]
            and "self.consumer = FrozenSelected()" in texts["runtime"]
        ),
        "frozen_imports_scheduler": "from scheduler import *" in texts["frozen"],
        "scheduler_binds_arlene": (
            "parent = _load('intact_arlene', HERE/'reference/next-panel/vendor/arlene.py')"
            in texts["scheduler"]
        ),
        "runtime_installs_spatial": (
            "from spatial_tempo import SpatialTempo" in texts["runtime"]
            and "self.spatial.install(self.controller)" in texts["runtime"]
        ),
    }

    try:
        moves = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
        noop, noop_src = _exec_function(
            texts["arlene"], "_noop",
            {"BOARD": 10, "MOVES": moves, "ANIMALS": {}},
        )
        shed_adjacent, shed_src = _exec_function(
            texts["arlene"], "_shed_adjacent", {"BOARD": 10}
        )
        path, path_src = _exec_function(texts["spatial"], "path", {})
        move, move_src = _exec_function(texts["spatial"], "move", {"MOVES": moves})

        locked_move = (
            noop(["EAST"], "LOCKED", {}, {}, 4, 4, 10) is False
            and noop(["WEST"], "LOCKED", {}, {}, 5, 5, 10) is False
            and noop(["EAST"], "LOCKED", {}, {}, 9, 4, 10) is True
        )
        four = {(4, 4), (5, 4), (4, 5), (5, 5)}
        shed_four = all(shed_adjacent(x, y, 10) for x, y in four)
        shed_exact = shed_four and not shed_adjacent(3, 4, 10) and not shed_adjacent(6, 5, 10)
        spatial_tile_agnostic = (
            "LOCKED" not in path_src
            and "LOCKED" not in move_src
            and path((4, 4), (5, 5)) == [["EAST"], ["SOUTH"]]
            and move((4, 4), ["EAST"], 10) == (5, 4)
        )
        arlene_move_branch_tile_agnostic = "if op in MOVES" in noop_src
        arlene_shed_source = "_shed_adjacent" in shed_src
    except (SyntaxError, ValueError, TypeError, KeyError, NameError) as exc:
        return {
            "equivalent": False,
            "reason": "semantic_probe_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "call_chain": chain,
        }

    rules = {
        "locked_transit_matches_engine": bool(locked_move and arlene_move_branch_tile_agnostic),
        "all_four_shed_corners_eligible": bool(shed_exact and arlene_shed_source),
        "spatial_routes_are_tile_agnostic": bool(spatial_tile_agnostic),
    }
    equivalent = all(chain.values()) and all(rules.values())
    return {
        "equivalent": equivalent,
        "reason": "native_semantic_equivalent" if equivalent else "semantic_precondition_failed",
        "call_chain": chain,
        "rules": rules,
        "sources": {
            name: {
                "path": rels[name],
                "git_blob": git_blob(texts[name].encode()),
                "sha256": sha256(texts[name].encode()),
            }
            for name in rels
        },
    }


def _pairs_no_dupes(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        out[key] = value
    return out


def _semantic_graph_registration(root: Path, semantic: dict, initial_config_raw: bytes) -> dict:
    """Authenticate graph/receipt custody against the same immutable proof inputs."""
    graph_path = root / GRAPH_REL
    if not graph_path.is_file():
        return {"registered": False, "reason": "missing_canonical_composition_graph", "path": str(GRAPH_REL)}
    try:
        graph = json.loads(
            graph_path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON: {value}")),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"registered": False, "reason": "invalid_canonical_composition_graph", "error": str(exc)}
    if not isinstance(graph, dict) or graph.get("schema") != "titan-v4-composition/v1":
        return {"registered": False, "reason": "wrong_canonical_composition_schema"}
    comps = graph.get("components")
    if not isinstance(comps, list):
        return {"registered": False, "reason": "composition_components_not_list"}
    matches = [c for c in comps if isinstance(c, dict) and c.get("id") == V218_COMPONENT_ID]
    if len(matches) != 1:
        return {"registered": False, "reason": "semantic_component_cardinality", "count": len(matches)}
    comp = matches[0]
    if comp.get("state") != "evidence_only":
        return {"registered": False, "reason": "semantic_component_not_evidence_only", "state": comp.get("state")}
    if comp.get("package") != V218_PACKAGE:
        return {"registered": False, "reason": "semantic_component_wrong_package", "package": comp.get("package")}
    if comp.get("transforms") != []:
        return {"registered": False, "reason": "semantic_component_must_not_transform"}
    if comp.get("entrypoints") != [V218_CHECKER_REL]:
        return {"registered": False, "reason": "semantic_component_wrong_entrypoint", "entrypoints": comp.get("entrypoints")}
    if comp.get("receipt") != V218_RECEIPT_REL:
        return {"registered": False, "reason": "semantic_component_wrong_receipt", "receipt": comp.get("receipt")}

    receipt_path = root / "candidates/v4" / V218_RECEIPT_REL
    checker_path = root / "candidates/v4" / V218_CHECKER_REL
    if not receipt_path.is_file():
        return {"registered": False, "reason": "registered_receipt_missing"}
    if not checker_path.is_file():
        return {"registered": False, "reason": "registered_checker_missing"}
    try:
        receipt = json.loads(
            receipt_path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON: {value}")),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"registered": False, "reason": "invalid_semantic_receipt", "error": str(exc)}
    if not isinstance(receipt, dict) or receipt.get("schema") != "titan-v4-v218-native-semantic-equivalence/v1":
        return {"registered": False, "reason": "wrong_semantic_receipt_schema"}
    if receipt.get("control_plane_disposition") != "evidence_only_no_transform_required":
        return {"registered": False, "reason": "semantic_receipt_wrong_disposition"}
    if receipt.get("runtime_promotion_authority") is not False or receipt.get("economic_authority") is not False:
        return {"registered": False, "reason": "semantic_receipt_claims_authority"}

    checker_blob = git_blob(checker_path.read_bytes())
    checker_row = receipt.get("semantic_checker")
    if not isinstance(checker_row, dict) or checker_row.get("path") != V218_CHECKER_REL:
        return {"registered": False, "reason": "semantic_receipt_wrong_checker_path"}
    if checker_row.get("git_blob") != checker_blob:
        return {
            "registered": False,
            "reason": "checker_identity_mismatch",
            "expected": checker_blob,
            "actual": checker_row.get("git_blob"),
        }

    source_identities = receipt.get("current_source_identities")
    if not isinstance(source_identities, dict):
        return {"registered": False, "reason": "semantic_source_identities_missing"}
    semantic_sources = semantic.get("sources")
    if not isinstance(semantic_sources, dict):
        return {"registered": False, "reason": "semantic_sources_missing"}
    expected: dict[str, str] = {}
    for key in SEMANTIC_SOURCE_KEYS:
        row = semantic_sources.get(key)
        if (
            not isinstance(row, dict)
            or type(row.get("path")) is not str
            or type(row.get("git_blob")) is not str
            or not row.get("path")
            or not row.get("git_blob")
        ):
            return {"registered": False, "reason": "semantic_source_receipt_missing", "source": key}
        rel = row["path"]
        if rel in expected:
            return {"registered": False, "reason": "duplicate_semantic_source_path", "source": key, "path": rel}
        expected[rel] = row["git_blob"]
    if CONFIG_REL in expected:
        return {"registered": False, "reason": "duplicate_semantic_source_path", "source": "config", "path": CONFIG_REL}
    expected[CONFIG_REL] = git_blob(initial_config_raw)

    if set(source_identities) != set(expected):
        return {
            "registered": False,
            "reason": "semantic_source_identity_set_mismatch",
            "expected_paths": sorted(expected),
            "actual_paths": sorted(source_identities),
        }
    if source_identities != expected:
        return {
            "registered": False,
            "reason": "semantic_source_identity_mismatch",
            "expected": expected,
            "actual": source_identities,
        }
    semantic_evidence = receipt.get("semantic_evidence")
    if not isinstance(semantic_evidence, dict) or semantic_evidence.get("frozen_nonterminal_config") is not True:
        return {"registered": False, "reason": "semantic_receipt_missing_frozen_config"}

    # Close the proof->registration TOCTOU: every source, including config, must
    # still be byte-identical after graph/receipt authentication.
    for rel, expected_blob in expected.items():
        path = root / rel
        try:
            actual_blob = git_blob(path.read_bytes())
        except OSError as exc:
            return {
                "registered": False,
                "reason": "semantic_source_changed_after_proof",
                "source": rel,
                "error": str(exc),
            }
        if actual_blob != expected_blob:
            return {
                "registered": False,
                "reason": "semantic_source_changed_after_proof",
                "source": rel,
                "expected": expected_blob,
                "actual": actual_blob,
            }

    return {
        "registered": True,
        "reason": "authenticated_evidence_only_semantic_edge",
        "component": V218_COMPONENT_ID,
        "receipt": V218_RECEIPT_REL,
        "checker_identity": checker_blob,
        "source_identities": expected,
    }


def audit(root: Path) -> dict:
    root = root.resolve()
    required = [root / "main.py", root / "titan_runtime.py", root / "TITAN-CONFIG.json"]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        raise ValueError(f"missing native package files: {missing}")

    config_raw = (root / CONFIG_REL).read_bytes()
    config = json.loads(config_raw)
    if type(config) is not dict:
        raise ValueError("TITAN-CONFIG.json must be an object")

    refs = []
    executable_refs = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in {"checks", "candidates"}:
            continue
        if path.suffix not in {".py", ".json"}:
            continue
        scanned += 1
        hit = _scan_text(path, root)
        if hit:
            refs.append(hit)
        if path.suffix == ".py":
            executable_hit = _scan_executable_python(path, root)
            if executable_hit:
                executable_refs.append(executable_hit)

    main = (root / "main.py").read_bytes()
    runtime = (root / "titan_runtime.py").read_bytes()
    config_v218_keys = sorted(
        k for k in config if "v218" in str(k).lower() or "movement_parity" in str(k).lower()
    )
    router_refs = sum(row["hits"]["r04_full_router"] for row in executable_refs)
    v218_refs = sum(row["hits"]["v218"] + row["hits"]["movement_parity"] for row in executable_refs)
    source_binding_diagnostic = bool(router_refs or v218_refs)
    explicit_binding = False
    semantic = _native_semantic_equivalence(root, config)
    equivalent = bool(semantic.get("equivalent"))
    registration = (
        _semantic_graph_registration(root, semantic, config_raw)
        if equivalent
        else {"registered": False, "reason": "semantic_equivalence_not_proven"}
    )
    semantic_wired = equivalent and bool(registration.get("registered"))
    wired = semantic_wired

    if semantic_wired:
        disposition = "NATIVE_SEMANTIC_EQUIVALENT_REQUIRES_RUNTIME_GATE"
    elif equivalent:
        disposition = "BLOCKED_AT_GRAPH_REGISTRATION"
    elif source_binding_diagnostic:
        disposition = "DIRECT_BINDING_UNVERIFIED"
    else:
        disposition = "BLOCKED_AT_NATIVE_ASSEMBLY"

    return {
        "schema": "titan-v4-v218-native-binding/v3",
        "native_root": str(root),
        "main": {"git_blob": git_blob(main), "sha256": sha256(main), "bytes": len(main)},
        "runtime": {"git_blob": git_blob(runtime), "sha256": sha256(runtime), "bytes": len(runtime)},
        "config": {
            "git_blob": git_blob(config_raw), "sha256": sha256(config_raw), "bytes": len(config_raw),
            "keys": sorted(config), "v218_keys": config_v218_keys,
        },
        "package_text_files_scanned": scanned,
        "binding_refs": refs,
        "source_binding_refs": executable_refs,
        "router_ref_count": router_refs,
        "v218_ref_count": v218_refs,
        "source_binding_diagnostic": source_binding_diagnostic,
        "explicit_binding": explicit_binding,
        "native_semantic_equivalence": semantic,
        "semantic_graph_registration": registration,
        "semantic_wired": semantic_wired,
        "wired": wired,
        "disposition": disposition,
        "scope": "binding/semantic custody only; no V218 execution or economics",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("native", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--require-wired", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = audit(args.native)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        ap.exit(2, f"v218-native-binding: {exc}\n")
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.require_wired and not report["wired"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())