# TITAN V4 C1 donor — bind matching r04 import and effect call to one executable path.
#
# Applies semantically after discarded-result donor 94f86a550e99de304f046eee593a67c8acc244c6.
# Donor only: no tree/ref/workflow/canonical authority.
#
# Exact 12a3 counterexample this closes:
#   if FLAG:
#       if cond: import r04_x
#       else: action = r04_x.apply_x(action)
# The stage-2 seam theorem sees an import and an action-producing call separately,
# but there is no runtime path where the import has executed before that call.

from __future__ import annotations
import ast
from typing import Iterable


def block_module_imports(statements: Iterable[ast.stmt], module: str,
                         static_truth) -> tuple[ast.Import, ...]:
    """Collect exact imports from the incumbent narrow live If grammar only."""
    out: list[ast.Import] = []
    for stmt in statements:
        if isinstance(stmt, ast.Import):
            if any(a.name == module and (a.asname is None or a.asname == module)
                   for a in stmt.names):
                out.append(stmt)
        if isinstance(stmt, ast.If):
            truth = static_truth(stmt.test)
            branches = ([stmt.body] if truth is True else [stmt.orelse]
                        if truth is False else [stmt.body, stmt.orelse])
            for branch in branches:
                out.extend(block_module_imports(branch, module, static_truth))
    return tuple(out)


def compatible_import_precedes_call(imports: Iterable[ast.Import], call: ast.Call,
                                    parents: dict[ast.AST, ast.AST],
                                    branch_constraints, paths_compatible) -> bool:
    """Require one exact import to execute earlier on a branch-compatible call path."""
    call_path = branch_constraints(call, parents)
    call_pos = (getattr(call, "lineno", -1), getattr(call, "col_offset", -1))
    for imported in imports:
        import_pos = (getattr(imported, "lineno", -1), getattr(imported, "col_offset", -1))
        if import_pos >= call_pos:
            continue
        if paths_compatible(branch_constraints(imported, parents), call_path):
            return True
    return False


def integration_shape() -> str:
    return """Inside _router_feature_seam, build parents from the whole reachable fn.\nFor each positive FLAG If/While body, collect imports = _block_module_imports(body,module).\nFor each call already proven by 94f's result/effect theorem, accept only when\ncompatible_import_precedes_call(imports, call, parents, _branch_constraints, _paths_compatible).\nDo not accept separate existence of an import and effect call."""


def _branch_constraints(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> dict[int, str]:
    out: dict[int, str] = {}
    cur: ast.AST = node
    while cur in parent:
        p = parent[cur]
        if isinstance(p, ast.If):
            if cur in p.body:
                out[id(p)] = "body"
            elif cur in p.orelse:
                out[id(p)] = "else"
        cur = p
    return out


def _paths_compatible(*paths: dict[int, str]) -> bool:
    seen: dict[int, str] = {}
    for path in paths:
        for controller, branch in path.items():
            prior = seen.get(controller)
            if prior is not None and prior != branch:
                return False
            seen[controller] = branch
    return True


def self_test() -> None:
    split = ast.parse("""\ndef f(action, cond):
    if cond:
        import r04_x
    else:
        action = r04_x.apply_x(action)
    return action
""").body[0]
    parents = {c: p for p in ast.walk(split) for c in ast.iter_child_nodes(p)}
    imports = tuple(n for n in ast.walk(split) if isinstance(n, ast.Import))
    call = next(n for n in ast.walk(split) if isinstance(n, ast.Call))
    assert not compatible_import_precedes_call(imports, call, parents,
                                               _branch_constraints, _paths_compatible)

    same = ast.parse("""\ndef f(action, cond):
    if cond:
        import r04_x
        action = r04_x.apply_x(action)
    return action
""").body[0]
    parents = {c: p for p in ast.walk(same) for c in ast.iter_child_nodes(p)}
    imports = tuple(n for n in ast.walk(same) if isinstance(n, ast.Import))
    call = next(n for n in ast.walk(same) if isinstance(n, ast.Call))
    assert compatible_import_precedes_call(imports, call, parents,
                                           _branch_constraints, _paths_compatible)

    before = ast.parse("""\ndef f(action):
    action = r04_x.apply_x(action)
    import r04_x
    return action
""").body[0]
    parents = {c: p for p in ast.walk(before) for c in ast.iter_child_nodes(p)}
    imports = tuple(n for n in ast.walk(before) if isinstance(n, ast.Import))
    call = next(n for n in ast.walk(before) if isinstance(n, ast.Call))
    assert not compatible_import_precedes_call(imports, call, parents,
                                               _branch_constraints, _paths_compatible)


if __name__ == "__main__":
    self_test()
    print("C1 IMPORT/CALL PATH DONOR OK")
