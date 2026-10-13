"""Extract the pinned unit-phase transition into a standalone bundled module.

The hosted archive must not depend on `kaggle_environments` being importable in
the agent process, and it must not fall back to a re-implementation: it carries
the engine's own `_apply_unit_action` and the exact transitive closure of the
helpers and constants that routine needs, copied VERBATIM from the pinned source,
with the upstream Apache-2.0 notice.

Verbatim matters. A hand-written copy would drift from the engine the moment the
pin moved, and every guard in `native_motifs.py` is only as good as the transition
it simulates. `tests/test_engine_pin_parity.py` re-checks the bundle against the
installed engine on real recorded turns and on generated states.
"""

import argparse
import ast
import hashlib
import os

# Two roots. The transition is what the proposal layer simulates; `market_price`
# is what it prices candidates with, and a hosted archive cannot assume the
# evaluator package is importable at runtime to supply it.
ROOTS = ("_apply_unit_action", "market_price")
HEADER = '''"""Bundled pinned unit-phase transition (GENERATED -- do not hand-edit).

Copied verbatim from Kaggle/kaggle-environments, which is licensed under the
Apache License, Version 2.0. The upstream NOTICE and full licence text ship
alongside this file as LICENSE-APACHE-2.0.txt.

  upstream   kaggle_environments/envs/kaggriculture/kaggriculture.py
  pin        {pin}
  sha256     {sha}
  extracted  {names}

Exported for the lab and the archive: the unit-phase transition
`_apply_unit_action` and the market quote `market_price(item, inventory, params)`,
each with the exact transitive closure of the helpers and constants it needs.

Regenerate with `extract_engine_pin.py`; verify with tests/test_engine_pin_parity.py.
"""

'''


def closure(tree):
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    consts = {t.id: n for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name)}
    need, seen, used = list(ROOTS), set(), set()
    while need:
        f = need.pop()
        if f in seen or f not in defs:
            continue
        seen.add(f)
        for nd in ast.walk(defs[f]):
            if isinstance(nd, ast.Name):
                if nd.id in defs and nd.id not in seen:
                    need.append(nd.id)
                if nd.id in consts:
                    used.add(nd.id)
    # A constant can reference other constants -- MARKET_PARAMS is written in terms
    # of MARKET_I0 -- so the closure has to run to a fixpoint over the constant
    # bodies too, not just the function bodies.
    while True:
        grown = set()
        for c in list(used):
            for nd in ast.walk(consts[c]):
                if isinstance(nd, ast.Name):
                    if nd.id in consts and nd.id not in used:
                        grown.add(nd.id)
                    elif nd.id in defs and nd.id not in seen:
                        seen.add(nd.id)
                        need.append(nd.id)
        if not grown:
            break
        used |= grown
    return defs, consts, seen, used


def needed_imports(tree, parts_src):
    """Emit the module imports the extracted code actually references.

    The closure walk finds functions and constants; it does not carry the
    `import math` those bodies rely on, and a bundle that omits it fails at first
    call rather than at import.
    """
    out = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                if re_word(name, parts_src):
                    out.append(f"import {alias.name}"
                               + (f" as {alias.asname}" if alias.asname else ""))
        elif isinstance(node, ast.ImportFrom):
            keep = [a for a in node.names
                    if re_word(a.asname or a.name, parts_src)]
            if keep and node.module and not node.level:
                out.append("from " + node.module + " import "
                           + ", ".join(a.name + (f" as {a.asname}" if a.asname else "")
                                       for a in keep))
    return out


def re_word(name, text):
    import re as _re
    return bool(_re.search(r"\b" + _re.escape(name) + r"\b", text))


def build(src_path, pin, out_path):
    src = open(src_path).read()
    sha = hashlib.sha256(src.encode()).hexdigest()
    lines = src.split("\n")
    tree = ast.parse(src)
    defs, consts, fns, cns = closure(tree)

    def seg(node):
        # verbatim source segment, including any decorator-free leading blank
        return "\n".join(lines[node.lineno - 1:node.end_lineno])

    # Emit constants in SOURCE order: a later one may be written in terms of an
    # earlier one, and sorting by name would break that.
    parts = [seg(consts[c])
             for c in sorted(cns, key=lambda n: consts[n].lineno)]
    parts += [seg(defs[f]) for f in sorted(fns)]
    body = HEADER.format(pin=pin, sha=sha,
                         names=", ".join(sorted(cns) + sorted(fns)))
    imports = needed_imports(tree, "\n".join(parts))
    if imports:
        body += "\n".join(imports) + "\n\n\n"
    body += "\n\n".join(parts) + "\n"
    with open(out_path, "w") as fh:
        fh.write(body)
    return {"source_sha256": sha, "functions": sorted(fns), "constants": sorted(cns),
            "bundle_sha256": hashlib.sha256(body.encode()).hexdigest()[:16],
            "bytes": len(body)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source",
                    default="/home/user/work/engine/kaggle_environments/envs/"
                            "kaggriculture/kaggriculture.py")
    ap.add_argument("--pin", default="28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c")
    ap.add_argument("--out", default="engine_pin.py")
    ap.add_argument("--license",
                    default="/home/user/work/engine/LICENSE")
    a = ap.parse_args()
    info = build(a.source, a.pin, a.out)
    dst = os.path.join(os.path.dirname(a.out) or ".", "LICENSE-APACHE-2.0.txt")
    if os.path.exists(a.license):
        with open(a.license) as fh, open(dst, "w") as out:
            out.write(fh.read())
        info["license"] = dst
    import json
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
