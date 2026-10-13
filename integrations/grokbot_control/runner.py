#!/usr/bin/env python3
"""Seat runners: hermetic echo + in-process GrokBot seat execution."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol

from .pools import attribution


@dataclass
class SeatResult:
    result_text: str
    attribution: dict[str, str]
    cancelled: bool = False


class SeatRunner(Protocol):
    def execute(
        self,
        *,
        run_id: str,
        session_id: str,
        pool_id: str,
        seat: str,
        prompt: str,
        history: list[dict[str, Any]],
        cancel_event: threading.Event,
    ) -> SeatResult: ...


class EchoSeatRunner:
    """Hermetic runner: attributed echo proving control path + attribution."""

    def execute(
        self,
        *,
        run_id: str,
        session_id: str,
        pool_id: str,
        seat: str,
        prompt: str,
        history: list[dict[str, Any]],
        cancel_event: threading.Event,
    ) -> SeatResult:
        if cancel_event.is_set():
            return SeatResult(
                result_text="",
                attribution=attribution(pool_id=pool_id, seat=seat),
                cancelled=True,
            )
        turn = len(history) + 1
        text = (
            "GrokBot seat %s pool=%s session=%s run=%s turn=%d echo: %s"
            % (seat, pool_id, session_id, run_id, turn, prompt)
        )
        return SeatResult(
            result_text=text,
            attribution=attribution(pool_id=pool_id, seat=seat),
        )


class InProcessSeatRunner:
    """Execute work inside this GrokBot seat process (live round-trip road).

    A Commons coordinator submits via the gateway; this runner is the
    executing GrokBot seat. No grok.com browser queue. No new secrets.
    Optional handler override for production seats.
    """

    def __init__(self, handler=None, *, default_seat: str = "SPARK") -> None:
        self._handler = handler
        self.default_seat = default_seat

    def execute(
        self,
        *,
        run_id: str,
        session_id: str,
        pool_id: str,
        seat: str,
        prompt: str,
        history: list[dict[str, Any]],
        cancel_event: threading.Event,
    ) -> SeatResult:
        if cancel_event.is_set():
            return SeatResult(
                result_text="",
                attribution=attribution(pool_id=pool_id, seat=seat),
                cancelled=True,
            )
        if self._handler is not None:
            text = self._handler(
                prompt=prompt,
                run_id=run_id,
                session_id=session_id,
                pool_id=pool_id,
                seat=seat,
                history=history,
                cancel_event=cancel_event,
            )
            if cancel_event.is_set():
                return SeatResult(
                    result_text="",
                    attribution=attribution(pool_id=pool_id, seat=seat),
                    cancelled=True,
                )
            return SeatResult(
                result_text=str(text),
                attribution=attribution(pool_id=pool_id, seat=seat),
            )
        # Default live seat behavior: return measured attribution + prompt ack.
        # A peer replacing SPARK swaps handler; the control surface stays.
        lines = [
            "GrokBot in-process seat execution",
            "seat=%s" % seat,
            "pool_id=%s" % pool_id,
            "session_id=%s" % session_id,
            "run_id=%s" % run_id,
            "history_turns=%d" % len(history),
            "prompt=%s" % prompt,
        ]
        return SeatResult(
            result_text="\n".join(lines),
            attribution=attribution(pool_id=pool_id, seat=seat),
        )