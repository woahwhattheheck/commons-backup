from __future__ import annotations

from ._model import *
from ._flow import *


class _CallCollector(ast.NodeVisitor):
    def __init__(self, root: ast.FunctionDef | ast.AsyncFunctionDef):
        self.root = root
        self.calls: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)


class _Analyzer:
    def __init__(self, tree: ast.Module, path: str):
        self.tree = tree
        self.path = path
        self.globals = _module_string_constants(tree)
        self.trusted_clock_names = _trusted_clock_names(tree)
        self.specs = _collect_function_specs(tree)
        self.function_keys = {spec.key for spec in self.specs}
        self.functions: dict[str, _FunctionModel] = {}

        for spec in self.specs:
            fn = spec.node
            params = _function_params(fn)
            authority_params = {name for name in params if _authority_name(name)}
            defs = _local_defs(fn)
            resolver = lambda raw, spec=spec: self._resolve_call(raw, spec)
            direct, returned_calls, _, _, _ = _collect_positive_paths(
                fn.body,
                facts=frozenset(),
                authority_params=authority_params,
                env={},
                globals_=self.globals,
                resolve_call=resolver,
            )
            collector = _CallCollector(fn)
            collector.visit(fn)
            all_calls: list[_CallSite] = []
            for call in collector.calls:
                targets: set[str] = set()
                direct_target = resolver(_name(call.func))
                if direct_target is not None:
                    targets.add(direct_target)
                if isinstance(call.func, ast.Name) and call.func.id in defs:
                    for value in defs[call.func.id]:
                        alias = resolver(_name(value))
                        if alias is not None:
                            targets.add(alias)
                all_calls.extend(
                    _CallSite(target, call, frozenset())
                    for target in sorted(targets)
                )
            self.functions[spec.key] = _FunctionModel(
                key=spec.key,
                owner=spec.owner,
                lexical_parent=spec.lexical_parent,
                surface=spec.surface,
                node=fn,
                params=params,
                authority_params=authority_params,
                local_defs=defs,
                trusted_clock_names=self.trusted_clock_names,
                direct_positive_requirements=direct,
                returned_calls=returned_calls,
                all_calls=all_calls,
                direct_time_requirements=_direct_time_requirements(
                    fn, defs, self.trusted_clock_names
                ),
                direct_retained_replay=_direct_retained_replay(
                    fn, defs, self.trusted_clock_names
                ),
            )

        self._positive_cache: dict[str, list[frozenset[str]]] = {}
        self._time_cache: dict[str, list[frozenset[str]]] = {}
        self._replay_cache: dict[str, bool] = {}

    def _resolve_call(self, raw: str, spec: _FunctionSpec) -> str | None:
        if not raw:
            return None
        if raw in self.function_keys:
            return raw
        if "." not in raw:
            candidate = f"{spec.key}.<locals>.{raw}"
            if candidate in self.function_keys:
                return candidate
            parent = spec.lexical_parent
            while parent is not None:
                candidate = f"{parent}.<locals>.{raw}"
                if candidate in self.function_keys:
                    return candidate
                parent_model = next((item for item in self.specs if item.key == parent), None)
                parent = parent_model.lexical_parent if parent_model is not None else None
        if spec.owner is not None:
            if raw.startswith("self.") or raw.startswith("cls."):
                candidate = f"{spec.owner}.{raw.split('.', 1)[1]}"
                if candidate in self.function_keys:
                    return candidate
            owner_short = spec.owner.rsplit(".", 1)[-1]
            if raw.startswith(owner_short + "."):
                candidate = f"{spec.owner}.{raw.split('.', 1)[1]}"
                if candidate in self.function_keys:
                    return candidate
        return None

    def _map_requirements(
        self,
        caller: _FunctionModel,
        call: ast.Call,
        callee: _FunctionModel,
        requirements: Iterable[frozenset[str]],
        facts: frozenset[str] = frozenset(),
    ) -> list[frozenset[str]]:
        params = set(caller.params)
        origins = _origins(
            caller.node,
            caller.local_defs,
            caller.trusted_clock_names,
        )
        out: list[frozenset[str]] = []
        for requirement in requirements:
            mapped = set(facts)
            for parameter in requirement:
                argument = _call_argument(call, callee, parameter)
                if argument is None:
                    continue
                sources = _expr_sources(
                    argument,
                    params=params,
                    origins=origins,
                    defs=caller.local_defs,
                    trusted_clock_names=caller.trusted_clock_names,
                )
                mapped.update(source for source in sources if source in caller.authority_params)
            out.append(frozenset(mapped))
        return out

    def positive_requirements(
        self,
        name: str,
        stack: frozenset[str] = frozenset(),
    ) -> list[frozenset[str]]:
        if name in self._positive_cache:
            return self._positive_cache[name]
        if name in stack:
            return [frozenset()]
        fn = self.functions[name]
        out = list(fn.direct_positive_requirements)
        for site in fn.returned_calls:
            callee = self.functions.get(site.callee)
            if callee is None:
                continue
            child = self.positive_requirements(site.callee, stack | {name})
            out.extend(
                self._map_requirements(
                    fn,
                    site.node,
                    callee,
                    child,
                    site.authority_facts,
                )
            )
        self._positive_cache[name] = out
        return out

    def time_requirements(
        self,
        name: str,
        stack: frozenset[str] = frozenset(),
    ) -> list[frozenset[str]]:
        if name in self._time_cache:
            return self._time_cache[name]
        if name in stack:
            return []
        fn = self.functions[name]
        out = list(fn.direct_time_requirements)
        params = set(fn.params)
        origins = _origins(fn.node, fn.local_defs, fn.trusted_clock_names)
        for site in fn.all_calls:
            callee = self.functions.get(site.callee)
            if callee is None:
                continue
            for requirement in self.time_requirements(site.callee, stack | {name}):
                mapped: set[str] = set()
                for parameter in requirement:
                    argument = _call_argument(site.node, callee, parameter)
                    if argument is None:
                        continue
                    sources = _expr_sources(
                        argument,
                        params=params,
                        origins=origins,
                        defs=fn.local_defs,
                        trusted_clock_names=fn.trusted_clock_names,
                    )
                    mapped.update(source for source in sources if source in params)
                if mapped:
                    out.append(frozenset(mapped))
        self._time_cache[name] = out
        return out

    def retained_replay(
        self,
        name: str,
        stack: frozenset[str] = frozenset(),
    ) -> bool:
        if name in self._replay_cache:
            return self._replay_cache[name]
        if name in stack:
            return True
        fn = self.functions[name]
        if fn.direct_retained_replay:
            self._replay_cache[name] = True
            return True
        unsafe = any(
            self.retained_replay(site.callee, stack | {name})
            for site in fn.all_calls
            if site.callee in self.functions
        )
        self._replay_cache[name] = unsafe
        return unsafe

    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for name, model in self.functions.items():
            fn = model.node
            if not model.surface or not _public(fn) or _historical_surface(fn):
                continue
            positives = self.positive_requirements(name)
            times = self.time_requirements(name)
            if times:
                out.append(
                    Finding(
                        self.path,
                        fn.lineno,
                        fn.col_offset + 1,
                        "CRG001",
                        "caller-derived data reaches a deadline/expiry comparison through this public surface",
                        name,
                    )
                )
            if positives:
                risky_time_params = [
                    parameter
                    for parameter in model.params
                    if any(word in parameter.lower() for word in _TIME_WORDS)
                    and any(
                        isinstance(child, ast.Name) and child.id == parameter
                        for child in ast.walk(fn)
                    )
                ]
                if risky_time_params:
                    out.append(
                        Finding(
                            self.path,
                            fn.lineno,
                            fn.col_offset + 1,
                            "CRG002",
                            "public current-positive surface accepts caller-selectable time/clock parameter(s): "
                            + ", ".join(sorted(risky_time_params)),
                            name,
                        )
                    )
                if any(not requirement for requirement in positives):
                    out.append(
                        Finding(
                            self.path,
                            fn.lineno,
                            fn.col_offset + 1,
                            "CRG003",
                            "a current-positive path is not controlled by an actually consumed independent authority parameter",
                            name,
                        )
                    )
            if "verify" in fn.name.lower() and self.retained_replay(name):
                out.append(
                    Finding(
                        self.path,
                        fn.lineno,
                        fn.col_offset + 1,
                        "CRG004",
                        "retained caller/report time reaches a current projection without a process-clock projection used in the verifier result",
                        name,
                    )
                )
        return sorted(set(out))


def analyze_source(source: str | bytes, *, path: str = "<memory>") -> list[Finding]:
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            return [Finding(path, exc.start + 1, 1, "CRG000", "source is not strict UTF-8", None)]
    if not isinstance(source, str):
        raise TypeError("source must be str or bytes")
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None) or 1
        col = getattr(exc, "offset", None) or 1
        message = exc.msg if isinstance(exc, SyntaxError) else str(exc)
        return [Finding(path, line, col, "CRG000", f"source parse failure: {message}", None)]
    return _Analyzer(tree, path).findings()


__all__ = [name for name in globals() if not name.startswith("__")]
