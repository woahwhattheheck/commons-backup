"""LDA retarget + verify patterns, translated into the existing Windows adapter.

Source of the patterns (do not replace that Kotlin executor):
- ActionAccessibilityService.performActionJson() verb salvage and set_text retarget
- ActionAccessibilityService.verifyExpectation() / assert checkpoint
- AgentOrchestrator post-action expect check (action-return is not proof)

This module is a translation layer in TitanHandsServer. It does not add a second
executor, does not shrink the Windows or Android action lists, and does not copy
Android safety gates onto Windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .protocol import PROTOCOL_VERSION, failure


WINDOWS_ID_RE = re.compile(r"^w_[0-9a-f]{16,}$", re.IGNORECASE)
LABEL_NOISE_RE = re.compile(r"[^a-z0-9]+")
WORD_RE = re.compile(r"\b[a-z0-9]{4,}\b")

# Salvage LDA off-list names onto Windows types. Any other type is forwarded
# to the backend so it can run or return useful corrective feedback.
VERB_ALIASES = {
    "type": "set_value",
    "input": "set_value",
    "enter_text": "set_value",
    "settext": "set_value",
    "set_text": "set_value",
    "type_text": "type_text",
    "tap": "click",
    "press": "invoke",
    "clear": "clear",
    "clear_field": "clear",
    "erase": "clear",
    "clear_text": "clear",
    "assert": "assert",
    "verify": "assert",
    "check": "assert",
    "confirm": "assert",
}

VALUE_TYPES = {"set_value", "type_text", "clear"}
CLICK_TYPES = {"invoke", "click", "toggle", "select", "expand", "collapse", "focus"}
ASSERT_TYPES = {"assert"}
NO_TREE_TYPES = {"key", "launch", "wait", "done", "scroll"}
EDIT_ROLES = {"edit", "document", "combobox", "spinner", "textbox"}


@dataclass
class PreparedAction:
    action: dict[str, Any]
    retarget: dict[str, Any] | None = None
    local: bool = False
    failure: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return LABEL_NOISE_RE.sub(" ", str(text or "").lower()).strip()


def canonical_type(raw: Mapping[str, Any] | str) -> str:
    if isinstance(raw, Mapping):
        value = str(raw.get("type") or raw.get("action") or "")
    else:
        value = str(raw or "")
    cleaned = value.lower().strip(" _-.*:`'\"")
    return VERB_ALIASES.get(cleaned, cleaned)


def is_windows_id(value: Any) -> bool:
    return bool(WINDOWS_ID_RE.fullmatch(str(value or "").strip()))


def is_editable(node: Mapping[str, Any] | None) -> bool:
    if not node:
        return False
    actions = {str(item) for item in (node.get("actions") or [])}
    if "set_value" in actions:
        return True
    role = str(node.get("role") or "").lower()
    return role in EDIT_ROLES


def focused_id(nodes: Mapping[str, Mapping[str, Any]], meta: Mapping[str, Any] | None) -> str:
    meta = meta or {}
    candidate = str(meta.get("focus_id") or "").strip()
    if candidate in nodes:
        return candidate
    for node_id, node in nodes.items():
        states = {str(item) for item in (node.get("states") or [])}
        if "focused" in states:
            return node_id
    return ""


def needs_tree(action: Mapping[str, Any]) -> bool:
    action_type = canonical_type(action)
    if action_type in ASSERT_TYPES or action_type in VALUE_TYPES:
        return True
    if action_type in NO_TREE_TYPES and not action.get("id"):
        return False
    return bool(
        action.get("id")
        or action.get("name")
        or action.get("label")
        or action.get("query")
        or (action_type in CLICK_TYPES)
    )


def _labels(node: Mapping[str, Any]) -> list[str]:
    values = []
    for key in ("name", "automation_id", "help_text", "value"):
        text = str(node.get(key) or "").strip()
        if text:
            values.append(text)
    return values


def _match_score(query: str, node: Mapping[str, Any]) -> int | None:
    needle = _norm(query)
    if not needle:
        return None
    words = [part for part in needle.split() if part]
    best: int | None = None
    for label in _labels(node):
        hay = _norm(label)
        if not hay:
            continue
        hit = needle in hay
        if not hit and len(hay) >= 3 and len(words) <= 3:
            hit = bool(re.search(rf"\b{re.escape(hay)}\b", needle))
        if not hit:
            continue
        score = len(hay)
        if best is None or score < best:
            best = score
    return best


def match_by_label(
    query: str, nodes: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for node in nodes.values():
        score = _match_score(query, node)
        if score is None:
            continue
        scored.append((score, dict(node)))
    if not scored:
        return None, []
    scored.sort(key=lambda item: (item[0], str(item[1].get("id") or "")))
    tightest = scored[0][0]
    winners = [node for score, node in scored if score == tightest]
    if len(winners) != 1:
        return None, winners
    return winners[0], winners


def requested_label(action: Mapping[str, Any], action_type: str) -> str:
    for key in ("name", "label", "query"):
        text = str(action.get(key) or "").strip()
        if text:
            return text
    if action_type not in VALUE_TYPES:
        text = str(action.get("text") or "").strip()
        if text:
            return text
    return ""


def candidate_list(nodes: Mapping[str, Mapping[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node_id in sorted(nodes):
        node = nodes[node_id]
        rows.append(
            {
                "id": node_id,
                "role": node.get("role"),
                "name": node.get("name"),
                "actions": node.get("actions") or [],
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _editable_nodes(nodes: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(node) for node in nodes.values() if is_editable(node)]


def _pick_editable(
    nodes: Mapping[str, Mapping[str, Any]], meta: Mapping[str, Any] | None
) -> tuple[dict[str, Any] | None, str]:
    focus = nodes.get(focused_id(nodes, meta))
    if is_editable(focus):
        return dict(focus), "focused_editable"
    editables = _editable_nodes(nodes)
    if len(editables) == 1:
        return editables[0], "lone_editable"
    return None, ""


def _pattern_fallback(action: dict[str, Any], node: Mapping[str, Any]) -> str | None:
    available = {str(item) for item in (node.get("actions") or [])}
    action_type = str(action.get("type") or "")
    if action_type == "invoke" and "invoke" not in available and "click" in available:
        action["type"] = "click"
        return "invoke_unavailable_native_click"
    if action_type == "set_value" and "set_value" not in available:
        action["type"] = "type_text"
        if not str(action.get("text") or ""):
            action["text"] = str(action.get("value") or "")
        return "value_pattern_unavailable_type_text"
    return None


def _note(prepared: PreparedAction, reason: str, **extra: Any) -> None:
    payload = {"reason": reason, **extra}
    if prepared.retarget is None:
        prepared.retarget = payload
    else:
        existing = prepared.retarget.setdefault("steps", [])
        if "reason" in prepared.retarget and not existing:
            existing.append({key: value for key, value in prepared.retarget.items() if key != "steps"})
        existing.append(payload)
        prepared.retarget["reason"] = reason
        prepared.retarget.update(extra)
    prepared.notes.append(reason)


def prepare_action(
    raw: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> PreparedAction:
    action = dict(raw)
    action_type = canonical_type(action)
    if action_type:
        action["type"] = action_type
    if action_type == "set_value":
        if not str(action.get("value") if action.get("value") is not None else "").strip():
            text = str(action.get("text") or "")
            if text:
                action["value"] = text
    prepared = PreparedAction(action=action)
    nodes = nodes or {}
    meta = meta or {}

    if action_type in ASSERT_TYPES:
        prepared.local = True
        return prepared

    if action_type == "clear":
        action["type"] = "set_value"
        action.setdefault("value", "")
        action_type = "set_value"
        _note(prepared, "clear_to_set_value")

    requested_id = action.get("id")
    id_text = str(requested_id).strip() if requested_id is not None else ""
    if action_type in VALUE_TYPES and id_text and not is_windows_id(id_text) and id_text not in nodes:
        if not str(action.get("text") or action.get("value") or "").strip():
            action["text"] = id_text
            action["value"] = id_text
            action.pop("id", None)
            id_text = ""
            _note(prepared, "id_slot_was_text")

    node = nodes.get(id_text) if id_text else None
    label = requested_label(action, action_type)

    if action_type in VALUE_TYPES:
        if not (node is not None and is_editable(node)):
            editables = {key: value for key, value in nodes.items() if is_editable(value)}
            if label:
                matched, winners = match_by_label(label, editables)
                if matched is None and winners:
                    prepared.failure = failure(
                        "TARGET_AMBIGUOUS",
                        f"multiple fields match {label!r}; name one id instead of guessing",
                        candidates=[{"id": item.get("id"), "name": item.get("name")} for item in winners],
                    )
                    return prepared
                if matched is not None:
                    action["id"] = matched["id"]
                    node = matched
                    _note(prepared, "label_match", from_id=id_text, to_id=matched["id"], label=label)
                else:
                    if not nodes:
                        return prepared
                    prepared.failure = failure(
                        "ELEMENT_STALE",
                        f"no field matches {label!r}",
                        asked_id=id_text,
                        label=label,
                        candidates=candidate_list(nodes),
                    )
                    return prepared
            else:
                replacement, reason = _pick_editable(nodes, meta)
                if replacement is None:
                    if not nodes:
                        return prepared
                    fields = [item["id"] for item in _editable_nodes(nodes)]
                    prepared.failure = failure(
                        "ELEMENT_STALE",
                        f"element {id_text or '<missing>'} is not a text field"
                        + (
                            f" - the field(s) are {', '.join(fields)}; set_value one of those"
                            if fields
                            else " and there is NO text field on this screen"
                        ),
                        asked_id=id_text,
                        candidates=candidate_list(nodes),
                    )
                    return prepared
                action["id"] = replacement["id"]
                node = replacement
                _note(
                    prepared,
                    "non_field_to_editable" if id_text else reason or "editable_retarget",
                    from_id=id_text,
                    to_id=replacement["id"],
                    via=reason,
                )

    elif (id_text and node is None) or (not id_text and label):
        matched, winners = match_by_label(label, nodes) if label else (None, [])
        if matched is None and winners:
            prepared.failure = failure(
                "TARGET_AMBIGUOUS",
                f"multiple controls match {label!r}; pick one id instead of guessing",
                candidates=[{"id": item.get("id"), "name": item.get("name")} for item in winners],
            )
            return prepared
        if matched is None:
            if not nodes:
                return prepared
            prepared.failure = failure(
                "ELEMENT_STALE",
                f"element is absent or stale: {id_text or label or '<missing>'}",
                asked_id=id_text,
                label=label,
                candidates=candidate_list(nodes),
            )
            return prepared
        action["id"] = matched["id"]
        node = matched
        _note(prepared, "stale_id_label_match", from_id=id_text, to_id=matched["id"], label=label)

    if node is not None:
        fallback = _pattern_fallback(action, node)
        if fallback:
            _note(prepared, fallback, to_id=node.get("id"))
        if "value" in action and action["type"] == "type_text" and not action.get("text"):
            action["text"] = str(action.get("value") or "")
    return prepared


def _node_text(node: Mapping[str, Any] | None) -> str:
    if not node:
        return ""
    return str(node.get("value") or node.get("name") or "").strip()


def _visible_text(nodes: Mapping[str, Mapping[str, Any]]) -> str:
    parts = []
    for node in nodes.values():
        parts.extend(_labels(node))
        parts.extend(str(item) for item in (node.get("states") or []))
    return " ".join(parts).lower()


def _state_matches(node: Mapping[str, Any] | None, state: str) -> bool | None:
    if node is None:
        return None
    states = {str(item).lower() for item in (node.get("states") or [])}
    needle = state.lower()
    if needle.startswith("check") or needle in {"on", "toggled"}:
        return "checked" in states or "on" in states
    if needle.startswith("enab") or needle == "ready":
        return "enabled" in states
    if needle.startswith("disab") or needle.startswith("grey") or needle.startswith("gray"):
        return "disabled" in states or "enabled" not in states
    if needle.startswith("select"):
        return "selected" in states
    if needle.startswith("focus"):
        return "focused" in states
    return needle in states


def verify_expectation(
    expect: str,
    nodes: Mapping[str, Mapping[str, Any]],
    meta: Mapping[str, Any] | None = None,
) -> str | None:
    """High-confidence checks only. A wrong ✓ is worse than leaving this unchecked."""
    text = str(expect or "").strip()
    if not text:
        return None
    lowered = text.lower()
    focus = nodes.get(focused_id(nodes, meta))
    editables = _editable_nodes(nodes)
    field = focus if is_editable(focus) else (editables[0] if len(editables) == 1 else None)
    if (
        any(token in lowered for token in ("text", "typed", "message", "prompt", "value"))
        and any(token in lowered for token in ("field", "box", "input", "typed", "entered", "landed"))
    ):
        if field is None:
            return None
        return "✓ text IS in the field now" if _node_text(field) else "✗ the field looks EMPTY - the text may not have landed"
    if "send" in lowered or "submit" in lowered:
        visible = _visible_text(nodes)
        present = "send" in visible or "submit" in visible
        return "✓ a Send control IS on screen" if present else "✗ no Send control is visible yet"
    return None


def verify_after(
    action: Mapping[str, Any],
    *,
    before_nodes: Mapping[str, Mapping[str, Any]],
    after_nodes: Mapping[str, Mapping[str, Any]],
    observation: Mapping[str, Any] | None,
    expect: Any = None,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Post-action evidence. Never treat a backend ok boolean as confirmation."""
    action_type = canonical_type(action)
    node_id = str(action.get("id") or "").strip()
    after = after_nodes.get(node_id)
    observation = observation or {}
    added = list(observation.get("added") or [])
    updated = list(observation.get("updated") or [])
    removed = list(observation.get("removed") or [])
    changed = bool(added or updated or removed or observation.get("meta_changed"))
    if not changed and before_nodes and after_nodes:
        changed = dict(before_nodes) != dict(after_nodes)
    checked: list[str] = []
    status = "unchecked"
    message = "no high-confidence check for this action; the observation is the evidence"

    if action_type in VALUE_TYPES:
        expected = str(action.get("value") if action.get("value") is not None else action.get("text") or "")
        actual = _node_text(after)
        checked.append("value_landed")
        if after is None:
            status = "unchecked"
            message = "field left the tree; cannot confirm the value landed"
        elif expected == "":
            status = "confirmed" if actual == "" else "contradicted"
            message = "✓ field is empty" if status == "confirmed" else f"✗ field still holds {actual!r}"
        elif expected.lower() in actual.lower():
            status = "confirmed"
            message = "✓ text IS in the field now"
        else:
            status = "contradicted"
            message = f"✗ the field does not contain {expected!r} (has {actual!r})"
    elif action_type in CLICK_TYPES:
        checked.append("tree_delta")
        if changed:
            status = "changed"
            message = "screen changed after the action; confirm the intended control against the delta"
        else:
            status = "contradicted"
            message = "✗ the screen looks UNCHANGED since the action - it may not have registered"

    expect_text = ""
    if isinstance(expect, Mapping):
        expect_text = str(expect.get("that") or expect.get("text") or expect.get("expect") or "").strip()
        expect_id = str(expect.get("id") or "").strip()
        expect_state = str(expect.get("state") or "").strip()
        if expect_id and expect_state:
            actual = _state_matches(after_nodes.get(expect_id), expect_state)
            checked.append("expected_state")
            structured_status = "unchecked"
            structured_message = f"can't check {expect_state!r} on {expect_id or 'missing id'}"
            if actual is True:
                structured_status = "confirmed"
                structured_message = f"✓ element {expect_id} IS {expect_state}"
            elif actual is False:
                structured_status = "contradicted"
                structured_message = f"✗ element {expect_id} is NOT {expect_state} - adapt, don't assume"
            if status == "contradicted":
                pass
            elif status == "unchecked":
                status = structured_status
                message = structured_message
            elif structured_status == "contradicted":
                status = "contradicted"
                message = structured_message
    else:
        expect_text = str(expect or "").strip()

    if expect_text:
        structural = verify_expectation(expect_text, after_nodes, meta)
        checked.append("expect")
        expect_status = "unchecked"
        expect_message = ""
        if structural is None:
            visible = _visible_text(after_nodes)
            keys = WORD_RE.findall(expect_text.lower())
            if keys and sum(1 for key in keys if key in visible) * 2 >= len(keys):
                expect_status = "confirmed"
                expect_message = f'✓ looks true - "{expect_text[:80]}" appears on screen'
            else:
                expect_status = "contradicted"
                expect_message = f'✗ can\'t confirm "{expect_text[:80]}" - it does NOT appear here; adapt, don\'t assume it worked'
        elif structural.startswith("✓"):
            expect_status = "confirmed"
            expect_message = structural
        else:
            expect_status = "contradicted"
            expect_message = structural
        if status == "contradicted":
            pass
        elif status == "unchecked":
            status = expect_status
            message = expect_message
        elif expect_status == "contradicted":
            status = "contradicted"
            message = expect_message

    return {
        "kind": "verification",
        "status": status,
        "message": message,
        "checked": checked,
        "changed": changed,
        "ok": status in {"confirmed", "changed"},
    }


def run_assert(
    action: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    node_id = str(action.get("id") or "").strip()
    state = str(action.get("state") or "").strip()
    that = str(action.get("that") or action.get("text") or action.get("expect") or "").strip()
    if node_id and state:
        actual = _state_matches(nodes.get(node_id), state)
        if actual is True:
            message = f"✓ element {node_id} IS {state}"
            status = "confirmed"
        elif actual is False:
            message = f"✗ element {node_id} is NOT {state} - adapt, don't assume"
            status = "contradicted"
        else:
            message = f"can't check that (no element {node_id}, or unknown state - try checked/enabled/disabled/selected)"
            status = "unchecked"
        verification = {
            "kind": "verification",
            "status": status,
            "message": message,
            "checked": ["element_state"],
            "ok": status == "confirmed",
        }
        if status != "confirmed":
            result = failure(
                "ASSERT_CONTRADICTED" if status == "contradicted" else "ASSERT_UNCHECKED",
                message,
            )
            result["verification"] = verification
            return result
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "action": "assert",
            "message": message,
            "verification": verification,
        }
    if not that:
        return failure("ASSERT_INCOMPLETE", 'assert needs "that":"what you expect" (or "id"+"state")')
    verification = verify_after(
        {"type": "assert"},
        before_nodes=nodes,
        after_nodes=nodes,
        observation={"added": [], "updated": [], "removed": []},
        expect=that,
        meta=meta,
    )
    if verification.get("status") != "confirmed":
        result = failure(
            "ASSERT_CONTRADICTED" if verification.get("status") == "contradicted" else "ASSERT_UNCHECKED",
            str(verification.get("message") or ""),
        )
        result["verification"] = verification
        return result
    return {
        "ok": True,
        "protocol": PROTOCOL_VERSION,
        "kind": "action_outcome",
        "action": "assert",
        "message": verification["message"],
        "verification": verification,
    }
