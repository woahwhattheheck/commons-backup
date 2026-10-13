"""Retained hostile proofs for second-precision chronology ambiguity."""

from __future__ import annotations

import copy
import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

import revenue.inbound_lead_control.engine as engine_module
from revenue.inbound_lead_control.engine import InputError, compile_snapshot
from revenue.inbound_lead_control.test_engine import _doc, _event


class InboundLeadChronologyHostiles(unittest.TestCase):
    def _rejects_both_orders(self, events) -> None:
        messages = []
        for ordered in (events, list(reversed(events))):
            doc = _doc()
            doc["leads"][0]["events"] = copy.deepcopy(ordered)
            with self.assertRaisesRegex(InputError, "chronology ambiguity") as caught:
                compile_snapshot(doc)
            messages.append(str(caught.exception))
        self.assertEqual(messages[0], messages[1])

    def test_same_second_human_intent_escalation_fails_closed_in_both_orders(self):
        events = [
            _event(
                "E-general",
                "HUMAN_INBOUND",
                "2026-09-17T08:55:00Z",
                intent="GENERAL",
                content="general-question",
            ),
            _event(
                "E-terms",
                "HUMAN_INBOUND",
                "2026-09-17T08:55:00Z",
                intent="BINDING_TERMS",
                content="binding-terms",
            ),
        ]
        self._rejects_both_orders(events)

    def test_same_second_inbound_outbound_has_no_list_order_authority(self):
        events = [
            _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", content="human"),
            _event("E-out", "OUTBOUND_SENT", "2026-09-17T08:55:00Z", content="sent"),
        ]
        self._rejects_both_orders(events)

    def test_same_second_bounce_inbound_has_no_kind_precedence_authority(self):
        events = [
            _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", content="human"),
            _event("E-bounce", "BOUNCE", "2026-09-17T08:55:00Z", content="bounce"),
        ]
        self._rejects_both_orders(events)

    def test_unfenced_legacy_module_is_not_importable(self):
        self.assertIsNone(importlib.util.find_spec("revenue.inbound_lead_control._engine_v1"))

    def test_public_engine_reload_keeps_compile_and_verify_fenced(self):
        reloaded = importlib.reload(engine_module)
        doc = _doc()
        doc["leads"][0]["events"] = [
            _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", content="human"),
            _event("E-out", "OUTBOUND_SENT", "2026-09-17T08:55:00Z", content="sent"),
        ]
        with self.assertRaisesRegex(reloaded.InputError, "chronology ambiguity"):
            reloaded.compile_snapshot(doc)
        self.assertFalse(reloaded.verify_compiled(doc, {}))

    def test_distinct_seconds_preserve_existing_state_machine(self):
        doc = _doc()
        doc["leads"][0]["events"] = [
            _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:50:00Z"),
            _event("E-out", "OUTBOUND_SENT", "2026-09-17T08:55:00Z"),
        ]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "WAITING_ON_COUNTERPARTY")
        self.assertEqual(row["evidence_refs"]["latest_inbound"]["event_id"], "E-in")
        self.assertEqual(row["evidence_refs"]["latest_outbound"]["event_id"], "E-out")

    def test_real_python_optimized_rejects_all_permutation_predecessors(self):
        code = textwrap.dedent(
            r'''
            import copy
            import importlib
            import importlib.util
            import revenue.inbound_lead_control.engine as engine_module
            from revenue.inbound_lead_control.test_engine import _doc, _event

            if importlib.util.find_spec("revenue.inbound_lead_control._engine_v1") is not None:
                raise SystemExit(10)

            cases = [
                [
                    _event("E-general", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", intent="GENERAL", content="general"),
                    _event("E-terms", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", intent="BINDING_TERMS", content="terms"),
                ],
                [
                    _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", content="human"),
                    _event("E-out", "OUTBOUND_SENT", "2026-09-17T08:55:00Z", content="sent"),
                ],
                [
                    _event("E-in", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", content="human"),
                    _event("E-bounce", "BOUNCE", "2026-09-17T08:55:00Z", content="bounce"),
                ],
            ]

            def check(module):
                for events in cases:
                    messages = []
                    for ordered in (events, list(reversed(events))):
                        doc = _doc()
                        doc["leads"][0]["events"] = copy.deepcopy(ordered)
                        try:
                            module.compile_snapshot(doc)
                        except module.InputError as exc:
                            message = str(exc)
                            if "chronology ambiguity" not in message:
                                raise SystemExit(11)
                            messages.append(message)
                        else:
                            raise SystemExit(12)
                        if module.verify_compiled(doc, {}):
                            raise SystemExit(14)
                    if messages[0] != messages[1]:
                        raise SystemExit(13)

            check(engine_module)
            check(importlib.reload(engine_module))
            '''
        )
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [sys.executable, "-O", "-c", code],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
