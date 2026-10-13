#!/usr/bin/env python3
import ast
from e184_12a3_prod import E184ProofError, _FN, _req, e184_policy_roots_12a3
# --------------------------- focused donor self-test ---------------------------
# These tiny callbacks model only the shapes used below. Production integration
# must pass 12a3's helpers, not these references.
def _ref_bindings(statements):
    out = {}
    for s in statements:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[s.name] = s
        elif isinstance(s, ast.Assign) and all(isinstance(t, ast.Name) for t in s.targets):
            value = out.get(s.value.id, s.value) if isinstance(s.value, ast.Name) else s.value
            for t in s.targets:
                out[t.id] = value
        elif isinstance(s, ast.Delete):
            for t in s.targets:
                if isinstance(t, ast.Name): out[t.id] = object()
    return out


def _ref_final_function(tree, name):
    node = _ref_bindings(tree.body).get(name)
    _req(isinstance(node, _FN) and not node.decorator_list, f"bad {name}")
    return node


def _ref_final_class(tree, name):
    node = _ref_bindings(tree.body).get(name)
    _req(isinstance(node, ast.ClassDef), f"bad class {name}")
    return node


def _ref_class_methods(cls):
    return {k: v for k, v in _ref_bindings(cls.body).items() if isinstance(v, _FN)}


def _ref_locals(fn):
    out = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
    for n in ast.walk(fn):
        if n is fn: continue
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
    return out


def _ref_live(statements):
    # Enough outcome handling to make post-return and both-arms-terminate poisons RED.
    def term(s):
        if isinstance(s, (ast.Return, ast.Raise)): return True
        if isinstance(s, ast.If) and s.body and s.orelse:
            return block_term(s.body) and block_term(s.orelse)
        return False
    def block_term(xs):
        return any(term(x) for x in xs)
    for s in statements:
        yield s
        if isinstance(s, ast.If):
            yield from _ref_live(s.body); yield from _ref_live(s.orelse)
        if term(s):
            break


_FIXTURE = '''\
def advance_sales(action, view, state, tape, step):
    return None
class Policy:
    def act(self, observation):
        advance_sales(action, view, state, tape, step)
        return action
_POLICY=None
def agent(observation, configuration=None):
    return _POLICY.act(observation)
_V216_PARENT=agent
del agent
def agent(observation, configuration=None):
    return _V216_PARENT(observation, configuration)
_SALE_PARENT=agent
del agent
def agent(observation, configuration=None):
    return _SALE_PARENT(observation, configuration)
POLICY_AGENT=agent
_SALE_NATIVE_ADVANCE=advance_sales
ADVANCE_START=288
def advance_sales(action, view, state, tape, step):
    if step < ADVANCE_START:
        return _SALE_NATIVE_ADVANCE(action, view, state, tape, step)
    return None
def _v3_stack(observation, configuration=None):
    action=POLICY_AGENT(observation, configuration)
    return action
def _v3_core(observation, configuration=None):
    return _v3_stack(observation, configuration)
def v3_agent(observation, configuration=None):
    if not OUTER:
        return _v3_core(observation, configuration)
    return observation
'''


def _run(src: str) -> tuple[ast.AST, ast.AST]:
    return e184_policy_roots_12a3(
        ast.parse(src), bindings_fn=_ref_bindings,
        final_function_fn=_ref_final_function, final_class_fn=_ref_final_class,
        class_methods_fn=_ref_class_methods, function_local_names=_ref_locals,
        live_nodes_block=_ref_live,
    )


def _reject(src: str) -> None:
    try:
        _run(src)
    except E184ProofError:
        return
    raise AssertionError("E184 poison false-passed")


def _self_test() -> None:
    act, native = _run(_FIXTURE)
    assert getattr(act, "name", None) == "act" and getattr(native, "name", None) == "advance_sales"
    _reject(_FIXTURE.replace("POLICY_AGENT=agent", "def bogus(observation, configuration=None): return observation\nPOLICY_AGENT=bogus"))
    _reject(_FIXTURE.replace("_SALE_NATIVE_ADVANCE=advance_sales", "_SALE_NATIVE_ADVANCE=agent"))
    _reject(_FIXTURE.replace("return _SALE_NATIVE_ADVANCE(action, view, state, tape, step)", "return None"))
    _reject(_FIXTURE.replace("advance_sales(action, view, state, tape, step)\n        return action",
                            "return action\n        advance_sales(action, view, state, tape, step)"))
    _reject(_FIXTURE.replace("return _v3_stack(observation, configuration)",
                            "return observation\n    _v3_stack(observation, configuration)"))
    _reject(_FIXTURE.replace("action=POLICY_AGENT(observation, configuration)",
                            "return observation\n    action=POLICY_AGENT(observation, configuration)"))
    _reject(_FIXTURE.replace("return _V216_PARENT(observation, configuration)",
                            "return observation\n    _V216_PARENT(observation, configuration)"))
    _reject(_FIXTURE.replace("def _v3_core(observation, configuration=None):\n    return _v3_stack(observation, configuration)",
                            "def _v3_core(observation, configuration=None):\n    def decoy(): return _v3_stack(observation, configuration)\n    return observation"))
    _reject(_FIXTURE.replace("def _v3_stack(observation, configuration=None):\n    action=POLICY_AGENT(observation, configuration)\n    return action",
                            "def _v3_stack(observation, configuration=None):\n    def decoy(): return POLICY_AGENT(observation, configuration)\n    return observation"))
    _reject(_FIXTURE.replace("    def act(self, observation):\n        advance_sales(action, view, state, tape, step)\n        return action",
                            "    def act(self, observation):\n        def decoy(): return advance_sales(action, view, state, tape, step)\n        return action"))
    _reject(_FIXTURE.replace("def agent(observation, configuration=None):\n    return _V216_PARENT(observation, configuration)",
                            "def agent(observation, configuration=None):\n    def decoy(): return _V216_PARENT(observation, configuration)\n    return observation", 1))
    _reject(_FIXTURE.replace("return _v3_stack(observation, configuration)",
                            "return (_v3_stack(x) for x in xs)"))
    _reject(_FIXTURE.replace("return _v3_stack(observation, configuration)",
                            "return (x for x in xs if _v3_stack(observation, configuration))"))
    _reject(_FIXTURE.replace("return _v3_stack(observation, configuration)",
                            "return (y for x in xs for y in _v3_stack(observation, configuration))"))
    _reject(_FIXTURE.replace("return _v3_stack(observation, configuration)",
                            "g = (_v3_stack(x) for x in xs)\n    return observation"))
    _reject(_FIXTURE.replace("        advance_sales(action, view, state, tape, step)\n",
                            "        (advance_sales(x, view, state, tape, step) for x in xs)\n", 1))
    # Outer genexpr iterable is eager: this edge remains visible by construction.
    eager = _FIXTURE.replace("return _v3_stack(observation, configuration)",
                             "return (x for x in _v3_stack(observation, configuration))")
    _run(eager)


if __name__ == "__main__":
    _self_test()
    print("E184 12A3 TOPOLOGY ADAPTER OK")
