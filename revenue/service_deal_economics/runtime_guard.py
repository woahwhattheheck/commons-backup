from __future__ import annotations

from types import FunctionType, ModuleType
from typing import Any, Callable, Iterable


_MISSING = object()

# Only these reachable types are part of CURRENT trust. Snapshotting every
# stdlib class on the graph (pathlib, weakref.finalize, datetime, ...) both
# pulls pathlib special-method dispatch back into the integrity set and
# self-poisons when tests or atexit mutate unrelated class namespaces.
_TRUST_CLASS_MODULES = {
    "revenue.service_deal_economics",
    "revenue.service_deal_economics.authority",
    "revenue.service_deal_economics.engine",
    "revenue.service_deal_economics.strict_json",
    "revenue.service_deal_economics.fixed_host",
    "revenue.service_deal_economics.current_runtime",
    "revenue.service_deal_economics.runtime_guard",
    "revenue.service_deal_economics.cli",
}
_TRUST_STDLIB_TYPES = {
    ("json", "JSONEncoder"),
    ("json.encoder", "JSONEncoder"),
    ("json", "JSONDecoder"),
    ("json.decoder", "JSONDecoder"),
    ("hmac", "HMAC"),
}


def _is_trust_class(cls: type) -> bool:
    module = getattr(cls, "__module__", "") or ""
    name = getattr(cls, "__name__", "") or ""
    if module in _TRUST_CLASS_MODULES or module.startswith("revenue.service_deal_economics."):
        return True
    return (module, name) in _TRUST_STDLIB_TYPES


def freeze_call_graph(
    *roots: Callable[..., Any],
    bindings: Iterable[tuple[object, str]] = (),
) -> Callable[[], bool]:
    """Capture a transitive Python call graph and return a closure-only guard.

    Resolution is frozen at three levels:
    * globals and builtins named by each Python function's bytecode;
    * selectively referenced module/class attributes and recursively reached
      Python function objects;
    * full namespaces for reachable trust-class instances and for package,
      JSONEncoder/JSONDecoder, and HMAC classes (including trust-class MRO
      bases and subclasses). Pathlib and other incidental stdlib types are
      not CURRENT trust roots and are not snapshotted as class namespaces.

    Whole module namespaces are deliberately not snapshotted: authority-bearing
    module attributes are already identity-bound selectively, while unrelated
    names may legitimately appear after import.

    The returned guard accepts no arguments. Snapshots and check primitives are
    held only in closure cells, preventing keyword/default trust injection.
    """

    global_bindings: list[tuple[dict[str, Any], str, object]] = []
    attr_bindings: list[tuple[object, str, object, bool]] = []
    function_bindings: list[tuple[FunctionType, object, object, object]] = []
    namespace_bindings: list[tuple[object, tuple[tuple[str, object], ...]]] = []
    seen_globals: set[tuple[int, str]] = set()
    seen_attrs: set[tuple[int, str, bool]] = set()
    seen_functions: set[int] = set()
    seen_namespaces: set[int] = set()
    seen_classes: set[int] = set()

    def snapshot_namespace(owner: object) -> None:
        if isinstance(owner, (FunctionType, ModuleType)):
            return
        marker = id(owner)
        if marker in seen_namespaces:
            return
        try:
            namespace = vars(owner)
        except TypeError:
            return
        seen_namespaces.add(marker)
        namespace_bindings.append((owner, tuple(namespace.items())))

    def capture_class(cls: type) -> None:
        marker = id(cls)
        if marker in seen_classes:
            return
        seen_classes.add(marker)
        if not _is_trust_class(cls):
            return
        snapshot_namespace(cls)
        # Snapshot inherited special-method providers that are themselves
        # trust types. Do not walk object / pathlib / weakref.
        for base in cls.__mro__[1:]:
            if isinstance(base, type) and _is_trust_class(base):
                capture_class(base)
        try:
            children = tuple(cls.__subclasses__())
        except TypeError:
            children = ()
        for child in children:
            if _is_trust_class(child):
                capture_class(child)

    def capture_mutable_state(owner: object) -> None:
        if isinstance(owner, (FunctionType, ModuleType)):
            return
        if isinstance(owner, type):
            capture_class(owner)
            return
        snapshot_namespace(owner)
        capture_class(type(owner))

    def capture_attr(owner: object, name: str) -> object:
        is_namespace = isinstance(owner, (ModuleType, type))
        key = (id(owner), name, is_namespace)
        if key in seen_attrs:
            if is_namespace:
                return vars(owner).get(name, _MISSING)
            return getattr(owner, name, _MISSING)
        seen_attrs.add(key)
        capture_mutable_state(owner)
        if is_namespace:
            value = vars(owner).get(name, _MISSING)
        else:
            value = getattr(owner, name, _MISSING)
        attr_bindings.append((owner, name, value, is_namespace))
        capture_mutable_state(value)
        if isinstance(value, FunctionType):
            capture_function(value)
        return value

    def bind_name(namespace: dict[str, Any], name: str, value: object) -> None:
        key = (id(namespace), name)
        if key not in seen_globals:
            seen_globals.add(key)
            global_bindings.append((namespace, name, value))
        capture_mutable_state(value)
        if isinstance(value, FunctionType):
            capture_function(value)

    def capture_function(fn: FunctionType) -> None:
        marker = id(fn)
        if marker in seen_functions:
            return
        seen_functions.add(marker)
        function_bindings.append((fn, fn.__code__, fn.__defaults__, fn.__kwdefaults__))
        names = tuple(fn.__code__.co_names)
        namespace = fn.__globals__
        builtins_namespace = fn.__builtins__
        if isinstance(builtins_namespace, ModuleType):
            builtins_namespace = vars(builtins_namespace)
        for name in names:
            if name in namespace:
                value = namespace[name]
                bind_name(namespace, name, value)
                if isinstance(value, (ModuleType, type)):
                    for attr_name in names:
                        if attr_name == name:
                            continue
                        if attr_name in vars(value) or hasattr(value, attr_name):
                            capture_attr(value, attr_name)
            elif name in builtins_namespace:
                bind_name(builtins_namespace, name, builtins_namespace[name])

    for root in roots:
        if not isinstance(root, FunctionType):
            raise TypeError("freeze_call_graph roots must be Python functions")
        capture_function(root)
    for owner, name in tuple(bindings):
        capture_attr(owner, name)

    globals_snapshot = tuple(global_bindings)
    attrs_snapshot = tuple(attr_bindings)
    functions_snapshot = tuple(function_bindings)
    namespaces_snapshot = tuple(namespace_bindings)
    missing = _MISSING
    get_attr = getattr
    get_vars = vars

    def intact() -> bool:
        for namespace, name, expected in globals_snapshot:
            if namespace.get(name, missing) is not expected:
                return False
        for owner, name, expected, is_namespace in attrs_snapshot:
            if is_namespace:
                actual = get_vars(owner).get(name, missing)
            else:
                actual = get_attr(owner, name, missing)
            if actual is not expected:
                return False
        for fn, code, defaults, kwdefaults in functions_snapshot:
            if fn.__code__ is not code or fn.__defaults__ is not defaults or fn.__kwdefaults__ is not kwdefaults:
                return False
        for owner, expected_items in namespaces_snapshot:
            try:
                current = get_vars(owner)
            except TypeError:
                return False
            if len(current) != len(expected_items):
                return False
            for name, expected in expected_items:
                if current.get(name, missing) is not expected:
                    return False
        return True

    return intact
