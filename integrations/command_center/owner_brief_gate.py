"""Owner-meeting-brief gate (WO-2 of the owner-commitment safety patch).

SYSTEM INVARIANT: before ANY externally confirmed meeting Bryce is expected
to attend, a concise owner brief must exist AND be delivered with enough lead
time for Bryce to actually read it. A brief generated after the meeting
starts does NOT satisfy the gate.

NO-LIVE-SEND INVARIANT: this module MUST NOT perform any network I/O and
MUST NOT contact any person. The urgent-notification path is CODE plus
delivery-record evidence ONLY: obligations are recorded through injected,
record-only NotificationSurface implementations. Nothing here sends a Slack
message, an email, or any other notification.

COMPOSITION WITH WO-1: WO-1 (owner commit gate) owns the commit state
machine -- a meeting must be OWNER_APPROVED before it can be
EXTERNALLY_CONFIRMED. This module does NOT duplicate that state machine. It
consumes only the externally-confirmed signal through the OwnerCommitGate
protocol below. If WO-1's module is present, adapt it to the protocol and
inject it; otherwise the meeting's own status label is used as the signal.
When an adapter is injected, ITS externally-confirmed signal wins over the
local status label, because WO-1 owns the state machine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol


# ---------------------------------------------------------------------------
# Canonical labels (shared vocabulary; NOT a state machine -- WO-1 owns that)
# ---------------------------------------------------------------------------

STATUS_PROPOSED = "PROPOSED"
STATUS_OWNER_APPROVED = "OWNER_APPROVED"
STATUS_EXTERNALLY_CONFIRMED = "EXTERNALLY_CONFIRMED"
STATUS_CANCELLED = "CANCELLED"

VERDICT_PASS = "PASS"                      # gate satisfied; meeting may proceed
VERDICT_STOP = "STOP"                      # gate blocks; do not proceed as confirmed
VERDICT_NOT_APPLICABLE = "NOT_APPLICABLE"  # gate does not apply to this meeting

URGENCY_ROUTINE = "routine"
URGENCY_URGENT = "urgent"

DEFAULT_MIN_LEAD_SECONDS = 30 * 60            # brief delivered >= 30 min before start
DEFAULT_URGENT_VALUE_USD = 10_000.0           # deal value at/above this is urgent
DEFAULT_URGENT_WINDOW_SECONDS = 4 * 60 * 60   # meeting within 4 h is urgent


# ---------------------------------------------------------------------------
# Domain records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Meeting:
    """A meeting Bryce may be expected to attend."""

    meeting_id: str          # stable key for the meeting
    deal_id: str             # stable key for the deal/opportunity
    title: str
    counterparty_name: str
    organization: str
    start_ts: float          # epoch seconds: exact meeting start
    timezone: str            # IANA timezone name, e.g. "America/New_York"
    location_or_link: str    # exact location or meeting link
    status: str              # canonical commit-state label (see STATUS_* above)
    owner_attends: bool = True
    deal_version: int = 1    # bumped on every material change (reschedule, scope)
    deal_value_usd: Optional[float] = None
    time_sensitive: bool = False


@dataclass(frozen=True)
class OwnerBrief:
    """The minimum owner-brief packet plus binding and delivery evidence.

    Every content field is required: the gate rejects incomplete packets.
    Binding fields (meeting_id / deal_id / meeting_start_ts / deal_version)
    pin the brief to one exact meeting at one exact time and version, so a
    stale or wrong-deal brief can never satisfy the gate.
    """

    brief_id: str
    meeting_id: str
    deal_id: str
    meeting_start_ts: float  # exact start the brief was prepared against
    deal_version: int
    generated_ts: float      # epoch seconds: when the brief was written
    generated_by: str        # agent seat/handle that prepared the brief
    # --- minimum brief packet (all required) ---
    counterparty_name: str   # who the person is
    organization: str        # their organization
    lead_origin: str         # how/why the lead exists
    deal_summary: str        # deal/opportunity description
    deal_value_usd: Optional[float]  # estimated value (number)
    deal_value_range: str     # estimated value/range (text); one of the two required
    value_evidence: str      # evidence behind the value estimate
    said_promised_offered: str  # what has already been said/promised/offered
    meeting_objective: str
    likely_asks: tuple       # likely asks from the counterparty
    key_questions: tuple     # key questions Bryce should ask
    commitments_risks_to_avoid: str
    recommended_opening: str
    recommended_closing: str
    source_links: tuple      # source links / receipts
    scheduled_time_line: str  # exact time/timezone/location/link, human readable
    followup_owner: str       # which agent owns follow-up
    # --- delivery evidence ---
    delivered_ts: Optional[float] = None  # epoch seconds: when Bryce received it
    delivery_channel: str = ""            # channel name the delivery used

    def __post_init__(self):
        # Tolerate list inputs; store canonical tuples.
        object.__setattr__(self, "likely_asks", tuple(self.likely_asks or ()))
        object.__setattr__(self, "key_questions", tuple(self.key_questions or ()))
        object.__setattr__(self, "source_links", tuple(self.source_links or ()))


# Required packet fields: blank/empty counts as missing.
REQUIRED_TEXT_FIELDS = (
    "counterparty_name",
    "organization",
    "lead_origin",
    "deal_summary",
    "value_evidence",
    "said_promised_offered",
    "meeting_objective",
    "commitments_risks_to_avoid",
    "recommended_opening",
    "recommended_closing",
    "scheduled_time_line",
    "followup_owner",
    "generated_by",
)
REQUIRED_LIST_FIELDS = (
    "likely_asks",
    "key_questions",
    "source_links",
)


def packet_problems(brief: OwnerBrief) -> list:
    """Return human-readable problems with the brief packet ([] == complete)."""
    problems = []
    for attr in REQUIRED_TEXT_FIELDS:
        value = getattr(brief, attr, "")
        if not isinstance(value, str) or not value.strip():
            problems.append("missing/blank %s" % attr)
    for attr in REQUIRED_LIST_FIELDS:
        value = getattr(brief, attr, ())
        if not value:
            problems.append("missing/empty %s" % attr)
    has_number = brief.deal_value_usd is not None
    has_range = isinstance(brief.deal_value_range, str) and bool(brief.deal_value_range.strip())
    if not (has_number or has_range):
        problems.append("missing deal value: set deal_value_usd or deal_value_range")
    return problems


def brief_packet_template(meeting: Meeting, generated_by: str, *, now: float = None) -> OwnerBrief:
    """Build a blank-but-bound brief packet pre-filled from the meeting.

    Agents fill in the content fields; the binding fields are already pinned
    to this exact meeting, start time, and deal version.
    """
    now = time.time() if now is None else float(now)
    when = time.strftime("%Y-%m-%d %H:%M %Z", time.gmtime(meeting.start_ts))
    return OwnerBrief(
        brief_id="OB-%s-v%d" % (meeting.meeting_id, meeting.deal_version),
        meeting_id=meeting.meeting_id,
        deal_id=meeting.deal_id,
        meeting_start_ts=meeting.start_ts,
        deal_version=meeting.deal_version,
        generated_ts=now,
        generated_by=generated_by,
        counterparty_name=meeting.counterparty_name,
        organization=meeting.organization,
        lead_origin="",
        deal_summary="",
        deal_value_usd=meeting.deal_value_usd,
        deal_value_range="",
        value_evidence="",
        said_promised_offered="",
        meeting_objective="",
        likely_asks=(),
        key_questions=(),
        commitments_risks_to_avoid="",
        recommended_opening="",
        recommended_closing="",
        source_links=(),
        scheduled_time_line="%s (%s) -- %s" % (when, meeting.timezone, meeting.location_or_link),
        followup_owner="",
    )


# ---------------------------------------------------------------------------
# Interface boundary to WO-1's owner commit gate (state machine lives there)
# ---------------------------------------------------------------------------

class OwnerCommitGate(Protocol):
    """Interface boundary for WO-1's owner-commit gate.

    WO-1 owns the commit state machine. This gate only needs the
    externally-confirmed signal; implementers adapt WO-1's module to this
    protocol and inject it. The gate never re-implements WO-1's transitions.
    """

    def externally_confirmed(self, meeting_id: str) -> bool:
        """True iff WO-1's state machine holds this meeting EXTERNALLY_CONFIRMED."""
        ...

    def commit_state(self, meeting_id: str) -> str:
        """WO-1's canonical commit-state label for the meeting."""
        ...


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateDecision:
    verdict: str          # PASS / STOP / NOT_APPLICABLE
    reasons: tuple         # human-readable, stable reason strings
    meeting_id: str
    brief_id: Optional[str]
    evaluated_ts: float
    urgency: str           # routine / urgent
    confirmed: bool
    confirmed_via: str     # "wo1-commit-gate" or "meeting-status-label"

    @property
    def is_blocked(self) -> bool:
        return self.verdict == VERDICT_STOP


# ---------------------------------------------------------------------------
# Urgent delivery path: code + record-only evidence (NO live sends)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeliveryRecord:
    """Record of an urgent owner-brief delivery OBLIGATION.

    This is evidence that the obligation was recorded -- it is NOT a sent
    message. live_send_performed is ALWAYS False; a live sender (human or
    authorized dispatcher) must fulfill the obligation separately.
    """

    brief_id: Optional[str]
    meeting_id: str
    channel: str            # notification surface name, e.g. "slack-dm"
    attempted_ts: float
    urgency: str
    status: str             # always "recorded-obligation"
    note: str
    live_send_performed: bool = False


@dataclass(frozen=True)
class DeliveryReceipt:
    record: DeliveryRecord
    received_ts: float
    surface_channel: str
    live_send_performed: bool = False


class NotificationSurface(Protocol):
    """A record-only urgent-notification surface.

    Implementations MUST NOT send anything; record() only stores the
    obligation and returns a receipt. There is deliberately no send method.
    """

    @property
    def channel(self) -> str:
        ...

    def record(self, record: DeliveryRecord) -> DeliveryReceipt:
        ...


class RecordingSurface:
    """In-memory record-only surface (reference implementation / test double)."""

    def __init__(self, channel: str):
        self._channel = str(channel)
        self.log: list = []

    @property
    def channel(self) -> str:
        return self._channel

    def record(self, record: DeliveryRecord) -> DeliveryReceipt:
        if record.live_send_performed:
            raise ValueError("record-only surface cannot accept a live-send record")
        self.log.append(record)
        return DeliveryReceipt(
            record=record,
            received_ts=record.attempted_ts,
            surface_channel=self._channel,
            live_send_performed=False,
        )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class OwnerBriefGate:
    """Enforces the pre-meeting owner-brief invariant."""

    def __init__(
        self,
        *,
        min_lead_seconds: float = DEFAULT_MIN_LEAD_SECONDS,
        urgent_value_usd: float = DEFAULT_URGENT_VALUE_USD,
        urgent_window_seconds: float = DEFAULT_URGENT_WINDOW_SECONDS,
    ):
        self.min_lead_seconds = float(min_lead_seconds)
        self.urgent_value_usd = float(urgent_value_usd)
        self.urgent_window_seconds = float(urgent_window_seconds)

    # -- urgency ---------------------------------------------------------
    def classify_urgency(self, meeting: Meeting, now: float = None) -> str:
        now = time.time() if now is None else float(now)
        value = meeting.deal_value_usd or 0.0
        if value >= self.urgent_value_usd:
            return URGENCY_URGENT
        if meeting.time_sensitive:
            return URGENCY_URGENT
        seconds_to_start = meeting.start_ts - now
        if 0 <= seconds_to_start <= self.urgent_window_seconds:
            return URGENCY_URGENT
        return URGENCY_ROUTINE

    # -- urgent path: record obligations, never send ---------------------
    def record_urgent_delivery_obligations(
        self,
        meeting: Meeting,
        brief: Optional[OwnerBrief] = None,
        surfaces: tuple = (),
        *,
        now: float = None,
    ) -> tuple:
        """Record urgent delivery obligations on every surface (no live sends).

        Returns DeliveryReceipts as evidence. For routine meetings this is a
        no-op returning (). Raises RuntimeError if any surface claims a live
        send happened (record-only surfaces must never do that).
        """
        now = time.time() if now is None else float(now)
        if self.classify_urgency(meeting, now) != URGENCY_URGENT:
            return ()
        receipts = []
        for surface in surfaces:
            if brief is None:
                note = (
                    "URGENT owner-brief delivery obligation recorded, but no "
                    "brief exists yet: generate the owner brief first, then "
                    "fulfill this delivery obligation. Record only -- no "
                    "message, email, or notification was sent by this code."
                )
                brief_id = None
            else:
                note = (
                    "URGENT owner-brief delivery obligation recorded for brief "
                    "%s. Record only -- no message, email, or notification "
                    "was sent by this code; a live sender must fulfill it."
                    % brief.brief_id
                )
                brief_id = brief.brief_id
            record = DeliveryRecord(
                brief_id=brief_id,
                meeting_id=meeting.meeting_id,
                channel=surface.channel,
                attempted_ts=now,
                urgency=URGENCY_URGENT,
                status="recorded-obligation",
                note=note,
                live_send_performed=False,
            )
            receipt = surface.record(record)
            if receipt.live_send_performed or record.live_send_performed:
                raise RuntimeError(
                    "record-only surface reported a live send; refusing")
            receipts.append(receipt)
        return tuple(receipts)

    # -- the gate --------------------------------------------------------
    def evaluate(
        self,
        meeting: Meeting,
        brief: Optional[OwnerBrief] = None,
        *,
        now: float = None,
        commit_gate: Optional[OwnerCommitGate] = None,
    ) -> GateDecision:
        now = time.time() if now is None else float(now)
        if commit_gate is not None:
            confirmed = bool(commit_gate.externally_confirmed(meeting.meeting_id))
            confirmed_via = "wo1-commit-gate"
        else:
            confirmed = meeting.status == STATUS_EXTERNALLY_CONFIRMED
            confirmed_via = "meeting-status-label"

        urgency = self.classify_urgency(meeting, now)
        brief_id = brief.brief_id if brief is not None else None

        def decide(verdict, reasons):
            return GateDecision(
                verdict=verdict,
                reasons=tuple(reasons),
                meeting_id=meeting.meeting_id,
                brief_id=brief_id,
                evaluated_ts=now,
                urgency=urgency,
                confirmed=confirmed,
                confirmed_via=confirmed_via,
            )

        # Gate applies only to externally confirmed meetings Bryce attends.
        if not meeting.owner_attends:
            return decide(VERDICT_NOT_APPLICABLE,
                          ["owner does not attend this meeting; brief gate not applicable"])
        if not confirmed:
            return decide(VERDICT_NOT_APPLICABLE,
                          ["meeting is not externally confirmed; brief gate not applicable"])

        # 1. confirmed + no brief = STOP.
        if brief is None:
            return decide(VERDICT_STOP, [
                "meeting is externally confirmed and owner-attended but no "
                "owner brief exists",
            ])

        # 2. Binding: the brief must be for THIS meeting, THIS deal,
        #    THIS exact start time, and THIS deal version.
        if brief.meeting_id != meeting.meeting_id:
            return decide(VERDICT_STOP, [
                "wrong-deal brief: brief %s binds to meeting %s, not %s"
                % (brief.brief_id, brief.meeting_id, meeting.meeting_id),
            ])
        if brief.deal_id != meeting.deal_id:
            return decide(VERDICT_STOP, [
                "wrong-deal brief: brief %s binds to deal %s, not %s"
                % (brief.brief_id, brief.deal_id, meeting.deal_id),
            ])
        if brief.meeting_start_ts != meeting.start_ts:
            return decide(VERDICT_STOP, [
                "stale brief: brief %s was prepared against start %r, but the "
                "meeting now starts at %r (rescheduled after the brief)"
                % (brief.brief_id, brief.meeting_start_ts, meeting.start_ts),
            ])
        if brief.deal_version != meeting.deal_version:
            return decide(VERDICT_STOP, [
                "stale brief: brief %s was prepared against deal version %d, "
                "but the meeting is at deal version %d"
                % (brief.brief_id, brief.deal_version, meeting.deal_version),
            ])

        # 3. Packet completeness: every minimum-packet field is required.
        problems = packet_problems(brief)
        if problems:
            return decide(VERDICT_STOP, [
                "brief packet incomplete: %s" % "; ".join(problems),
            ])

        # 4. Time ordering: generated before the meeting starts (a brief
        #    generated after the meeting starts does NOT satisfy the gate),
        #    generated before/at delivery, delivered in the past.
        if brief.generated_ts >= meeting.start_ts:
            return decide(VERDICT_STOP, [
                "brief %s was generated at/after the meeting start; a brief "
                "generated after the meeting starts does not satisfy the gate"
                % brief.brief_id,
            ])
        if brief.delivered_ts is None:
            return decide(VERDICT_STOP, [
                "brief %s exists but was never delivered" % brief.brief_id,
            ])
        if brief.generated_ts > brief.delivered_ts:
            return decide(VERDICT_STOP, [
                "brief %s has inconsistent timestamps: generated after delivery"
                % brief.brief_id,
            ])
        if brief.delivered_ts > now:
            return decide(VERDICT_STOP, [
                "brief %s delivery timestamp is in the future; it cannot have "
                "been delivered yet" % brief.brief_id,
            ])

        # 5. Lead time: delivered early enough for Bryce to actually read it.
        lead = meeting.start_ts - brief.delivered_ts
        if lead < self.min_lead_seconds:
            return decide(VERDICT_STOP, [
                "brief %s delivered only %.0f seconds before the meeting "
                "start; need at least %.0f seconds of lead time"
                % (brief.brief_id, lead, self.min_lead_seconds),
            ])

        return decide(VERDICT_PASS, [
            "fresh complete brief %s delivered %.0f seconds before start "
            "(>= %.0f required)" % (brief.brief_id, lead, self.min_lead_seconds),
        ])

    def process(
        self,
        meeting: Meeting,
        brief: Optional[OwnerBrief] = None,
        surfaces: tuple = (),
        *,
        now: float = None,
        commit_gate: Optional[OwnerCommitGate] = None,
    ):
        """Evaluate the gate; for urgent meetings also record delivery obligations.

        Returns (GateDecision, tuple[DeliveryReceipt, ...]). Never sends anything.
        """
        decision = self.evaluate(meeting, brief, now=now, commit_gate=commit_gate)
        receipts: tuple = ()
        if decision.urgency == URGENCY_URGENT:
            receipts = self.record_urgent_delivery_obligations(
                meeting, brief, surfaces, now=now)
        return decision, receipts
