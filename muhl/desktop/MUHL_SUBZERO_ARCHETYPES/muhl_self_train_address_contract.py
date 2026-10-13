#!/usr/bin/env python3
"""Training address contract utilities."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = "."
DEFAULT_CARD = os.path.join("ground", "MUHL_SELF_TRAIN_ADDRESS_CONTRACT.md")
CONTRACT_REL = os.path.join(
    "muhl",
    "desktop",
    "MUHL_SUBZERO_ARCHETYPES",
    "muhl_self_train_address_contract.py",
)
TRAINER_REL = os.path.join(
    "muhl",
    "desktop",
    "MUHL_SUBZERO_ARCHETYPES",
    "muhl_self_train.py",
)
TRAINER_NAME = "muhl_self_train.py"
TEST_REL = "test_muhl_self_train_address_contract.py"
H006_CARD = os.path.join("ground", "MUHL_TRAIN_BRIDGE.md")
H006_HOST = os.path.join("host", "muhl_train_bridge.py")
SLACK_TS = "1787648830.269449"
TAKING_ID = "muhl-self-train-address-contract-20260825-01"
CLAIMED_BASE = "683d0837f6b4b665bcffd32b5b6766ea48414058"
FORBIDDEN_IMPORTS = (
    "muhl_self_train",
    "pfc_paths",
    "titan_circuit",
)
UNRESOLVED = "UNRESOLVED"
CANDIDATE = "CANDIDATE"
DEFERRED = "DEFERRED"
SOURCE_NAMED = "SOURCE_NAMED"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
BLOCKED = "BLOCKED"
OK = "OK"
RELATIVE = "RELATIVE"
ABSOLUTE = "ABSOLUTE"
ONE_GIB = 1 << 30
TWO_BYTE_STEP = 2
NAMED_PTR_BITS = 30
NAMED_CAPACITY = 50 * ONE_GIB
MAX_POINTER = (1 << NAMED_PTR_BITS) - 1
LAST_SAFE_START = MAX_POINTER - 1
STEPS_BEFORE_WRAP = (1 << NAMED_PTR_BITS) // TWO_BYTE_STEP
REQUIRED_BITS = 36
PTR_BITS_CAPACITY_CONFLICT = "ptr_bits_vs_capacity"
ABSOLUTE_BASE_OVERFLOW = "absolute_base_overflow"
REGISTRY_HEADER_DISAGREEMENT = "registry_header_disagreement"
HEADER_LAYOUT_BYTES = 24
HEADER_FIELD_SPAN = 8
FOLLOWUP_SLACK_TS = "1787651271.265499"
FOLLOWUP_ID = "muhl-address-contract-integrity-followup-20260825-02"
STRIDE_MATH_SLACK_TS = "1787652385.567949"
STRIDE_MATH_ID = "muhl-address-contract-stride-math-20260825-01"
SEARCH_SPACE = (
    DEFAULT_CARD,
    CONTRACT_REL,
    TEST_REL,
    TRAINER_REL,
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "source-only",
    "dest from file",
    "no legacy trainer import",
    "no titan",
    "h-006 is candidate evidence only",
    "xproc harness is deferred",
    "unresolved",
    "never 0",
    "finder-failed",
    "talk is not a land",
    "no auth",
    "no gate",
    "do not remint",
    "max_pointer",
    "last_safe_start",
    "steps_before_wrap",
    "required_bits",
    "fail-closed",
    "blocked",
    "no named-default",
    "address-mode",
    "data-start",
    "stride",
    "tampered",
    "re-signed",
    "full-stride",
    "modular cycle",
)
REQUIRED_PACKET_FIELDS = (
    "kind",
    "source_index",
    "dests",
    "live_offsets",
    "host_inference",
    "titan",
    "legacy_trainer_import",
    "legacy_trainer_execute",
    "xproc",
    "h006",
)
NAMED_DEST_KEYS = (
    "name",
    "reservoir_input",
    "intake_header",
    "intake_capacity",
    "weight_bytes",
    "nw",
    "nf",
    "h",
    "ncls",
    "ptr_bits",
    "file_marker",
    "receiver",
    "write_ptr_rel",
    "size_rel",
    "capacity_rel",
    "data_start_rel",
)


def required_bits_for(span):
    """Bits needed to name pointers 0 .. span-1. Missing span stays None."""
    if not isinstance(span, int) or span <= 0:
        return None
    value = span - 1
    bits = 0
    while value:
        value >>= 1
        bits += 1
    return bits


def _valid_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _mode_text(value):
    if not isinstance(value, str):
        return UNRESOLVED
    mode = value.strip().upper()
    if mode in (RELATIVE, ABSOLUTE):
        return mode
    if mode in ("", UNRESOLVED):
        return UNRESOLVED
    return UNRESOLVED


def payload_digest(payload):
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def registry_header_disagreement(dests, registry=None):
    """Compare a presented registry row to dests FROM FILE. Missing is not 0."""
    dests = dests or {}
    if not isinstance(registry, dict) or not registry:
        return {
            "state": UNRESOLVED,
            "id": REGISTRY_HEADER_DISAGREEMENT,
            "reasons": ["missing_or_malformed_registry"],
            "note": (
                "registry row was not read. Absence is UNRESOLVED, never 0. "
                "No named-default substitution."
            ),
        }
    reasons = []
    header = dests.get("intake_header")
    capacity = dests.get("intake_capacity")
    data_start = dests.get("data_start_rel")
    if "header_len" in registry:
        if not _valid_positive_int(registry.get("header_len")):
            reasons.append("malformed_registry_header_len")
        elif not _valid_positive_int(header):
            reasons.append("missing_or_malformed_data_start")
        elif registry.get("header_len") != header:
            reasons.append("registry_header_len")
    if "capacity" in registry:
        if not _valid_positive_int(registry.get("capacity")):
            reasons.append("malformed_registry_capacity")
        elif not _valid_positive_int(capacity):
            reasons.append("missing_or_malformed_capacity")
        elif registry.get("capacity") != capacity:
            reasons.append("registry_capacity")
    if "data_start" in registry and _valid_positive_int(data_start):
        offset = registry.get("offset")
        header_len = registry.get("header_len")
        presented = registry.get("data_start")
        if not isinstance(presented, int) or isinstance(presented, bool):
            reasons.append("malformed_registry_data_start")
        elif isinstance(offset, int) and not isinstance(offset, bool) and _valid_positive_int(header_len):
            expected = offset + header_len
            if presented != expected or header_len != data_start:
                reasons.append("registry_data_start")
        elif presented != data_start:
            reasons.append("registry_data_start")
    if not reasons:
        return None
    return {
        "state": SOURCE_CONFLICT,
        "id": REGISTRY_HEADER_DISAGREEMENT,
        "reasons": reasons,
        "note": (
            "registry/header-disagreement: %s. fail-closed BLOCKED. "
            "Live allocated offsets stay UNRESOLVED. Never 0."
            % ", ".join(reasons)
        ),
    }


def pointer_space(ptr_bits=None, capacity=None, stride=None, address_mode=None, absolute_base=None):
    """Full-stride bounds and modular wrap-cycle. Missing stays UNRESOLVED."""
    reasons = []
    bits = ptr_bits if _valid_positive_int(ptr_bits) else UNRESOLVED
    step = stride if _valid_positive_int(stride) else UNRESOLVED
    if bits is UNRESOLVED:
        reasons.append("missing_or_malformed_ptr_bits")
    if not _valid_positive_int(capacity):
        reasons.append("missing_or_malformed_capacity")
    if step is UNRESOLVED:
        reasons.append("missing_or_malformed_stride")
    pointer_span = (1 << bits) if bits is not UNRESOLVED else UNRESOLVED
    mode = _mode_text(address_mode)
    base = (
        absolute_base
        if mode == ABSOLUTE
        and isinstance(absolute_base, int)
        and not isinstance(absolute_base, bool)
        and absolute_base >= 0
        else UNRESOLVED
    )
    declared_span = capacity if _valid_positive_int(capacity) else UNRESOLVED
    if mode == ABSOLUTE and isinstance(base, int) and isinstance(declared_span, int):
        max_pointer = base + declared_span - 1
        wrap_span = declared_span
    else:
        max_pointer = (pointer_span - 1) if isinstance(pointer_span, int) else UNRESOLVED
        wrap_span = pointer_span
    last_safe_start = UNRESOLVED
    steps_before_wrap = UNRESOLVED
    if isinstance(wrap_span, int) and isinstance(step, int):
        if step > wrap_span:
            reasons.append(
                "stride_exceeds_declared_capacity"
                if mode == ABSOLUTE
                else "stride_exceeds_pointer_space"
            )
        else:
            last_safe_start = wrap_span - step
            if mode == ABSOLUTE and isinstance(base, int):
                last_safe_start += base
        steps_before_wrap = wrap_span // math.gcd(step, wrap_span)
    needed_input = (
        base + declared_span
        if mode == ABSOLUTE and isinstance(base, int) and isinstance(declared_span, int)
        else capacity
    )
    needed = required_bits_for(needed_input)
    return {
        "max_pointer": max_pointer,
        "last_safe_start": last_safe_start,
        "steps_before_wrap": steps_before_wrap,
        "required_bits": needed if needed is not None else UNRESOLVED,
        "stride": step,
        "reasons": reasons,
    }


def bind_address_facts(dests=None, registry=None, ptr_bits=None, capacity=None, stride=None, address_mode=None, data_start=None, absolute_base=None):
    """Bind stride/address-mode/data-start/status/reasons plus derived fields.

    Missing or malformed address facts stay UNRESOLVED. No named-default
    substitution. Live allocated offsets stay UNRESOLVED.
    """
    dests = dict(dests or {})
    if ptr_bits is None:
        ptr_bits = dests.get("ptr_bits")
    if capacity is None:
        capacity = dests.get("intake_capacity")
    if stride is None:
        stride = dests.get("stride")
    if address_mode is None:
        address_mode = dests.get("address_mode")
    if data_start is None:
        data_start = dests.get("data_start_rel")
    if absolute_base is None:
        absolute_base = dests.get("absolute_base")
    reasons = []
    mode = _mode_text(address_mode)
    if isinstance(address_mode, str) and address_mode.strip() and mode is UNRESOLVED:
        reasons.append("malformed_address_mode")
    if not _valid_positive_int(ptr_bits):
        ptr_bits = UNRESOLVED
        reasons.append("missing_or_malformed_ptr_bits")
    if not _valid_positive_int(capacity):
        capacity = UNRESOLVED
        reasons.append("missing_or_malformed_capacity")
    if not _valid_positive_int(stride):
        stride = UNRESOLVED
        reasons.append("missing_or_malformed_stride")
    if not _valid_positive_int(data_start):
        data_start = UNRESOLVED
        reasons.append("missing_or_malformed_data_start")
    base = absolute_base
    if mode == ABSOLUTE and not (isinstance(base, int) and not isinstance(base, bool) and base >= 0):
        base = UNRESOLVED
        reasons.append("missing_or_malformed_absolute_base")
    elif mode != ABSOLUTE:
        base = UNRESOLVED if not (isinstance(base, int) and not isinstance(base, bool) and base >= 0) else base
    space = pointer_space(
        ptr_bits=ptr_bits,
        capacity=capacity,
        stride=stride,
        address_mode=mode,
        absolute_base=base,
    )
    if mode == ABSOLUTE and isinstance(base, int) and not isinstance(base, bool) and base >= 0 and _valid_positive_int(capacity):
        needed = required_bits_for(base + capacity)
        space["required_bits"] = needed if needed is not None else UNRESOLVED
    status = OK
    if (
        ptr_bits is UNRESOLVED
        or capacity is UNRESOLVED
        or stride is UNRESOLVED
        or data_start is UNRESOLVED
    ):
        status = UNRESOLVED
    elif mode == ABSOLUTE and not (isinstance(base, int) and not isinstance(base, bool) and base >= 0):
        status = UNRESOLVED
    elif mode == ABSOLUTE and isinstance(base, int) and not isinstance(base, bool):
        pointer_span = 1 << ptr_bits
        if (base + capacity) > pointer_span:
            status = BLOCKED
            reasons.append(ABSOLUTE_BASE_OVERFLOW)
    elif (1 << ptr_bits) != capacity:
        status = BLOCKED
        reasons.append(PTR_BITS_CAPACITY_CONFLICT)
    elif mode is UNRESOLVED:
        status = UNRESOLVED
        reasons.append("missing_or_malformed_address_mode")
    for reason in space.get("reasons") or []:
        if reason in ("stride_exceeds_pointer_space", "stride_exceeds_declared_capacity"):
            if reason not in reasons:
                reasons.append(reason)
            if status == OK:
                status = BLOCKED
    registry_row = registry_header_disagreement(dests, registry)
    if registry_row and registry_row.get("state") == SOURCE_CONFLICT:
        status = BLOCKED
        reasons.extend(registry_row.get("reasons") or [])
        reasons.append(REGISTRY_HEADER_DISAGREEMENT)
    conflict_id = PTR_BITS_CAPACITY_CONFLICT
    if ABSOLUTE_BASE_OVERFLOW in reasons:
        conflict_id = ABSOLUTE_BASE_OVERFLOW
    elif REGISTRY_HEADER_DISAGREEMENT in reasons:
        conflict_id = REGISTRY_HEADER_DISAGREEMENT
    payload = {
        "id": conflict_id,
        "address_mode": mode,
        "data_start": data_start,
        "last_safe_start": space["last_safe_start"],
        "max_pointer": space["max_pointer"],
        "named_capacity": capacity,
        "ptr_bits": ptr_bits,
        "reasons": list(reasons),
        "required_bits": space["required_bits"],
        "status": status,
        "steps_before_wrap": space["steps_before_wrap"],
        "stride": stride,
    }
    if mode == ABSOLUTE:
        payload["absolute_base"] = base
    digest = payload_digest(payload)
    return {
        "max_pointer": space["max_pointer"],
        "last_safe_start": space["last_safe_start"],
        "steps_before_wrap": space["steps_before_wrap"],
        "required_bits": space["required_bits"],
        "stride": stride,
        "address_mode": mode,
        "data_start": data_start,
        "absolute_base": base if mode == ABSOLUTE else UNRESOLVED,
        "named_capacity": capacity,
        "ptr_bits": ptr_bits,
        "status": status,
        "reasons": list(reasons),
        "canonical_payload": payload,
        "canonical_hash": digest,
        "registry": registry_row,
    }


def canonical_conflict_payload(space=None, ptr_bits=None, capacity=None, stride=None, address_mode=None, data_start=None, dests=None, registry=None, absolute_base=None):
    bound = bind_address_facts(
        dests=dests,
        registry=registry,
        ptr_bits=ptr_bits,
        capacity=capacity,
        stride=stride,
        address_mode=address_mode,
        data_start=data_start,
        absolute_base=absolute_base,
    )
    if space:
        payload = dict(bound["canonical_payload"])
        for key in ("max_pointer", "last_safe_start", "steps_before_wrap", "required_bits"):
            if key in space:
                payload[key] = space[key]
        if "stride" in space:
            payload["stride"] = space["stride"]
        bound["canonical_payload"] = payload
        bound["canonical_hash"] = payload_digest(payload)
    return bound["canonical_payload"]


def canonical_conflict_hash(space=None, ptr_bits=None, capacity=None, stride=None, address_mode=None, data_start=None, dests=None, registry=None, absolute_base=None):
    payload = canonical_conflict_payload(
        space=space,
        ptr_bits=ptr_bits,
        capacity=capacity,
        stride=stride,
        address_mode=address_mode,
        data_start=data_start,
        dests=dests,
        registry=registry,
        absolute_base=absolute_base,
    )
    return payload_digest(payload)


def validate_canonical_record(record, dests=None, registry=None):
    """Recompute semantics. Reject tampered or re-signed records."""
    expected = bind_address_facts(dests, registry=registry)
    expected_payload = expected["canonical_payload"]
    expected_hash = expected["canonical_hash"]
    if not isinstance(record, dict) or not record:
        return {
            "state": UNRESOLVED,
            "note": (
                "canonical record missing. Absence is UNRESOLVED, never 0. "
                "No named-default substitution."
            ),
            "z": "FINDER-FAILED",
            "canonical_payload": expected_payload,
            "canonical_hash": expected_hash,
        }
    presented_payload = record.get("canonical_payload")
    presented_hash = record.get("canonical_hash")
    if presented_payload is not None:
        if not isinstance(presented_payload, dict):
            return {
                "state": "NOT_LANDED",
                "note": (
                    "tampered: malformed canonical_payload. Recomputed "
                    "semantics win. FINDER-FAILED, never 0."
                ),
                "z": "FINDER-FAILED",
                "canonical_payload": expected_payload,
                "canonical_hash": expected_hash,
            }
        if presented_payload != expected_payload:
            return {
                "state": "NOT_LANDED",
                "note": (
                    "tampered: canonical payload does not match recomputed "
                    "semantics. FINDER-FAILED, never 0."
                ),
                "z": "FINDER-FAILED",
                "canonical_payload": expected_payload,
                "canonical_hash": expected_hash,
            }
        resigned = payload_digest(presented_payload)
        if presented_hash and presented_hash != resigned:
            return {
                "state": "NOT_LANDED",
                "note": (
                    "re-signed: presented hash does not bind the presented "
                    "payload. FINDER-FAILED, never 0."
                ),
                "z": "FINDER-FAILED",
                "canonical_payload": expected_payload,
                "canonical_hash": expected_hash,
            }
        if resigned != expected_hash:
            return {
                "state": "NOT_LANDED",
                "note": (
                    "tampered: payload hash does not match recomputed hash. "
                    "FINDER-FAILED, never 0."
                ),
                "z": "FINDER-FAILED",
                "canonical_payload": expected_payload,
                "canonical_hash": expected_hash,
            }
    if presented_hash is not None and presented_hash != expected_hash:
        return {
            "state": "NOT_LANDED",
            "note": (
                "re-signed or tampered: hash does not match recomputed "
                "semantics. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
            "canonical_payload": expected_payload,
            "canonical_hash": expected_hash,
        }
    state = expected["status"]
    if state == OK:
        state = "VALID"
    return {
        "state": state,
        "note": (
            "canonical record matches recomputed semantics. status=%s. "
            "Live allocated offsets stay UNRESOLVED."
            % expected["status"]
        ),
        "z": "" if expected["status"] != UNRESOLVED else "FINDER-FAILED",
        "canonical_payload": expected_payload,
        "canonical_hash": expected_hash,
        "max_pointer": expected["max_pointer"],
        "last_safe_start": expected["last_safe_start"],
        "steps_before_wrap": expected["steps_before_wrap"],
        "required_bits": expected["required_bits"],
        "reasons": expected["reasons"],
    }


def source_space_conflicts(dests, registry=None):
    """Deterministic source-space conflicts. Never invent live offsets."""
    dests = dests or {}
    bound = bind_address_facts(dests, registry=registry)
    conflicts = []
    if bound["status"] != BLOCKED:
        return conflicts
    digest = bound["canonical_hash"]
    payload = bound["canonical_payload"]
    conflict_id = payload.get("id") or PTR_BITS_CAPACITY_CONFLICT
    conflicts.append(
        {
            "id": conflict_id,
            "state": SOURCE_CONFLICT,
            "max_pointer": bound["max_pointer"],
            "last_safe_start": bound["last_safe_start"],
            "steps_before_wrap": bound["steps_before_wrap"],
            "required_bits": bound["required_bits"],
            "stride": bound["stride"],
            "address_mode": bound["address_mode"],
            "data_start": bound["data_start"],
            "status": BLOCKED,
            "reasons": bound["reasons"],
            "canonical_hash": digest,
            "canonical_payload": payload,
            "note": (
                "source-space integrity is fail-closed BLOCKED. "
                "ptr_bits=%s capacity=%s stride=%s address-mode=%s "
                "data-start=%s status=%s reasons=%s max_pointer=%s "
                "last_safe_start=%s steps_before_wrap=%s required_bits=%s "
                "canonical_hash=%s. Live allocated offsets stay UNRESOLVED. "
                "Never 0. No named-default substitution."
                % (
                    bound["ptr_bits"],
                    bound["named_capacity"],
                    bound["stride"],
                    bound["address_mode"],
                    bound["data_start"],
                    bound["status"],
                    ",".join(bound["reasons"]),
                    bound["max_pointer"],
                    bound["last_safe_start"],
                    bound["steps_before_wrap"],
                    bound["required_bits"],
                    digest,
                )
            ),
        }
    )
    return conflicts


def conflict_is_source_space(item):
    return str((item or {}).get("state") or "").strip().upper() == SOURCE_CONFLICT


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _const_int(node, env=None):
    env = env or {}
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _const_int(node.operand, env)
        return None if value is None else -value
    if isinstance(node, ast.Name):
        value = env.get(node.id)
        return value if isinstance(value, int) else None
    if isinstance(node, ast.BinOp):
        left = _const_int(node.left, env)
        right = _const_int(node.right, env)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.LShift):
            return left << right
    return None


def _const_text(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bytes):
            return node.value.decode("ascii", "replace")
        if isinstance(node.value, str):
            return node.value
    return None


def parse_trainer_source(text):
    """Read dests FROM FILE. Parse is not import and not execute."""
    if not str(text or "").strip():
        return {
            "ok": False,
            "state": UNRESOLVED,
            "z": "FINDER-FAILED",
            "note": (
                "trainer source not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
            "dests": {},
            "live_offsets": UNRESOLVED,
            "conflicts": [],
        }
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {
            "ok": False,
            "state": UNRESOLVED,
            "z": "FINDER-FAILED",
            "note": "trainer source is not parseable: %s. FINDER-FAILED, never 0." % exc,
            "dests": {},
            "live_offsets": UNRESOLVED,
            "conflicts": [],
        }
    env = {}
    dests = {}
    receiver = UNRESOLVED
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        number = _const_int(node.value, env)
        if number is not None:
            env[name] = number
        text_value = _const_text(node.value)
        if name == "NAME" and text_value:
            dests["name"] = text_value
        elif name == "RESERVOIR_INPUT" and number is not None:
            dests["reservoir_input"] = number
        elif name == "INTAKE_HEADER" and number is not None:
            dests["intake_header"] = number
        elif name == "INTAKE_CAPACITY" and number is not None:
            dests["intake_capacity"] = number
        elif name == "WEIGHT_BYTES" and number is not None:
            dests["weight_bytes"] = number
        elif name == "NW" and number is not None:
            dests["nw"] = number
        elif name == "NF" and number is not None:
            dests["nf"] = number
        elif name == "H" and number is not None:
            dests["h"] = number
        elif name == "NCLS" and number is not None:
            dests["ncls"] = number
        elif name == "PTR_BITS" and number is not None:
            dests["ptr_bits"] = number
        elif name == "STRIDE" and number is not None:
            dests["stride"] = number
        elif name == "ADDRESS_MODE" and text_value:
            dests["address_mode"] = text_value.strip().upper()
        elif name == "ABSOLUTE_BASE" and number is not None:
            dests["absolute_base"] = number
        elif name == "FILE_MARKER" and text_value:
            dests["file_marker"] = text_value
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "receiver":
                value = _const_text(keyword.value)
                if value:
                    receiver = value
    dests["receiver"] = receiver
    lowered = text.lower()
    if dests.get("stride") is None and (
        "ptr_val + 2" in lowered or "ptr_val+2" in lowered.replace(" ", "")
    ):
        dests["stride"] = TWO_BYTE_STEP
    if dests.get("address_mode") is None:
        if "address 1 gb intake data area" in lowered:
            dests["address_mode"] = RELATIVE
        elif "address-mode" in lowered and "relative" in lowered:
            dests["address_mode"] = RELATIVE
    header = dests.get("intake_header")
    if header == HEADER_LAYOUT_BYTES:
        dests["write_ptr_rel"] = 0
        dests["size_rel"] = HEADER_FIELD_SPAN
        dests["capacity_rel"] = HEADER_FIELD_SPAN * 2
        dests["data_start_rel"] = HEADER_LAYOUT_BYTES
    else:
        dests["write_ptr_rel"] = UNRESOLVED
        dests["size_rel"] = UNRESOLVED
        dests["capacity_rel"] = UNRESOLVED
        dests["data_start_rel"] = (
            header if _valid_positive_int(header) else UNRESOLVED
        )
    if dests.get("stride") is None:
        dests["stride"] = UNRESOLVED
    if dests.get("address_mode") is None:
        dests["address_mode"] = UNRESOLVED
    conflicts = []
    capacity = dests.get("intake_capacity")
    space = pointer_space(
        ptr_bits=dests.get("ptr_bits"),
        capacity=capacity,
        stride=dests.get("stride"),
        address_mode=dests.get("address_mode"),
        absolute_base=dests.get("absolute_base"),
    )
    if isinstance(capacity, int) and capacity != ONE_GIB and "1 GB" in text:
        conflicts.append(
            {
                "id": "intake_capacity_comment",
                "state": SOURCE_CONFLICT,
                "max_pointer": space["max_pointer"],
                "last_safe_start": space["last_safe_start"],
                "steps_before_wrap": space["steps_before_wrap"],
                "required_bits": space["required_bits"],
                "note": (
                    "source names INTAKE_CAPACITY=%s while comments still "
                    "say 1 GB. fail-closed BLOCKED. max_pointer=%s "
                    "last_safe_start=%s steps_before_wrap=%s "
                    "required_bits=%s. Live size stays UNRESOLVED. Never 0. "
                    "No named-default substitution."
                    % (
                        capacity,
                        space["max_pointer"],
                        space["last_safe_start"],
                        space["steps_before_wrap"],
                        space["required_bits"],
                    )
                ),
            }
        )
    conflicts.extend(source_space_conflicts(dests))
    missing = [key for key in NAMED_DEST_KEYS if dests.get(key) in (None, "", UNRESOLVED)]
    ok = not missing
    return {
        "ok": ok,
        "state": SOURCE_NAMED if ok else UNRESOLVED,
        "z": "" if ok else "FINDER-FAILED",
        "note": (
            "named dests read FROM FILE. Live allocated offsets stay "
            "UNRESOLVED."
            if ok
            else (
                "named dests missing from trainer source: "
                + ", ".join(missing)
                + ". FINDER-FAILED, never 0."
            )
        ),
        "dests": dests,
        "live_offsets": {
            "intake_off": UNRESOLVED,
            "weights_off": UNRESOLVED,
            "circuit_off": UNRESOLVED,
            "state_off": UNRESOLVED,
            "loop_bit_off": UNRESOLVED,
        },
        "conflicts": conflicts,
        "missing": missing,
    }


def trainer_imported():
    return any(name in sys.modules for name in FORBIDDEN_IMPORTS)


def classify_h006(root):
    """H-006 is candidate evidence only. Missing stays UNRESOLVED, never 0."""
    card = _exists(root, H006_CARD)
    host = _exists(root, H006_HOST)
    if card or host:
        return {
            "state": CANDIDATE,
            "note": (
                "H-006 / MUHL_TRAIN_BRIDGE is present as candidate "
                "evidence only. It is not a live train and not this leftover."
            ),
            "paths": [rel for rel in (H006_CARD, H006_HOST) if _exists(root, rel)],
        }
    return {
        "state": UNRESOLVED,
        "note": (
            "H-006 / MUHL_TRAIN_BRIDGE was not read on this tree. "
            "Absence is UNRESOLVED, never 0."
        ),
        "paths": [],
        "z": "FINDER-UNVERIFIED",
    }


def synthetic_packet(parsed=None):
    dests = dict((parsed or {}).get("dests") or {})
    return {
        "kind": "MUHL_SELF_TRAIN_ADDRESS",
        "source_index": TRAINER_REL,
        "dests": dests,
        "live_offsets": UNRESOLVED,
        "host_inference": False,
        "titan": "NOT_WRITTEN",
        "legacy_trainer_import": False,
        "legacy_trainer_execute": False,
        "xproc": DEFERRED,
        "h006": CANDIDATE,
    }


def validate_packet(obj, parsed=None):
    """Classify one synthetic address packet. Unchanged/missing is never 0."""
    if not isinstance(obj, dict) or not obj:
        return {
            "state": "UNMEASURED",
            "note": (
                "address packet not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    kind = str(obj.get("kind") or "").strip().upper()
    if kind in ("TAKING", "TAKING_BACKEND_SWARM"):
        return {
            "state": "CARRIER_ONLY",
            "note": (
                "Slack taking is mail. Talk is CLAIMED until the leftover "
                "ships. FINDER-UNVERIFIED, never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    if kind != "MUHL_SELF_TRAIN_ADDRESS":
        return {
            "state": "NOT_LANDED",
            "note": "kind is not MUHL_SELF_TRAIN_ADDRESS. FINDER-FAILED, never 0.",
            "z": "FINDER-FAILED",
        }
    missing = [field for field in REQUIRED_PACKET_FIELDS if field not in obj]
    if missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing fields: "
                + ", ".join(missing)
                + ". FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if obj.get("host_inference") is True or str(obj.get("host_inference")).lower() == "true":
        return {
            "state": "NOT_LANDED",
            "note": "host inference is refused. Source-only. FINDER-FAILED, never 0.",
            "z": "FINDER-FAILED",
        }
    if obj.get("legacy_trainer_import") is True or obj.get("legacy_trainer_execute") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "legacy trainer import/execute is refused. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    titan = str(obj.get("titan") or "").strip().upper()
    if titan not in ("NOT_WRITTEN", "NOT_LANDED"):
        return {
            "state": "NOT_LANDED",
            "note": "live Titan is refused. titan stays NOT_WRITTEN. FINDER-FAILED, never 0.",
            "z": "FINDER-FAILED",
        }
    live = obj.get("live_offsets")
    if live in (0, "0", 0.0) or live is None:
        return {
            "state": "NOT_LANDED",
            "note": (
                "live allocated offsets must stay UNRESOLVED. A zero is a "
                "broken test. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if str(live).strip().upper() != UNRESOLVED and not (
        isinstance(live, dict)
        and all(str(value).strip().upper() == UNRESOLVED for value in live.values())
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "invented live offsets are refused. Dest FROM FILE only. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if str(obj.get("xproc") or "").strip().upper() not in (DEFERRED, UNRESOLVED):
        return {
            "state": "NOT_LANDED",
            "note": "larger xproc harness stays DEFERRED / UNRESOLVED. Never 0.",
            "z": "FINDER-FAILED",
        }
    h006 = str(obj.get("h006") or "").strip().upper()
    if h006 not in (CANDIDATE, UNRESOLVED):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-006 is candidate evidence only. Do not treat it as a live "
                "train. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    dests = obj.get("dests")
    if not isinstance(dests, dict) or not dests:
        return {
            "state": "NOT_LANDED",
            "note": "dests missing. Dest FROM FILE. FINDER-FAILED, never 0.",
            "z": "FINDER-FAILED",
        }
    if parsed and parsed.get("ok"):
        expected = parsed.get("dests") or {}
        for key in NAMED_DEST_KEYS:
            if dests.get(key) != expected.get(key):
                return {
                    "state": "NOT_LANDED",
                    "note": (
                        "dest %s does not match trainer source. FINDER-FAILED, never 0."
                        % key
                    ),
                    "z": "FINDER-FAILED",
                }
    registry = obj.get("registry")
    if registry is None and parsed:
        registry = parsed.get("registry")
    bound = bind_address_facts(dests, registry=registry)
    presented = {}
    if "canonical_payload" in obj or "canonical_hash" in obj:
        presented = {
            "canonical_payload": obj.get("canonical_payload"),
            "canonical_hash": obj.get("canonical_hash"),
        }
    elif isinstance(obj.get("integrity"), dict):
        presented = obj.get("integrity") or {}
    if presented:
        checked = validate_canonical_record(presented, dests=dests, registry=registry)
        if checked.get("state") == "NOT_LANDED":
            return checked
    found = []
    for item in list((parsed or {}).get("conflicts") or []):
        if conflict_is_source_space(item):
            found.append(item)
    for item in source_space_conflicts(dests, registry=registry):
        if item.get("id") not in {row.get("id") for row in found}:
            found.append(item)
    if bound["status"] == UNRESOLVED and bound["reasons"]:
        return {
            "state": UNRESOLVED,
            "note": (
                "missing or malformed address facts stay UNRESOLVED: %s. "
                "No named-default substitution. Live offsets stay "
                "UNRESOLVED. Never 0."
                % ",".join(bound["reasons"])
            ),
            "z": "FINDER-FAILED",
            "max_pointer": bound["max_pointer"],
            "last_safe_start": bound["last_safe_start"],
            "steps_before_wrap": bound["steps_before_wrap"],
            "required_bits": bound["required_bits"],
            "stride": bound["stride"],
            "address_mode": bound["address_mode"],
            "data_start": bound["data_start"],
            "status": UNRESOLVED,
            "reasons": bound["reasons"],
            "canonical_hash": bound["canonical_hash"],
            "canonical_payload": bound["canonical_payload"],
        }
    if found or bound["status"] == BLOCKED:
        record = next(
            (item for item in found if item.get("id") == PTR_BITS_CAPACITY_CONFLICT),
            found[0] if found else bound,
        )
        if presented:
            checked = validate_canonical_record(record, dests=dests, registry=registry)
            if checked.get("state") == "NOT_LANDED":
                return checked
        digest = bound["canonical_hash"]
        return {
            "state": BLOCKED,
            "note": (
                "deterministic source-space conflict is fail-closed BLOCKED. "
                "max_pointer=%s last_safe_start=%s steps_before_wrap=%s "
                "required_bits=%s stride=%s address-mode=%s data-start=%s "
                "canonical_hash=%s. Live offsets stay UNRESOLVED. Never 0. "
                "No named-default substitution."
                % (
                    bound["max_pointer"],
                    bound["last_safe_start"],
                    bound["steps_before_wrap"],
                    bound["required_bits"],
                    bound["stride"],
                    bound["address_mode"],
                    bound["data_start"],
                    digest,
                )
            ),
            "z": "FINDER-FAILED",
            "max_pointer": bound["max_pointer"],
            "last_safe_start": bound["last_safe_start"],
            "steps_before_wrap": bound["steps_before_wrap"],
            "required_bits": bound["required_bits"],
            "stride": bound["stride"],
            "address_mode": bound["address_mode"],
            "data_start": bound["data_start"],
            "status": BLOCKED,
            "reasons": bound["reasons"],
            "canonical_hash": digest,
            "canonical_payload": bound["canonical_payload"],
            "conflicts": found,
        }
    return {
        "state": "SYNTHETIC_OK",
        "note": (
            "source-only address packet is well-formed. 1 GiB / 30-bit "
            "relative is OK. Live offsets stay UNRESOLVED. H-006 stays "
            "candidate. xproc stays deferred. This is not a live train."
        ),
        "z": "",
        "max_pointer": bound["max_pointer"],
        "last_safe_start": bound["last_safe_start"],
        "steps_before_wrap": bound["steps_before_wrap"],
        "required_bits": bound["required_bits"],
        "stride": bound["stride"],
        "address_mode": bound["address_mode"],
        "data_start": bound["data_start"],
        "canonical_hash": bound["canonical_hash"],
        "canonical_payload": bound["canonical_payload"],
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "contract_present": bool(facts.get("contract_present")),
        "test_present": bool(facts.get("test_present")),
        "trainer_present": bool(facts.get("trainer_present")),
        "parsed_ok": bool(facts.get("parsed_ok")),
        "dests": dict(facts.get("dests") or {}),
        "live_offsets": facts.get("live_offsets") or UNRESOLVED,
        "conflicts": list(facts.get("conflicts") or []),
        "max_pointer": facts.get("max_pointer", UNRESOLVED),
        "last_safe_start": facts.get("last_safe_start", UNRESOLVED),
        "steps_before_wrap": facts.get("steps_before_wrap", UNRESOLVED),
        "required_bits": facts.get("required_bits", UNRESOLVED),
        "stride": facts.get("stride", UNRESOLVED),
        "address_mode": facts.get("address_mode", UNRESOLVED),
        "data_start": facts.get("data_start", UNRESOLVED),
        "reasons": list(facts.get("reasons") or []),
        "canonical_payload": dict(facts.get("canonical_payload") or {}),
        "canonical_hash": facts.get("canonical_hash") or UNRESOLVED,
        "found_phrases": list(facts.get("found_phrases") or []),
        "h006": dict(facts.get("h006") or {}),
        "xproc": str(facts.get("xproc") or DEFERRED),
        "packet_ok": bool(facts.get("packet_ok")),
        "legacy_import": bool(facts.get("legacy_import")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "slack_ts": str(facts.get("slack_ts") or SLACK_TS),
        "taking_id": str(facts.get("taking_id") or TAKING_ID),
    }


def classify(row):
    """Turn a measured address-contract leftover into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "self-train address-contract leftover not read. Absence was "
                "not stillness. A Slack TAKING is not a land. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence "
                "proof. FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("legacy_import"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "legacy trainer / pfc_paths / titan_circuit was imported. "
                "Source-only leftover refuses that. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    if (
        not row.get("card_present")
        or not row.get("contract_present")
        or not row.get("test_present")
        or not row.get("trainer_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/contract/test/trainer"])
                + ". Slack TAKING stays CLAIMED. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("parsed_ok"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "trainer source did not yield named dests FROM FILE. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    conflicts = [item for item in list(row.get("conflicts") or []) if conflict_is_source_space(item)]
    if conflicts:
        record = next(
            (item for item in conflicts if item.get("id") == PTR_BITS_CAPACITY_CONFLICT),
            conflicts[0],
        )
        bound = bind_address_facts(row.get("dests") or {})
        presented = {
            "canonical_payload": record.get("canonical_payload"),
            "canonical_hash": record.get("canonical_hash"),
        }
        if presented.get("canonical_payload") or presented.get("canonical_hash"):
            checked = validate_canonical_record(presented, dests=row.get("dests") or {})
            if checked.get("state") == "NOT_LANDED":
                return checked
        digest = bound["canonical_hash"]
        return {
            "state": BLOCKED,
            "note": (
                "deterministic source-space conflict is fail-closed BLOCKED. "
                "max_pointer=%s last_safe_start=%s steps_before_wrap=%s "
                "required_bits=%s stride=%s address-mode=%s data-start=%s "
                "canonical_hash=%s. Live allocated offsets stay UNRESOLVED. "
                "Never 0. No named-default substitution."
                % (
                    bound["max_pointer"],
                    bound["last_safe_start"],
                    bound["steps_before_wrap"],
                    bound["required_bits"],
                    bound["stride"],
                    bound["address_mode"],
                    bound["data_start"],
                    digest,
                )
            ),
            "z": "FINDER-FAILED",
            "taking_state": "CLAIMED",
            "max_pointer": bound["max_pointer"],
            "last_safe_start": bound["last_safe_start"],
            "steps_before_wrap": bound["steps_before_wrap"],
            "required_bits": bound["required_bits"],
            "stride": bound["stride"],
            "address_mode": bound["address_mode"],
            "data_start": bound["data_start"],
            "canonical_hash": digest,
            "canonical_payload": bound["canonical_payload"],
            "reasons": bound["reasons"],
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
    if (
        needed
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or not row.get("packet_ok")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    h006 = (row.get("h006") or {}).get("state") or UNRESOLVED
    if h006 not in (CANDIDATE, UNRESOLVED):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-006 must stay CANDIDATE or UNRESOLVED. Never treat it as "
                "a live train. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "self-train address-contract leftover is on this tree. Named "
            "dests are FROM FILE. Live allocated offsets stay UNRESOLVED. "
            "H-006 stays %s. xproc stays %s. A Slack TAKING is still not "
            "the file."
            % (h006, row.get("xproc") or DEFERRED)
        ),
        "z": "",
        "taking_state": "CLAIMED",
        "h006": h006,
        "xproc": row.get("xproc") or DEFERRED,
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        else:
            blobs.append(text)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    trainer_text = _read(root, TRAINER_REL)
    if not trainer_text:
        sibling = os.path.join(HERE, TRAINER_NAME)
        if os.path.isfile(sibling):
            with open(sibling, encoding="utf-8", errors="replace") as handle:
                trainer_text = handle.read()
    parsed = parse_trainer_source(trainer_text)
    packet = validate_packet(synthetic_packet(parsed), parsed=parsed)
    bound = bind_address_facts(parsed.get("dests") or {})
    h006 = classify_h006(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and ("calibration:" + rel) not in misses:
                misses.append("calibration:" + rel)
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "contract_present": _exists(root, CONTRACT_REL) or os.path.isfile(
            os.path.join(HERE, os.path.basename(CONTRACT_REL))
        ),
        "test_present": _exists(root, TEST_REL),
        "trainer_present": bool(trainer_text),
        "parsed_ok": bool(parsed.get("ok")),
        "dests": parsed.get("dests") or {},
        "live_offsets": parsed.get("live_offsets") or UNRESOLVED,
        "conflicts": parsed.get("conflicts") or [],
        "found_phrases": found,
        "h006": h006,
        "xproc": DEFERRED,
        "packet_ok": packet.get("state") == "SYNTHETIC_OK",
        "legacy_import": trainer_imported(),
        "posting_open": "open door" in hay and "unseated" in hay,
        "no_auth": "no auth" in hay,
        "no_gate": "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "taking_id": TAKING_ID,
        "max_pointer": bound["max_pointer"],
        "last_safe_start": bound["last_safe_start"],
        "steps_before_wrap": bound["steps_before_wrap"],
        "required_bits": bound["required_bits"],
        "stride": bound["stride"],
        "address_mode": bound["address_mode"],
        "data_start": bound["data_start"],
        "reasons": bound["reasons"],
        "canonical_payload": bound["canonical_payload"],
        "canonical_hash": bound["canonical_hash"],
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "parsed": parsed,
            "packet": packet,
            "h006": h006,
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "dests": parsed.get("dests") or {},
                "conflicts": parsed.get("conflicts") or [],
                "h006": h006.get("state"),
                "packet": packet.get("state"),
                "calibration_hits": calibration_hits,
            },
            "z": row.get("misses")
            or parsed.get("conflicts")
            or "FINDER-UNVERIFIED live offsets / xproc / unresolved evidence, never 0",
        }
    )
    return row


def self_test():
    empty = classify({})
    if empty.get("state") != "UNMEASURED":
        return False
    silent = validate_packet(
        {
            "kind": "MUHL_SELF_TRAIN_ADDRESS",
            "source_index": TRAINER_REL,
            "dests": {"name": "muhl_self_train"},
            "live_offsets": 0,
            "host_inference": False,
            "titan": "NOT_WRITTEN",
            "legacy_trainer_import": False,
            "legacy_trainer_execute": False,
            "xproc": DEFERRED,
            "h006": CANDIDATE,
        }
    )
    if silent.get("state") != "NOT_LANDED" or "never 0" not in silent.get("note", "").lower():
        return False
    missing = parse_trainer_source("")
    if missing.get("state") != UNRESOLVED or missing.get("z") != "FINDER-FAILED":
        return False
    conflicted = parse_trainer_source(
        "INTAKE_CAPACITY = 50 * (1 << 30)  # 1 GB\n"
        "PTR_BITS = 30\n"
        "STRIDE = 2\n"
        "ADDRESS_MODE = 'RELATIVE'\n"
        "INTAKE_HEADER = 24\n"
    )
    blocked = validate_packet(synthetic_packet(conflicted), parsed=conflicted)
    if blocked.get("state") != BLOCKED:
        return False
    if blocked.get("max_pointer") != MAX_POINTER:
        return False
    if blocked.get("last_safe_start") != LAST_SAFE_START:
        return False
    if blocked.get("steps_before_wrap") != STEPS_BEFORE_WRAP:
        return False
    if blocked.get("required_bits") != REQUIRED_BITS:
        return False
    if not blocked.get("canonical_hash"):
        return False
    missing = validate_packet(
        {
            "kind": "MUHL_SELF_TRAIN_ADDRESS",
            "source_index": TRAINER_REL,
            "dests": {"name": "muhl_self_train"},
            "live_offsets": UNRESOLVED,
            "host_inference": False,
            "titan": "NOT_WRITTEN",
            "legacy_trainer_import": False,
            "legacy_trainer_execute": False,
            "xproc": DEFERRED,
            "h006": CANDIDATE,
        }
    )
    if missing.get("state") != UNRESOLVED:
        return False
    if missing.get("max_pointer") != UNRESOLVED:
        return False
    odd = pointer_space(
        ptr_bits=8,
        capacity=256,
        stride=3,
        address_mode=RELATIVE,
    )
    if odd.get("last_safe_start") != 253:
        return False
    if odd.get("steps_before_wrap") != 256:
        return False
    if odd.get("last_safe_start") == 254:
        return False
    if odd.get("steps_before_wrap") == (256 // 3):
        return False
    absolute = bind_address_facts(
        {
            "ptr_bits": 4,
            "intake_capacity": 8,
            "stride": 3,
            "address_mode": ABSOLUTE,
            "absolute_base": 0,
            "data_start_rel": 1,
        }
    )
    if absolute.get("max_pointer") != 7:
        return False
    if absolute.get("last_safe_start") != 5:
        return False
    if absolute.get("steps_before_wrap") != 8:
        return False
    if (absolute.get("canonical_payload") or {}).get("absolute_base") != 0:
        return False
    tampered = dict(blocked.get("canonical_payload") or {})
    if tampered:
        tampered["max_pointer"] = 1
        forged = validate_packet(
            {
                "kind": "MUHL_SELF_TRAIN_ADDRESS",
                "source_index": TRAINER_REL,
                "dests": conflicted.get("dests") or {},
                "live_offsets": UNRESOLVED,
                "host_inference": False,
                "titan": "NOT_WRITTEN",
                "legacy_trainer_import": False,
                "legacy_trainer_execute": False,
                "xproc": DEFERRED,
                "h006": CANDIDATE,
                "canonical_payload": tampered,
                "canonical_hash": blocked.get("canonical_hash"),
            },
            parsed=conflicted,
        )
        if forged.get("state") != "NOT_LANDED":
            return False
        if "tampered" not in forged.get("note", "").lower():
            return False
    return trainer_imported() is False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the source-only self-train address contract"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
