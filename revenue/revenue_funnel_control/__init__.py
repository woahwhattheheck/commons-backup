"""Provider-evidence-bound revenue funnel control.

The implementation is loaded lazily so ``python -m revenue.revenue_funnel_control.engine``
does not pre-import the target module through package initialization.

Normal imports seal the exact engine module after source execution. This prevents
ordinary same-process reassignment/deletion of the exported semantic generation
before downstream consumers capture it. Custom loaders, source replacement,
direct ``__dict__`` mutation, and interpreter/host takeover are outside this
metadata boundary.
"""

from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import PathFinder
import sys
from types import ModuleType

__all__ = ["FunnelError", "compile_bundle", "compile_portfolio", "verify_bundle"]

_ENGINE_NAME = f"{__name__}.engine"
_MUTABLE_IMPORT_METADATA = frozenset(
    {"__spec__", "__loader__", "__package__", "__cached__", "__name__", "__file__"}
)


def _seal_engine(
    module: ModuleType,
    _module_type=ModuleType,
    _mutable_import_metadata=_MUTABLE_IMPORT_METADATA,
) -> None:
    """Block ordinary rebinding of the loaded funnel semantic generation."""
    if getattr(type(module), "__revenue_funnel_semantic_root_sealed__", False):
        return

    frozen_names = frozenset(module.__dict__) | {"__class__"}

    class _SealedFunnelEngineModule(_module_type):
        __revenue_funnel_semantic_root_sealed__ = True

        def __setattr__(
            self,
            name,
            value,
            _frozen_names=frozen_names,
            _mutable=_mutable_import_metadata,
        ):
            if name in _frozen_names and name not in _mutable:
                raise AttributeError(f"revenue-funnel semantic root is sealed: {name}")
            return super().__setattr__(name, value)

        def __delattr__(
            self,
            name,
            _frozen_names=frozen_names,
            _mutable=_mutable_import_metadata,
        ):
            if name in _frozen_names and name not in _mutable:
                raise AttributeError(f"revenue-funnel semantic root is sealed: {name}")
            return super().__delattr__(name)

    module.__class__ = _SealedFunnelEngineModule


class _EngineLoader(Loader):
    """Delegate normal loading, then seal the exact imported engine object."""

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped

    def create_module(self, spec):
        create = getattr(self._wrapped, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module, _seal=_seal_engine) -> None:
        self._wrapped.exec_module(module)
        _seal(module)

    def get_code(self, fullname):
        return self._wrapped.get_code(fullname)

    def get_source(self, fullname):
        get_source = getattr(self._wrapped, "get_source", None)
        return get_source(fullname) if get_source is not None else None

    def is_package(self, fullname):
        is_package = getattr(self._wrapped, "is_package", None)
        return is_package(fullname) if is_package is not None else False

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _EngineSealFinder(MetaPathFinder):
    _revenue_funnel_marker = f"{__name__}:engine-semantic-seal-v1"

    def find_spec(
        self,
        fullname,
        path=None,
        target=None,
        _engine_name=_ENGINE_NAME,
        _path_finder=PathFinder,
        _loader_type=_EngineLoader,
    ):
        if fullname != _engine_name:
            return None
        spec = _path_finder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _loader_type(spec.loader)
        return spec


_marker = f"{__name__}:engine-semantic-seal-v1"
if not any(
    getattr(finder, "_revenue_funnel_marker", None) == _marker
    for finder in sys.meta_path
):
    sys.meta_path.insert(0, _EngineSealFinder())


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(".engine", __name__)
    return getattr(module, name)
