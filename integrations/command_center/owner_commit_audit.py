"""Owner-commitment classification with never-invent-consent semantics.

Every future meeting/call/demo/interview/customer commitment/RSVP where Bryce
(the owner) is personally expected classifies into exactly one of:

  - OWNER_APPROVED
  - PROPOSED_NOT_CONFIRMED
  - EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL
  - NEEDS_OWNER_ACTION

The state machine is fail-closed: an externally confirmed item with no owner
approval evidence classifies EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL (it is
never defaulted to approved), ambiguous or conflicting evidence collapses to
NEEDS_OWNER_ACTION, and approval evidence bound to the wrong commitment or a
stale event time approves nothing.

Stdlib only, matching the rest of integrations/command_center.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

OWNER_APPROVED = "OWNER_APPROVED"
PROPOSED_NOT_CONFIRMED = "PROPOSED_NOT_CONFIRMED"
EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL = "EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL"
NEEDS_OWNER_ACTION = "NEEDS_OWNER_ACTION"

ALL_STATES = (
    OWNER_APPROVED,
    PROPOSED_NOT_CONFIRMED,
    EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL,
    NEEDS_OWNER_ACTION,
)

# Commitment kinds where the owner is personally expected.
OWNER_PRESENT_KINDS = frozenset({
    "meeting",
    "call",
    "demo",
    "interview",
    "customer_commitment",
    "rsvp",
})

# Identities whose approval counts as the owner's explicit approval. Approval
# claimed by any other identity (a seat, an agent, a relay, "he said yes")
# is not owner approval and approves nothing.
DEFAULT_OWNER_IDENTITIES = frozenset({"bryce"})


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovalEvidence:
    """A single claim that the owner approved a commitment.

    source:      identity that gave the approval (must be an owner identity).
    at:          ISO timestamp of the approval.
    commitment_id: the commitment this approval binds to.
    event_time:  the event time the approval covered (None = time-agnostic).
    text:        exact wording of the approval, for the audit trail.
    """
    source: str
    at: str
    commitment_id: str
    event_time: Optional[str] = None
    text: str = ""


@dataclass(frozen=True)
class ExternalConfirmation:
    """A signal that someone other than the owner treated the commitment as set.

    kind: one of "counterpart_confirmed", "seat_confirmed_to_external",
          "calendar_hold_with_external", "invite_sent_external".
    detail: human-readable detail for the audit trail.
    """
    kind: str
    detail: str = ""


@dataclass(frozen=True)
class Proposal:
    """A proposal that was made but never confirmed by any party."""
    detail: str = ""


@dataclass
class Commitment:
    """One future commitment where the owner is personally expected."""
    commitment_id: str
    kind: str
    summary: str = ""
    counterpart: str = ""
    event_time: Optional[str] = None
    approval_evidence: List[ApprovalEvidence] = field(default_factory=list)
    external_confirmation: List[ExternalConfirmation] = field(default_factory=list)
    proposals: List[Proposal] = field(default_factory=list)
    # Free-form notes of unclear or conflicting signals. Non-empty means the
    # evidence is ambiguous and must fail closed (never resolved by guessing).
    ambiguity: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Classification:
    """Exactly one state plus the audit trail that produced it."""
    state: str
    commitment_id: str
    reasons: Tuple[str, ...]
    approving_evidence: Optional[ApprovalEvidence] = None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _is_owner(identity: str, owner_identities) -> bool:
    return str(identity or "").strip().lower() in owner_identities


def _event_time_matches(ev: ApprovalEvidence, commitment: Commitment) -> bool:
    """Approval for a moved event does not survive the move.

    If both the approval and the commitment carry an event time and they
    differ, the approval is stale evidence and approves nothing.
    """
    if ev.event_time and commitment.event_time:
        return ev.event_time == commitment.event_time
    return True


def _binding_approval(commitment: Commitment, owner_identities) -> Optional[ApprovalEvidence]:
    """Return the first approval that actually binds this commitment, or None.

    Never invent consent: the approval must come from an owner identity, must
    name this commitment, and must cover the current event time. Anything else
    (agent-claimed approval, wrong commitment id, stale time) is discarded.
    """
    for ev in commitment.approval_evidence:
        if not _is_owner(ev.source, owner_identities):
            continue  # not the owner: an agent saying "he approved" is nothing
        if ev.commitment_id != commitment.commitment_id:
            continue  # wrong deal: approval for another commitment approves nothing
        if not _event_time_matches(ev, commitment):
            continue  # stale: the meeting moved after the approval
        return ev
    return None


def classify(commitment: Commitment,
             owner_identities=DEFAULT_OWNER_IDENTITIES) -> Classification:
    """Classify a commitment into exactly one of the four states.

    Check order is fail-closed:
      1. Any ambiguity/conflict -> NEEDS_OWNER_ACTION (never guessed away,
         and it outranks even a binding-looking approval: a contested
         approval is not an approval).
      2. A binding owner approval -> OWNER_APPROVED.
      3. External confirmation without owner approval ->
         EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL (never defaulted to approved).
      4. Proposal only -> PROPOSED_NOT_CONFIRMED.
      5. Otherwise -> NEEDS_OWNER_ACTION.
    """
    if commitment.kind not in OWNER_PRESENT_KINDS:
        raise ValueError("kind must be one of %s, got %r"
                         % (sorted(OWNER_PRESENT_KINDS), commitment.kind))

    if commitment.ambiguity:
        return Classification(
            state=NEEDS_OWNER_ACTION,
            commitment_id=commitment.commitment_id,
            reasons=("ambiguous evidence fails closed: %s"
                     % "; ".join(commitment.ambiguity),),
        )

    binding = _binding_approval(commitment, owner_identities)
    if binding is not None:
        return Classification(
            state=OWNER_APPROVED,
            commitment_id=commitment.commitment_id,
            reasons=("explicit owner approval from %s at %s binds this commitment"
                     % (binding.source, binding.at),),
            approving_evidence=binding,
        )

    if commitment.external_confirmation:
        kinds = sorted({c.kind for c in commitment.external_confirmation})
        return Classification(
            state=EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL,
            commitment_id=commitment.commitment_id,
            reasons=("externally confirmed (%s) with no owner approval evidence; "
                     "not defaulted to approved" % ", ".join(kinds),),
        )

    if commitment.proposals:
        return Classification(
            state=PROPOSED_NOT_CONFIRMED,
            commitment_id=commitment.commitment_id,
            reasons=("proposed but not confirmed by any party: %s"
                     % "; ".join(p.detail for p in commitment.proposals),),
        )

    return Classification(
        state=NEEDS_OWNER_ACTION,
        commitment_id=commitment.commitment_id,
        reasons=("no approval, no external confirmation, no proposal: "
                 "owner decision required",),
    )


def audit(commitments, owner_identities=DEFAULT_OWNER_IDENTITIES):
    """Classify every commitment; returns (classifications, by_state)."""
    results = [classify(c, owner_identities) for c in commitments]
    by_state = {s: [] for s in ALL_STATES}
    for c, r in zip(commitments, results):
        by_state[r.state].append((c, r))
    return results, by_state


# ---------------------------------------------------------------------------
# Owner decision packet
# ---------------------------------------------------------------------------

def owner_decision_for(commitment: Commitment, classification: Classification) -> str:
    """One exact owner decision per item, worded as approve/deny.

    Only generated for states that need the owner to decide; returns "" for
    OWNER_APPROVED (nothing to decide).
    """
    state = classification.state
    if state == OWNER_APPROVED:
        return ""
    kind = commitment.kind.replace("_", " ")
    when = commitment.event_time or "time TBD"
    who = (" with %s" % commitment.counterpart) if commitment.counterpart else ""
    label = commitment.summary or commitment.commitment_id
    if state == EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL:
        return ("APPROVE or CANCEL: %s%s scheduled %s (%s) was confirmed "
                "without your approval. Approve to keep it, or cancel it."
                % (kind, who, when, label))
    if state == PROPOSED_NOT_CONFIRMED:
        return ("APPROVE or DECLINE: proposed %s%s at %s (%s) is awaiting "
                "confirmation. Approve to let it be confirmed, or decline it."
                % (kind, who, when, label))
    return ("DECIDE: %s%s at %s (%s) needs your action. State why before "
            "anything is confirmed."
            % (kind, who, when, label))


# ---------------------------------------------------------------------------
# Consent-signal helpers (for reconstructing the real failure mode)
# ---------------------------------------------------------------------------

# Phrases agents used as if they were consent; none of them are approval.
_MISTAKEN_CONSENT_RE = re.compile(
    r"\b(?:he'?s\s+good|he\s+said\s+yes|assumed|probably\s+fine|no\s+objection|"
    r"didn'?t\s+object|silence|read\s+receipt|thumbs?[\s-]?up|ok\s+from\s+context|"
    r"bryce\s+(?:is\s+(?:good|fine)|said\s+yes|approved\s+it))\b",
    re.IGNORECASE,
)

# Direct owner utterance ("Bryce: approved ...") is not a relay claim.
_DIRECT_OWNER_RE = re.compile(r"^\s*bryce\s*:", re.IGNORECASE)


def looks_like_mistaken_consent(text: str) -> bool:
    """True if the text resembles a signal an agent might mistake for consent.

    Third-party claims about the owner ("Bryce is good with it", "he said
    yes") flag True; direct owner utterances do not. Used by audits to flag,
    never to approve: a True here must never feed approval evidence.
    """
    t = (text or "").strip()
    if _DIRECT_OWNER_RE.match(t):
        return False
    return bool(_MISTAKEN_CONSENT_RE.search(t))
