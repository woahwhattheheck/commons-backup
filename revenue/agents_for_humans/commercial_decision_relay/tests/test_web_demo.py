import json
from pathlib import Path

from decision_relay.core import reconcile
from decision_relay.web_demo import render_dashboard


def test_dashboard_has_decision_and_routine_states():
    batch = json.loads((Path(__file__).parents[1] / "fixtures" / "demo-batch.json").read_text())
    html = render_dashboard(reconcile(batch))
    assert "HUMAN_CLOSING_READY" in html
    assert "COUNTEROFFER_REVIEW" in html
    assert "DECLINED" in html
    assert "AWAITING_RESPONSE" in html
    assert "payment_or_charge=false" in html
