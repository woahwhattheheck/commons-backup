"""Non-executing source/route comparison for TITAN opponent provenance.

SPDX-License-Identifier: Apache-2.0
Only the tool's decoding primitives run; inspected policies are never imported.
Overlap is evidence about source/data, not authorship or game equivalence.
"""
from __future__ import annotations

import argparse
import ast
import base64
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

MAX_SOURCE = 4 * 1024 * 1024
MAX_DECODED = 16 * 1024 * 1024
MAX_TURNS = 10000
SCHEMA = "titan.static-lineage.v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError(f"source exceeds {MAX_SOURCE} bytes: {path.name}")
    return data


def inflate(data: bytes) -> bytes:
    decoder = zlib.decompressobj()
    result = decoder.decompress(data, MAX_DECODED + 1)
    if len(result) > MAX_DECODED or decoder.unconsumed_tail:
        raise ValueError("compressed literal exceeds decoded-size limit")
    if not decoder.eof or decoder.unused_data:
        raise ValueError("truncated or concatenated compressed literal")
    return result


def data_value(node: ast.AST, literals: dict, depth: int = 0):
    """Interpret only literal data and named stdlib data encodings, never eval."""
    if depth > 30:
        raise ValueError("literal expression nesting limit")
    if isinstance(node, ast.Name) and node.id in literals:
        return literals[node.id]
    if not isinstance(node, ast.Call):
        return ast.literal_eval(node)
    if node.keywords:
        raise ValueError("unsupported decoder keyword arguments")
    if (isinstance(node.func, ast.Attribute) and node.func.attr == "decode"
            and not isinstance(node.func.value, ast.Name)):
        value = data_value(node.func.value, literals, depth + 1)
        encoding = ast.literal_eval(node.args[0]) if node.args else "utf-8"
        if len(node.args) > 1 or encoding not in ("utf-8", "utf8", "ascii") or not isinstance(value, bytes):
            raise ValueError("unsupported bytes decoding convention")
        return value.decode(encoding)
    if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
            and len(node.args) == 1):
        raise ValueError("not a supported literal data decoder")
    name = node.func.value.id + "." + node.func.attr
    if name not in {"json.loads", "zlib.decompress", "base64.b64decode", "base64.b85decode"}:
        raise ValueError("not a supported literal data decoder")
    value = data_value(node.args[0], literals, depth + 1)
    if name == "json.loads":
        if not isinstance(value, (str, bytes)) or len(value) > MAX_DECODED:
            raise ValueError("invalid JSON literal input")
        return json.loads(value)
    if name == "zlib.decompress":
        if not isinstance(value, bytes):
            raise ValueError("compressed literal is not bytes")
        return inflate(value)
    if not isinstance(value, (str, bytes)):
        raise ValueError("base encoded literal is not text/bytes")
    return (base64.b64decode(value, validate=True) if name.endswith("b64decode")
            else base64.b85decode(value))


def is_route(value) -> bool:
    return (isinstance(value, list) and 0 < len(value) <= MAX_TURNS
            and all(isinstance(a, dict) and all(k in a for k in ("farmer", "hands", "market"))
                    and isinstance(a["farmer"], list) and isinstance(a["hands"], list)
                    and isinstance(a["market"], list) for a in value))


def routes_from_data(value, prefix="data", depth=0) -> dict:
    if depth > 20:
        raise ValueError("route data nesting limit")
    if is_route(value):
        return {prefix: value}
    # Arlene's published full route + ordered (parent, at, suffix) representation.
    if isinstance(value, dict) and {"main", "full", "tails"} <= value.keys():
        if not isinstance(value["main"], str) or not is_route(value["full"]) or not isinstance(value["tails"], list):
            raise ValueError("invalid full/tails route pack")
        out = {value["main"]: value["full"]}
        for tail in value["tails"]:
            if not isinstance(tail, dict) or not {"h", "parent", "at", "suffix"} <= tail.keys():
                raise ValueError("invalid tail record")
            key, parent, start = tail["h"], tail["parent"], tail["at"]
            if (not isinstance(key, str) or key in out or not isinstance(parent, str)
                    or parent not in out or type(start) is not int
                    or not 0 <= start <= len(out[parent]) or not is_route(tail["suffix"])):
                raise ValueError("unresolved/duplicate parent or invalid tail boundary")
            route = out[parent][:start] + tail["suffix"]
            if not is_route(route):
                raise ValueError("invalid reconstructed route")
            out[key] = route
        return {prefix + "/" + key: route for key, route in out.items()}
    out = {}
    children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
    for key, child in children:
        out.update(routes_from_data(child, prefix + "/" + str(key), depth + 1))
    return out


class WithoutDocstrings(ast.NodeTransformer):
    def visit(self, node):
        node = super().visit(node)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:]
        return node


def python_profile(text: str) -> tuple[dict, dict, dict]:
    tree = ast.parse(text)
    literals, routes, diagnostics = {}, {}, []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        literals[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError, SyntaxError, RecursionError):
                        pass
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "json"
                and node.func.attr == "loads"):
            try:
                data = data_value(node, literals)
                found = routes_from_data(data, f"json@{node.lineno}")
                routes.update(found)
            except (ValueError, TypeError, SyntaxError, zlib.error, UnicodeError, RecursionError) as exc:
                diagnostics.append({"line": node.lineno, "decoder": "json.loads", "error": type(exc).__name__})
    for name, value in literals.items():
        if isinstance(value, (dict, list)):
            try:
                routes.update(routes_from_data(value, "literal/" + name))
            except (ValueError, TypeError, RecursionError) as exc:
                diagnostics.append({"literal": name, "error": type(exc).__name__})
    imports = sorted({(n.module or "") if isinstance(n, ast.ImportFrom) else a.name
                      for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                      for a in n.names})
    tree = WithoutDocstrings().visit(tree)
    profile = {"ast_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
               "imports": imports, "diagnostics": diagnostics}
    return profile, routes, literals


def native_tapes(text: str, symbols: dict) -> dict:
    """Decode Apex's textual numeric tape format using its supplied symbol tables.

    Conversion mirrors published main.py::_unit_order/_market_order. Native policy
    execution and dynamic overlays are deliberately outside this representation.
    """
    turns_m = re.search(r"\bkTurns\s*=\s*(\d+)\s*;", text)
    routes_m = re.search(r"\bkRoutes\s*=\s*(\d+)\s*;", text)
    array_m = re.search(r"\bkEncodedTapes\s*\[[^]]+\]\s*\[[^]]+\]\s*=\s*\{(.*?)\};", text, re.S)
    if not (turns_m and routes_m and array_m):
        raise ValueError("unsupported native tape declaration")
    turns, count = int(turns_m[1]), int(routes_m[1])
    if not 0 < turns <= MAX_TURNS or not 0 < count <= 32:
        raise ValueError("native tape dimensions out of bounds")
    strings = re.findall(r'"([^"\\]*)"', array_m[1])
    residue = re.sub(r'"[^"\\]*"', "", array_m[1])
    if residue.strip(" \r\n\t{},") or len(strings) != turns * count:
        raise ValueError("native tape string count/initializer mismatch")
    units, markets, items = (symbols[k] for k in ("_UNIT_OPS", "_MARKET_OPS", "_ITEMS"))
    if not all(isinstance(table, (list, tuple)) and table and all(isinstance(v, str) for v in table)
               for table in (units, markets, items)):
        raise ValueError("invalid native symbol table")
    decoded = []
    for encoded in strings:
        if not re.fullmatch(r"[\s+\-0-9]+", encoded):
            raise ValueError("native tape contains noninteger data")
        values = list(map(int, encoded.split()))
        if len(values) < 2:
            raise ValueError("missing native action counts")
        nu, nm = values[:2]
        if not 1 <= nu <= 40 or not 0 <= nm <= 16 or len(values) != 2 + 3 * (nu + nm):
            raise ValueError("invalid native action counts")
        orders, market = [], []
        for i in range(nu + nm):
            op, arg, qty = values[2 + 3*i:5 + 3*i]
            if i < nu:
                if not 0 <= op < len(units):
                    raise ValueError("invalid native unit opcode")
                name = units[op]
                order = [name]
                if name in {"PLANT", "PICKUP", "PLACE"}:
                    if not 0 <= arg < len(items):
                        raise ValueError("invalid native unit item")
                    order += [items[arg]] + ([] if qty == 1 else [qty])
                orders.append(order)
            else:
                if not 0 <= op < len(markets):
                    raise ValueError("invalid native market opcode")
                name = markets[op]
                if name == "PASS":
                    continue
                if name in {"HIRE", "BUY_LAND"}:
                    market.append([name])
                else:
                    if not 0 <= arg < len(items):
                        raise ValueError("invalid native market item")
                    market.append([name, items[arg], qty])
        decoded.append({"farmer": orders[0], "hands": orders[1:], "market": market})
    return {f"native/{i}": decoded[i*turns:(i+1)*turns] for i in range(count)}


def inspect_bundle(spec: dict, base_dir: Path) -> tuple[dict, dict]:
    label = spec["id"]
    if "missing" in spec:
        return {"id": label, "status": "missing", "reason": spec["missing"],
                "provenance": spec.get("provenance", {})}, {}
    root = (base_dir / spec.get("root", ".")).resolve()
    files, routes, texts, symbols = [], {}, {}, {}
    names = spec.get("files")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names) or len(set(names)) != len(names):
        raise ValueError(f"{label}: files must be a nonempty unique list")
    for name in names:
        raw = read_bounded(root / name)
        record = {"path": name, "bytes": len(raw), "sha256": digest(raw)}
        if name.endswith(".py"):
            try:
                profile, found, table = python_profile(raw.decode("utf-8"))
                record.update(profile)
                routes.update({name + ":" + k: v for k, v in found.items()})
                symbols[name] = table
            except (SyntaxError, UnicodeError, ValueError, RecursionError) as exc:
                record["parse_error"] = type(exc).__name__
        texts[name] = raw
        files.append(record)
    if "native_tapes" in spec:
        config = spec["native_tapes"]
        try:
            found = native_tapes(texts[config["tape"]].decode("utf-8"), symbols[config["symbols"]])
            routes.update({config["tape"] + ":" + k: v for k, v in found.items()})
        except (KeyError, ValueError, UnicodeError, TypeError) as exc:
            files.append({"native_tape_error": type(exc).__name__, "detail": str(exc)})
    evidence = []
    for name in spec.get("evidence", []):
        raw = read_bounded(root / name)
        evidence.append({"path": name, "sha256": digest(raw), "bytes": len(raw)})
    result = {"id": label, "status": "inspected", "provenance": spec.get("provenance", {}),
              "files": files, "evidence": evidence,
              "routes": [{"id": k, "turns": len(v), "sha256": digest(canonical(v))}
                         for k, v in sorted(routes.items())]}
    return result, routes


def route_overlap(left: list, right: list) -> dict:
    """Exact same-index JSON equality; no implicit default normalization."""
    common = min(len(left), len(right))
    equal = [left[i] == right[i] for i in range(common)]
    unequal = [i for i, same in enumerate(equal) if not same]
    prefix = next((i for i, same in enumerate(equal) if not same), common)
    maximum = current = 0
    for same in equal:
        current = current + 1 if same else 0
        maximum = max(maximum, current)
    return {"candidate_turns": len(left), "reference_turns": len(right), "aligned_turns": common,
            "identical_full_route": len(left) == len(right) and all(equal),
            "equal_actions": sum(equal), "equal_prefix_turns": prefix,
            "longest_equal_run": maximum, "candidate_only_turns": len(left)-common,
            "reference_only_turns": len(right)-common,
            "unit_equal_turns": sum((left[i]["farmer"], left[i]["hands"]) ==
                                    (right[i]["farmer"], right[i]["hands"]) for i in range(common)),
            "market_equal_turns": sum(left[i]["market"] == right[i]["market"] for i in range(common)),
            "first_differing_steps": unequal[:20]}


def compare_manifest(manifest: dict, base_dir: Path | str = ".") -> dict:
    specs = [manifest["candidate"], *manifest["references"]]
    labels = [s["id"] for s in specs]
    if any(not isinstance(x, str) or not x for x in labels) or len(set(labels)) != len(labels):
        raise ValueError("bundle ids must be distinct nonempty strings")
    profiles = [inspect_bundle(s, Path(base_dir)) for s in specs]
    candidate, croutes = profiles[0]
    if candidate["status"] != "inspected":
        raise ValueError("candidate source is missing")
    comparisons = []
    for reference, rroutes in profiles[1:]:
        row = {"reference": reference["id"], "status": reference["status"]}
        if reference["status"] == "inspected":
            cf = [f for f in candidate["files"] if "sha256" in f]
            rf = [f for f in reference["files"] if "sha256" in f]
            row["identical_code_file_multiset"] = (collections.Counter(f["sha256"] for f in cf) ==
                                                    collections.Counter(f["sha256"] for f in rf))
            row["byte_identical_files"] = [{"candidate": a["path"], "reference": b["path"]}
                                           for a in cf for b in rf if a["sha256"] == b["sha256"]]
            row["ast_identical_python_files"] = [{"candidate": a["path"], "reference": b["path"]}
                                                 for a in cf for b in rf if a.get("ast_sha256")
                                                 and a["ast_sha256"] == b.get("ast_sha256")]
            row["route_pairs"] = [{"candidate_route": ck, "reference_route": rk, **route_overlap(cv, rv)}
                                  for ck, cv in sorted(croutes.items()) for rk, rv in sorted(rroutes.items())]
            row["route_comparison_available"] = bool(croutes and rroutes)
        comparisons.append(row)
    return {"schema": SCHEMA, "tool_sha256": digest(Path(__file__).read_bytes()),
            "method": {"executes_inspected_code": False, "uses_game_seeds": False,
                       "ast": "Python AST without positions, comments or docstrings; identifiers and other literals retained",
                       "routes": "Literal JSON/full-tail packs and explicitly supplied Apex numeric tape convention; exact aligned JSON comparison",
                       "limits": "Source/data overlap is not authorship, runtime equivalence, strength, or license permission. Unrecognized dynamic data remains unmeasured; evidence documents are hash-preserved, not legally interpreted."},
            "candidate": candidate, "references": [x[0] for x in profiles[1:]], "comparisons": comparisons}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(read_bounded(args.manifest))
        report = compare_manifest(manifest, args.manifest.resolve().parent)
        encoded = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f"LINEAGE_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, "candidate": report["candidate"]["id"],
                      "references": len(report["references"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
