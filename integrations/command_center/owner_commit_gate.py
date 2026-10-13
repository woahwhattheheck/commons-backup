"""Owner-calendar-commit gate (WO-1: owner-commitment safety patch).

Hard owner-attendance state machine for any path that would bind the owner's
(Bryce's) personal time:

    PROPOSED -> OWNER_APPROVED -> EXTERNALLY_CONFIRMED

Enforced rules (implemented as code, not comments):
  - Agents MAY: discover leads, negotiate, propose times, check free/busy,
    draft invites, prepare a meeting.
  - Agents MUST NOT, until explicit OWNER_APPROVED evidence exists: represent
    Bryce as attending, confirm a time, send an invite that commits Bryce,
    accept an invite for Bryce, or otherwise bind Bryce's personal time.
  - Calendar availability is NOT consent. Silence / no response is NOT
    consent. Prior general autonomy directives are NOT consent to a specific
    owner-attended meeting.
  - Reschedule / cancel / RSVP changes affecting Bryce require explicit owner
    approval, unless Bryce directly requested that exact action.
  - Approval evidence is persisted (source + timestamp + exact meeting/deal
    identity) so a later agent cannot infer approval from context.
  - Fail closed on missing / ambiguous approval.

INTEGRATION POINT (documented, no live path invented): as of WO-1 there is no
live calendar send/confirm path in integrations/command_center/ (its tools API
dispatches only existing gateway schemas; no calendar tool exists), so the gate
hooks into the canonical path by convention: ANY future outbound
invite/confirm/accept/reschedule/cancel path that can bind the owner's time
MUST call `OwnerCommitGate.require_owner_commit(meeting_id, action)` (or use
the `guard_owner_commit` decorator) before performing the external send.
The gate raises OwnerCommitDenied when the invariant is not met.
"""

from __future__ import annotations

import functools
import json
import os
import time
import uuid
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# States and action classes
# ---------------------------------------------------------------------------

PROPOSED = "PROPOSED"
OWNER_APPROVED = "OWNER_APPROVED"
EXTERNALLY_CONFIRMED = "EXTERNALLY_CONFIRMED"
CANCELLED = "CANCELLED"

TERMINAL_STATES = frozenset({EXTERNALLY_CONFIRMED, CANCELLED})

#: What agents are free to do without owner approval.
PREPARATION_ACTIONS = frozenset({
    "discover_leads",
    "negotiate",
    "propose_times",
    "check_freebusy",
    "draft_invite",
    "prepare_meeting",
})

#: Actions that bind the owner's personal time. ALL require explicit,
#: evidence-backed OWNER_APPROVED state (or an owner direct request for
#: reschedule/cancel/rsvp changes).
BINDING_ACTIONS = frozenset({
    "represent_attending",
    "confirm_time",
    "send_invite",
    "accept_invite",
    "reschedule",
    "cancel",
    "rsvp_change",
})

#: Reschedule/cancel/RSVP changes need FRESH approval even on an already
#: confirmed meeting: an old approval never covers a new time or a new decision.
RE_APPROVAL_ACTIONS = frozenset({"reschedule", "cancel", "rsvp_change"})

#: Signals that can NEVER constitute owner consent. Enforced by
#: consent_from_signal() and by approval validation below.
NON_CONSENT_SIGNALS = frozenset({
    "calendar_free",
    "freebusy_open",
    "silence",
    "no_response",
    "prior_general_autonomy",
    "general_directive",
    "inferred_context",
    "assumed",
})


class OwnerCommitDenied(Exception):
    """Raised when an attempt to bind the owner's time lacks valid approval."""


class AmbiguousApprovalError(OwnerCommitDenied):
    """Raised when purported approval evidence is missing or ambiguous."""


def consent_from_signal(signal):
    """Return True only if the signal is explicit owner approval evidence.

    Fail-closed by construction: every non-explicit signal returns False, so no
    code path can treat availability, silence, or prior general autonomy as
    consent to a specific owner-attended meeting.
    """
    return False


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeetingIdentity:
    """Exact identity of a proposed meeting.

    An owner approval is bound to ALL of these fields: a new time, a different
    deal, or a different meeting id never inherits an old approval.
    """
    meeting_id: str
    deal_id: str
    starts_at: str   # ISO 8601, e.g. "2026-09-22T10:00:00-04:00"
    ends_at: str     # ISO 8601


@dataclass(frozen=True)
class OwnerApproval:
    """Persisted evidence of explicit owner approval.

    `source` names the exact channel the approval came through, e.g.
    "owner_chat_msg:<msg_id>", "owner_slack_ts:<ts>", "owner_direct_request".
    Never a NON_CONSENT_SIGNAL and never inferred.
    """
    meeting_id: str
    deal_id: str
    starts_at: str
    ends_at: str
    source: str
    approved_at: str      # ISO 8601 timestamp of the owner's approval
    explicit: bool = True


@dataclass(frozen=True)
class OwnerDirectRequest:
    """Evidence that Bryce directly requested an exact action.

    The only bypass for reschedule/cancel/rsvp-change re-approval: the owner
    himself ordered THAT exact action. Never inferable from context.
    """
    action: str
    meeting_id: str
    source: str          # e.g. "owner_chat_msg:<msg_id>"
    requested_at: str    # ISO 8601


def _approval_key(approval):
    return (approval.meeting_id, approval.deal_id,
            approval.starts_at, approval.ends_at)


def _identity_key(identity):
    return (identity.meeting_id, identity.deal_id,
            identity.starts_at, identity.ends_at)


def _validate_identity(identity):
    for field in ("meeting_id", "deal_id", "starts_at", "ends_at"):
        value = getattr(identity, field)
        if not isinstance(value, str) or not value.strip():
            raise AmbiguousApprovalError(
                "Meeting identity field %r is missing or empty." % field)
    return identity


def _validate_approval(approval):
    """Fail closed: approval evidence must be complete, explicit, and exact."""
    if not isinstance(approval, OwnerApproval):
        raise AmbiguousApprovalError("Approval must be an OwnerApproval record.")
    _validate_identity(approval)
    if approval.explicit is not True:
        raise AmbiguousApprovalError(
            "Approval is not marked explicit: refuse to infer consent.")
    if not isinstance(approval.source, str) or not approval.source.strip():
        raise AmbiguousApprovalError("Approval source is missing.")
    if approval.source.strip().lower() in NON_CONSENT_SIGNALS:
        raise AmbiguousApprovalError(
            "Approval source %r is not a consent signal." % approval.source)
    if not isinstance(approval.approved_at, str) or not approval.approved_at.strip():
        raise AmbiguousApprovalError("Approval timestamp is missing.")
    return approval


# ---------------------------------------------------------------------------
# Evidence store (persisted so approval cannot be inferred from context)
# ---------------------------------------------------------------------------

class CommitEvidenceStore:
    """Durable JSON store of meetings + approval evidence.

    A later agent re-instantiating the gate from the same path sees exactly
    the persisted evidence — nothing inferred from chat context.
    """

    def __init__(self, path):
        self.path = path

    def save(self, meetings, approvals):
        payload = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "meetings": meetings,
            "approvals": [self._approval_to_dict(a) for a in approvals],
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        if not os.path.exists(self.path):
            return {}, []
        with open(self.path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        approvals = [self._approval_from_dict(d)
                     for d in payload.get("approvals", [])]
        return payload.get("meetings", {}), approvals

    @staticmethod
    def _approval_to_dict(approval):
        return {
            "meeting_id": approval.meeting_id,
            "deal_id": approval.deal_id,
            "starts_at": approval.starts_at,
            "ends_at": approval.ends_at,
            "source": approval.source,
            "approved_at": approval.approved_at,
            "explicit": approval.explicit,
        }

    @staticmethod
    def _approval_from_dict(data):
        return OwnerApproval(
            meeting_id=data["meeting_id"],
            deal_id=data["deal_id"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            source=data["source"],
            approved_at=data["approved_at"],
            explicit=data.get("explicit", True),
        )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class OwnerCommitGate:
    """Enforces PROPOSED -> OWNER_APPROVED -> EXTERNALLY_CONFIRMED."""

    def __init__(self, store_path=None):
        self._meetings = {}    # meeting_id -> dict(state, identity, history)
        self._approvals = {}   # (meeting_id, deal_id, starts_at, ends_at) -> OwnerApproval
        self._consumed = set() # approval keys already consumed by a reschedule/cancel/rsvp
        self._store = CommitEvidenceStore(store_path) if store_path else None
        if self._store is not None:
            meetings, approvals = self._store.load()
            for mid, record in meetings.items():
                self._meetings[mid] = record
            for approval in approvals:
                try:
                    _validate_approval(approval)
                except AmbiguousApprovalError:
                    continue  # never persist ambiguous evidence forward
                self._approvals[_approval_key(approval)] = approval

    # -- persistence -------------------------------------------------------
    def _persist(self):
        if self._store is not None:
            self._store.save(self._meetings, list(self._approvals.values()))

    # -- preparation (always allowed) --------------------------------------
    def prepare(self, action):
        """Preparation never binds the owner's time."""
        return {"allowed": True, "action": action, "gate": "preparation"}

    def propose(self, identity, proposed_by=None):
        """Record a proposed owner-attended meeting. Always allowed.

        Binding the owner's time still requires explicit owner approval first.
        """
        _validate_identity(identity)
        record = {
            "state": PROPOSED,
            "identity": {
                "meeting_id": identity.meeting_id,
                "deal_id": identity.deal_id,
                "starts_at": identity.starts_at,
                "ends_at": identity.ends_at,
            },
            "proposed_by": proposed_by,
            "history": [{"event": "proposed", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())}],
        }
        self._meetings[identity.meeting_id] = record
        self._persist()
        return {"meeting_id": identity.meeting_id, "state": PROPOSED}

    # -- approval -----------------------------------------------------------
    def record_owner_approval(self, approval):
        """OWNER_APPROVED: bind explicit owner approval evidence to the exact meeting identity.

        Fails closed on missing/ambiguous evidence, or when the approval's
        identity does not match the currently proposed meeting identity
        (wrong deal, wrong meeting, wrong time are all rejected).
        """
        _validate_approval(approval)
        meeting = self._meetings.get(approval.meeting_id)
        if meeting is None:
            raise OwnerCommitDenied(
                "No proposed meeting %r: cannot approve what was never proposed."
                % (approval.meeting_id,))
        current = meeting["identity"]
        if (current["deal_id"] != approval.deal_id
                or current["starts_at"] != approval.starts_at
                or current["ends_at"] != approval.ends_at):
            raise OwnerCommitDenied(
                "Approval identity does not match the proposed meeting "
                "(deal/time mismatch): refusing to bind.")
        if meeting["state"] in TERMINAL_STATES:
            raise OwnerCommitDenied(
                "Meeting %r is already %s." % (approval.meeting_id, meeting["state"]))
        self._approvals[_approval_key(approval)] = approval
        meeting["state"] = OWNER_APPROVED
        meeting["history"].append({
            "event": "owner_approved",
            "at": approval.approved_at,
            "source": approval.source,
        })
        self._persist()
        return {"meeting_id": approval.meeting_id, "state": OWNER_APPROVED}

    # -- binding actions (the gate) -----------------------------------------
    def require_owner_commit(self, meeting_id, action, owner_direct_request=None):
        """Enforced hook. Call BEFORE any action that binds the owner's time.

        Raises OwnerCommitDenied when a BINDING action lacks persisted owner
        commit evidence:
          - the meeting is in OWNER_APPROVED (or EXTERNALLY_CONFIRMED for
            non-re-approval actions) with approval evidence matching the exact
            current meeting identity, or
          - for reschedule/cancel/rsvp_change: a valid OwnerDirectRequest shows
            Bryce himself ordered that exact action.
        Operations that do not bind the owner's time are not calendar commits.
        """
        if action in BINDING_ACTIONS:
            meeting = self._meetings.get(meeting_id)
            if meeting is None:
                raise OwnerCommitDenied(
                    "Meeting %r was never proposed: no owner commitment allowed." % (meeting_id,))
            state = meeting["state"]
            identity = meeting["identity"]

            if action in RE_APPROVAL_ACTIONS:
                if owner_direct_request is not None and self._validate_direct_request(
                        owner_direct_request, meeting_id, action):
                    return {"allowed": True, "action": action,
                            "meeting_id": meeting_id, "via": "owner_direct_request"}
                raise OwnerCommitDenied(
                    "Action %r on meeting %r requires fresh explicit owner approval "
                    "(or an owner direct request for this exact action)."
                    % (action, meeting_id))

            if state == PROPOSED:
                raise OwnerCommitDenied(
                    "Meeting %r is PROPOSED but not owner-approved: cannot %s."
                    % (meeting_id, action))
            if state not in (OWNER_APPROVED, EXTERNALLY_CONFIRMED):
                raise OwnerCommitDenied(
                    "Meeting %r is in state %s: cannot %s." % (meeting_id, state, action))

            key = (identity["meeting_id"], identity["deal_id"],
                   identity["starts_at"], identity["ends_at"])
            if key not in self._approvals:
                raise OwnerCommitDenied(
                    "No persisted explicit owner approval for the exact identity of "
                    "meeting %r: refusing to bind." % (meeting_id,))
            return {"allowed": True, "action": action, "meeting_id": meeting_id,
                    "state": state, "approval_source": self._approvals[key].source}
        return {"allowed": True, "action": action, "meeting_id": meeting_id,
                "kind": "not_binding"}

    def _validate_direct_request(self, request, meeting_id, action):
        if not isinstance(request, OwnerDirectRequest):
            raise AmbiguousApprovalError(
                "Owner direct request must be an OwnerDirectRequest record.")
        if request.action != action or request.meeting_id != meeting_id:
            raise OwnerCommitDenied(
                "Owner direct request does not match this exact action/meeting.")
        if not request.source or not request.source.strip():
            raise AmbiguousApprovalError("Owner direct request source missing.")
        if not request.requested_at or not request.requested_at.strip():
            raise AmbiguousApprovalError("Owner direct request timestamp missing.")
        return True

    # -- external confirmation ----------------------------------------------
    def external_confirm(self, meeting_id):
        """EXTERNALLY_CONFIRMED: mark the approved meeting confirmed externally.

        Itself a binding action; requires OWNER_APPROVED evidence.
        """
        self.require_owner_commit(meeting_id, "confirm_time")
        meeting = self._meetings[meeting_id]
        meeting["state"] = EXTERNALLY_CONFIRMED
        meeting["history"].append({
            "event": "externally_confirmed",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        })
        self._persist()
        return {"meeting_id": meeting_id, "state": EXTERNALLY_CONFIRMED}

    def reschedule(self, meeting_id, new_identity, approval=None,
                   owner_direct_request=None):
        """Move a meeting to a new time.

        The old approval does NOT carry over: the new identity needs fresh
        explicit owner approval (or an owner direct request for this exact
        reschedule). Until then the meeting returns to PROPOSED.
        """
        _validate_identity(new_identity)
        if new_identity.meeting_id != meeting_id:
            raise OwnerCommitDenied("Reschedule cannot change the meeting id.")
        meeting = self._meetings.get(meeting_id)
        if meeting is None:
            raise OwnerCommitDenied("Meeting %r was never proposed." % (meeting_id,))
        if meeting["state"] in (PROPOSED,):
            # Never approved at all: still need the owner before any binding,
            # but re-proposing the time itself is allowed.
            pass
        else:
            self.require_owner_commit(meeting_id, "reschedule",
                                      owner_direct_request=owner_direct_request)
        self.propose(new_identity, proposed_by=meeting.get("proposed_by"))
        if approval is not None:
            self.record_owner_approval(approval)
        return {"meeting_id": meeting_id, "state": self._meetings[meeting_id]["state"]}

    def cancel(self, meeting_id, owner_direct_request=None):
        """Cancel an owner-attended meeting.

        Requires fresh explicit owner approval or an owner direct request for
        this exact cancellation.
        """
        self.require_owner_commit(meeting_id, "cancel",
                                  owner_direct_request=owner_direct_request)
        meeting = self._meetings[meeting_id]
        meeting["state"] = CANCELLED
        meeting["history"].append({
            "event": "cancelled",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        })
        self._persist()
        return {"meeting_id": meeting_id, "state": CANCELLED}

    # -- introspection -------------------------------------------------------
    def state(self, meeting_id):
        meeting = self._meetings.get(meeting_id)
        return meeting["state"] if meeting else None

    def approval_evidence(self, meeting_id):
        """Return the persisted approval evidence for a meeting, or None.

        Evidence lookup is by exact identity match only: nothing is inferred.
        """
        meeting = self._meetings.get(meeting_id)
        if meeting is None:
            return None
        identity = meeting["identity"]
        key = (identity["meeting_id"], identity["deal_id"],
               identity["starts_at"], identity["ends_at"])
        return self._approvals.get(key)


def guard_owner_commit(action, meeting_id_arg="meeting_id", gate=None):
    """Decorator: enforce the owner-commit gate on a future send/confirm function.

    Usage (documented integration point for a live calendar/invite path)::

        gate = OwnerCommitGate(store_path="...")

        @guard_owner_commit("send_invite", gate=gate)
        def send_invite(meeting_id, ...):
            ...

    The wrapped function runs only if require_owner_commit() allows the action.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound_gate = kwargs.pop("gate", gate)
            if bound_gate is None:
                raise OwnerCommitDenied(
                    "No OwnerCommitGate supplied: cannot verify owner consent.")
            bound = kwargs.get(meeting_id_arg)
            if bound is None and args:
                bound = args[0]
            bound_gate.require_owner_commit(bound, action)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


__all__ = [
    "PROPOSED", "OWNER_APPROVED", "EXTERNALLY_CONFIRMED", "CANCELLED",
    "PREPARATION_ACTIONS", "BINDING_ACTIONS", "RE_APPROVAL_ACTIONS",
    "NON_CONSENT_SIGNALS",
    "OwnerCommitDenied", "AmbiguousApprovalError",
    "MeetingIdentity", "OwnerApproval", "OwnerDirectRequest",
    "CommitEvidenceStore", "OwnerCommitGate",
    "consent_from_signal", "guard_owner_commit",
]
