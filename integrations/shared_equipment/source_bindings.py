"""Bind exact source accounts to existing authenticated native readers.

The host supplies the reader and a stable, nonsecret ID for its actual route.
This registry does not acquire credentials, switch accounts, or admit peers.
Readers return ``payload``, the actual ``account_ref``, and nonsecret
``binding_evidence``; native payloads pass through without projection.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from importlib import import_module
import json
from threading import RLock
from typing import Callable

from integrations.shared_equipment.outcomes import effect_uncertain, tool_failed
from integrations.shared_equipment.provider_io import EquipmentError, redacted
from integrations.shared_equipment.slack_read_arguments import normalize_slack_read_arguments


def _unresolved(message):
    return EquipmentError(message, code="source_binding_unresolved", uncertain=False)


def _mismatch(message):
    return EquipmentError(message, code="source_binding_mismatch", uncertain=False)


def _public_reference(value, label):
    if (not isinstance(value, str) or not value.strip()
            or value != value.strip() or redacted(value) != value):
        raise _unresolved("Source binding requires a nonsecret " + label)
    return value


def _binding_evidence(value):
    if not isinstance(value, (str, dict)) or not value:
        raise _unresolved("Source reader returned no account binding evidence")
    if isinstance(value, str) and not value.strip():
        raise _unresolved("Source reader returned no account binding evidence")
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise _unresolved("Source binding evidence is not a public identity reference") from None
    if redacted(value) != value or redacted(encoded) != encoded:
        raise _unresolved("Source binding evidence contains credential material")
    return value


@dataclass(frozen=True)
class SourceBinding:
    account_ref: str
    reader: Callable[[str, dict], dict] = field(repr=False, compare=False)
    service: str | None = None
    binding_id: str | None = None

    def __post_init__(self):
        _public_reference(self.account_ref, "account reference")
        _public_reference(self.binding_id, "reader route ID")
        if self.service is not None:
            _public_reference(self.service, "service reference")
        if not callable(self.reader):
            raise _unresolved("Source binding has no authenticated reader")

    def context(self):
        """Stable journal identity; never includes credentials or the callback."""
        return {"account_ref": self.account_ref, "service": self.service,
                "binding_id": self.binding_id}

    def call(self, name, args):
        """Read one native page and verify the account actually used by the host."""
        observed = self.reader(name, normalize_slack_read_arguments(name, deepcopy(args)))
        if (not isinstance(observed, Mapping) or "payload" not in observed
                or not isinstance(observed.get("account_ref"), str)
                or not observed["account_ref"].strip()):
            raise _unresolved("Source reader returned no actual account binding")
        if observed["account_ref"] != self.account_ref:
            raise _mismatch("Source reader used a different account")
        actual_service = observed.get("service")
        if actual_service is not None:
            _public_reference(actual_service, "observed service reference")
            if self.service is not None and actual_service != self.service:
                raise _mismatch("Source reader used a different service")
        evidence = _binding_evidence(observed.get("binding_evidence"))
        payload = observed["payload"]
        return {"result": payload,
                "source_context": {**self.context(), "binding_evidence": evidence},
                "isError": tool_failed(payload),
                "uncertain": effect_uncertain(payload)}


class SourceBindings:
    """Exact account lookup with no default-account or tool-name fallback.

    ``bindings`` maps account references to ``reader``, ``service`` and
    ``binding_id`` dictionaries, or to already constructed SourceBinding values.
    An explicit bind replaces that account's route. The host must change its
    binding_id when it changes the underlying authenticated route.
    """

    def __init__(self, bindings=None):
        self._bindings = {}
        self._lock = RLock()
        if bindings is None:
            return
        if not isinstance(bindings, Mapping):
            raise _unresolved("Source bindings must map account references to readers")
        for account_ref, value in bindings.items():
            if isinstance(value, SourceBinding):
                if account_ref != value.account_ref:
                    raise _mismatch("Source binding key names a different account")
                self.bind(account_ref, value.reader, service=value.service,
                          binding_id=value.binding_id)
            elif isinstance(value, Mapping):
                self.bind(account_ref, value.get("reader"), service=value.get("service"),
                          binding_id=value.get("binding_id"))
            else:
                raise _unresolved("Source binding has no authenticated reader configuration")

    def bind(self, account_ref, reader, *, service=None, binding_id=None):
        binding = SourceBinding(account_ref, reader, service, binding_id)
        with self._lock:
            self._bindings[account_ref] = binding
        return binding

    def resolve(self, account_ref, service=None):
        _public_reference(account_ref, "account reference")
        if service is not None:
            _public_reference(service, "service reference")
        with self._lock:
            binding = self._bindings.get(account_ref)
        if binding is None:
            raise _unresolved("No authenticated reader is bound to the selected account")
        if service is not None:
            if binding.service is None:
                raise _unresolved("The selected account's reader has no declared service")
            if binding.service != service:
                raise _mismatch("The selected account is bound to a different service")
        return binding

    def describe(self):
        with self._lock:
            return [self._bindings[key].context() for key in sorted(self._bindings)]


def source_bindings_from_config(config):
    """Load a trusted local factory for already authenticated native readers.

    ``source_reader_factory`` is ``module:callable``. It receives only
    ``source_reader_config`` and returns a SourceBindings instance or the same
    account mapping accepted by its constructor. With no factory, reads remain
    unresolved until a host binds an existing route explicitly.
    """
    if not isinstance(config, Mapping):
        raise _unresolved("Source reader configuration must be an object")
    specification = config.get("source_reader_factory")
    if specification is None:
        return SourceBindings()
    if not isinstance(specification, str):
        raise _unresolved("Source reader factory must name a local module and callable")
    module_name, separator, factory_name = specification.partition(":")
    if (not separator or not factory_name.isidentifier()
            or not module_name or not all(part.isidentifier() for part in module_name.split("."))):
        raise _unresolved("Source reader factory must name a local module and callable")
    try:
        factory = getattr(import_module(module_name), factory_name)
    except Exception:
        raise _unresolved("The configured local source reader factory is unavailable") from None
    if not callable(factory):
        raise _unresolved("The configured local source reader factory is not callable")
    try:
        bindings = factory(config.get("source_reader_config", {}))
    except EquipmentError:
        raise
    except Exception:
        raise _unresolved("The configured source reader factory could not bind its readers") from None
    if isinstance(bindings, SourceBindings):
        return bindings
    if isinstance(bindings, Mapping):
        return SourceBindings(bindings)
    raise _unresolved("The configured source reader factory returned no account bindings")
