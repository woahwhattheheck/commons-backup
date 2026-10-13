from __future__ import annotations

import importlib.abc
import importlib.machinery
import math
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import wraps
from types import ModuleType
from typing import Any, Optional

from revenue.outbound_connector_lease.key import SUPPORTED_REPLY_PROVIDERS

from . import engine as _engine


ContractError = _engine.ContractError
VERSION = _engine.VERSION
canonical_json = _engine.canonical_json
render_markdown = _engine.render_markdown
sha256_hex = _engine.sha256_hex

# Provider identity is one cross-revenue seam. Reuse the registry that already
# protects outbound reply leases instead of minting a second vocabulary that can
# drift and reopen alias splits later.
CANONICAL_MESSAGE_PROVIDERS = SUPPORTED_REPLY_PROVIDERS

_MESSAGE_EVENT_TYPES = frozenset(
    {
        "OFFER_SENT",
        "BUYER_INTEREST",
        "PROPOSAL_SENT",
        "BUYER_ACCEPTED",
        "BUYER_REJECTED",
        "PAYMENT_REQUEST_SENT",
        "FULFILLMENT_SENT",
        "BUYER_FULFILLMENT_ACCEPTED",
    }
)

_ENGINE_NAME = _engine.__name__
_GUARD_MARKER = "__commercial_deal_room_guarded__"
_FINDER_MARKER = "__commercial_deal_room_reload_finder__"

# Public diagnostics only. The production snapshotter binds the actual limits
# into a private closure below, so later rebinding of these module names cannot
# weaken or tighten the installed product boundary.
_MAX_SNAPSHOT_DEPTH = 64
_MAX_SNAPSHOT_NODES = 250_000


def _make_detacher(*, max_depth: int, max_nodes: int):
    """Build one snapshotter with policy and helper authority captured by value."""

    if type(max_depth) is not int or max_depth < 0:
        raise ValueError("max_depth must be a non-negative exact int")
    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive exact int")

    # Retain the trusted helper generation as closure cells. Ordinary same-
    # process rebinding of guarded module names after import must not alter the
    # semantics of an already-installed production boundary.
    error_type = ContractError
    isfinite = math.isfinite
    mapping_type = Mapping
    sequence_type = Sequence
    scalar_classes = (str, bytes, bytearray, bool, int, float)

    def detach(
        value: Any,
        *,
        path: str = "packet",
        _memo: Optional[dict[int, tuple[Any, Any]]] = None,
        _active: Optional[set[int]] = None,
        _nodes: Optional[list[int]] = None,
        _depth: int = 0,
    ) -> Any:
        """Capture a bounded caller-owned JSON-shaped graph once by identity.

        Container aliases reuse one completed plain snapshot. Active back-edges
        fail closed as cycles. The identity memo retains each source object so an
        integer ``id()`` cannot be recycled during capture. Scalar leaves and
        mapping keys must be exact JSON builtin types; subclasses are rejected
        rather than carrying attacker-controlled equality/hash semantics across
        the trust boundary.
        """

        if _depth > max_depth:
            raise error_type(f"{path} exceeds snapshot depth limit")
        if _memo is None:
            _memo = {}
        if _active is None:
            _active = set()
        if _nodes is None:
            _nodes = [0]

        value_type = type(value)
        if value_type in (type(None), bool, int, str):
            return value
        if value_type is float:
            if not isfinite(value):
                raise error_type(f"{path} contains a non-finite JSON number")
            return value

        # Reject scalar subclasses before container classification. In
        # particular, a str/int subclass may serialize one wire value while
        # overriding equality/hash to route as another semantic value.
        if isinstance(value, scalar_classes):
            raise error_type(f"{path} scalar must use an exact JSON builtin type")

        is_mapping = isinstance(value, mapping_type)
        is_sequence = isinstance(value, sequence_type)
        if not (is_mapping or is_sequence):
            raise error_type(f"{path} contains an unsupported value type")

        identity = id(value)
        if identity in _active:
            raise error_type(f"{path} contains a cyclic input graph")
        memo_entry = _memo.get(identity)
        if memo_entry is not None:
            witness, snapshot = memo_entry
            if witness is value:
                return snapshot
            # A strong witness makes this unreachable for ordinary Python
            # objects, but fail closed if a runtime violates live identity
            # uniqueness rather than aliasing two distinct objects.
            raise error_type(f"{path} contains a snapshot identity collision")

        _nodes[0] += 1
        if _nodes[0] > max_nodes:
            raise error_type("input graph exceeds snapshot node limit")
        _active.add(identity)

        try:
            if is_mapping:
                out: dict[str, Any] = {}
                _memo[identity] = (value, out)
                try:
                    for key in value:
                        _nodes[0] += 1
                        if _nodes[0] > max_nodes:
                            raise error_type("input graph exceeds snapshot node limit")
                        if type(key) is not str:
                            raise error_type(
                                f"{path} mapping key must use exact str type"
                            )
                        try:
                            child = value[key]
                        except Exception as exc:
                            raise error_type(
                                f"{path} changed while being snapshotted"
                            ) from exc
                        out[key] = detach(
                            child,
                            path=f"{path}[{key!r}]",
                            _memo=_memo,
                            _active=_active,
                            _nodes=_nodes,
                            _depth=_depth + 1,
                        )
                except error_type:
                    raise
                except Exception as exc:
                    raise error_type(f"{path} could not be snapshotted") from exc
                return out

            out_list: list[Any] = []
            _memo[identity] = (value, out_list)
            try:
                for index, child in enumerate(value):
                    _nodes[0] += 1
                    if _nodes[0] > max_nodes:
                        raise error_type("input graph exceeds snapshot node limit")
                    out_list.append(
                        detach(
                            child,
                            path=f"{path}[{index}]",
                            _memo=_memo,
                            _active=_active,
                            _nodes=_nodes,
                            _depth=_depth + 1,
                        )
                    )
            except error_type:
                raise
            except Exception as exc:
                raise error_type(f"{path} could not be snapshotted") from exc
            return out_list
        except Exception:
            _memo.pop(identity, None)
            raise
        finally:
            _active.discard(identity)

    return detach


# Bind the safety policy once. Rebinding _MAX_SNAPSHOT_* later changes only the
# diagnostic names above; the installed product snapshotter retains 64/250000.
_detach = _make_detacher(
    max_depth=_MAX_SNAPSHOT_DEPTH,
    max_nodes=_MAX_SNAPSHOT_NODES,
)


def _make_provider_validator():
    """Retain provider-vocabulary authority independent of later globals."""

    error_type = ContractError
    mapping_type = Mapping
    sequence_type = Sequence
    event_types = _MESSAGE_EVENT_TYPES
    providers = CANONICAL_MESSAGE_PROVIDERS

    def validate(packet: Any) -> None:
        if not isinstance(packet, mapping_type):
            return
        events = packet.get("events")
        if not isinstance(events, sequence_type) or isinstance(
            events, (str, bytes, bytearray)
        ):
            return

        for index, event in enumerate(events):
            if not isinstance(event, mapping_type) or event.get("type") not in event_types:
                continue
            payload = event.get("payload")
            if not isinstance(payload, mapping_type) or "provider" not in payload:
                continue
            provider = payload["provider"]
            if type(provider) is not str or provider not in providers:
                raise error_type(
                    f"event[{index}].payload.provider must be a canonical provider ID: "
                    f"{sorted(providers)}"
                )

    return validate


validate_message_providers = _make_provider_validator()


def _make_guard_installer(*, detacher: Any, provider_validator: Any):
    """Retain one trusted guard generation across later module rebinding/reload."""

    error_type = ContractError
    module_type = ModuleType
    wraps_fn = wraps
    engine_name = _ENGINE_NAME
    guard_marker = _GUARD_MARKER

    def install_engine_guards(module: ModuleType) -> None:
        """Install guarded entrypoints into one live engine module generation."""

        namespace = module_type.__getattribute__(module, "__dict__")
        required = {
            "ContractError",
            "VERSION",
            "canonical_json",
            "render_markdown",
            "sha256_hex",
            "normalize_packet",
            "verify_board",
        }
        missing = sorted(required - set(namespace))
        if missing:
            raise ImportError(f"{engine_name} missing guarded entrypoints: {missing}")

        # Engine source defines a new exception class on every reload. Preserve
        # the original exported identity so pre-reload callers keep catching it.
        namespace["ContractError"] = error_type

        current_normalize = namespace["normalize_packet"]
        if getattr(current_normalize, guard_marker, False):
            return

        core_normalize = current_normalize
        core_verify = namespace["verify_board"]

        # Refresh helper aliases after reload creates new function objects in the
        # existing engine module dictionary. These aliases are convenience, not
        # the retained security authority captured by this installer closure.
        module_globals = globals()
        module_globals["VERSION"] = namespace["VERSION"]
        module_globals["canonical_json"] = namespace["canonical_json"]
        module_globals["render_markdown"] = namespace["render_markdown"]
        module_globals["sha256_hex"] = namespace["sha256_hex"]

        @wraps_fn(core_normalize)
        def guarded_normalize_packet(packet: Any):
            snapshot = detacher(packet)
            provider_validator(snapshot)
            return core_normalize(snapshot)

        setattr(guarded_normalize_packet, guard_marker, True)

        @wraps_fn(core_verify)
        def guarded_verify_board(
            packet: Any, board: Any, *, now: Optional[datetime] = None
        ):
            # Core verification compiles historical and current views separately.
            # Capture packet + board into one bounded identity domain before core
            # touches either caller-owned graph, so historical verification sees
            # one stable board generation and cross-input aliases share a snapshot.
            memo: dict[int, tuple[Any, Any]] = {}
            active: set[int] = set()
            nodes = [0]
            packet_snapshot = detacher(
                packet,
                path="packet",
                _memo=memo,
                _active=active,
                _nodes=nodes,
            )
            board_snapshot = detacher(
                board,
                path="board",
                _memo=memo,
                _active=active,
                _nodes=nodes,
            )
            return core_verify(packet_snapshot, board_snapshot, now=now)

        setattr(guarded_verify_board, guard_marker, True)

        # Existing compile_board() resolves normalize_packet from engine globals
        # at call time. One patched normalizer therefore protects package and
        # direct-engine entrypoints plus stale compile references across reload.
        namespace["normalize_packet"] = guarded_normalize_packet
        namespace["verify_board"] = guarded_verify_board

    return install_engine_guards


_install_engine_guards = _make_guard_installer(
    detacher=_detach,
    provider_validator=validate_message_providers,
)


class _ReloadGuardLoader(importlib.abc.Loader):
    """Delegate source execution, then restore a retained guard generation."""

    def __init__(self, wrapped: Any, installer: Any) -> None:
        self._wrapped = wrapped
        self._installer = installer

    def create_module(self, spec: Any):
        create = getattr(self._wrapped, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module: ModuleType) -> None:
        self._wrapped.exec_module(module)
        self._installer(module)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class _ReloadGuardFinder(importlib.abc.MetaPathFinder):
    """Wrap only Commercial Deal Room engine loads/reloads with retained helpers."""

    __commercial_deal_room_reload_finder__ = True

    def __init__(self, engine_name: str, loader_type: Any, installer: Any) -> None:
        self._engine_name = engine_name
        self._loader_type = loader_type
        self._installer = installer
        self._path_finder = importlib.machinery.PathFinder

    def find_spec(self, fullname: str, path: Any, target: Optional[ModuleType] = None):
        if fullname != self._engine_name:
            return None
        # Delegate directly to retained PathFinder so this finder never recurses
        # through sys.meta_path while resolving the engine's real loader.
        spec = self._path_finder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None:
            spec.loader = self._loader_type(spec.loader, self._installer)
        return spec


_install_engine_guards(_engine)

# guarded.py may itself be reloaded. Keep exactly one retained finder; the
# existing finder keeps a trusted installer generation instead of consulting
# later-rebindable guarded-module helper names during an engine reload.
if not any(getattr(finder, _FINDER_MARKER, False) for finder in sys.meta_path):
    sys.meta_path.insert(
        0,
        _ReloadGuardFinder(_ENGINE_NAME, _ReloadGuardLoader, _install_engine_guards),
    )


def _make_public_api(engine_module: ModuleType):
    """Capture the engine module object so rebinding guarded._engine is inert."""

    def normalize_packet(packet: Any):
        return engine_module.normalize_packet(packet)

    def compile_board(packet: Any, *, now: Optional[datetime] = None):
        return engine_module.compile_board(packet, now=now)

    def verify_board(packet: Any, board: Any, *, now: Optional[datetime] = None):
        return engine_module.verify_board(packet, board, now=now)

    return normalize_packet, compile_board, verify_board


normalize_packet, compile_board, verify_board = _make_public_api(_engine)
