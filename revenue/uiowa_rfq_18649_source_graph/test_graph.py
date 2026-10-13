import copy
import json
import unittest

from revenue.uiowa_rfq_18649_source_graph.graph import GraphError, build_graph, render_html


def _citation(cid, sid, version, sha, *, resolved=True, locator="lines 2-3", diagnostics=None):
    return {
        "citation_id": cid,
        "source_id": sid,
        "version": version,
        "sha256": sha,
        "requested_locator": locator,
        "requested_quote": f"quote-{cid}",
        "resolved": resolved,
        "bound_to_compiler_source": resolved,
        "diagnostics": list(diagnostics or []),
        "citation": ({
            "source_path": f"documents/{sid}.md",
            "retained_path": f"original/documents/{sid}.md",
            "locator": locator,
            "quote": f"quote-{cid}",
            "context": f"context-{cid}",
            "warnings": [],
        } if resolved else None),
    }


def trace_fixture():
    shared = "a" * 64
    missing = "b" * 64
    return {
        "schema": "uiowa.citation-trace.v1",
        "label": "SYNTHETIC_DRAFT_NON_AUTHORITATIVE",
        "findings": [
            {"finding_id": "F-A", "kind": "strength", "group": "ESS", "dimension": "software",
             "statement": "First interpretation", "limits": "fixture", "trace_status": "SOURCE_LINKS_RESOLVED",
             "citations": [_citation("F-A-C1", "SRC-1", "v1", shared)]},
            {"finding_id": "F-B", "kind": "gap", "group": "ESS", "dimension": "software",
             "statement": "Contradictory interpretation", "limits": "fixture", "trace_status": "SOURCE_LINKS_RESOLVED",
             "citations": [_citation("F-B-C1", "SRC-1", "v1", shared)]},
            {"finding_id": "F-MISSING", "kind": "open_question", "group": "RIS", "dimension": "ai_readiness",
             "statement": "Requested evidence absent", "limits": "fixture", "trace_status": "REVIEW_REQUIRED",
             "citations": [_citation("F-MISSING-C1", "SRC-X", "v1", missing, resolved=False,
                                     diagnostics=["MISSING_SOURCE_ID"])]},
        ],
        "recommendations": [
            {"recommendation_id": "R-1", "finding_ids": ["F-A", "F-B"], "action": "Reconcile interpretations",
             "rationale": "Shared bytes need review", "phase": "0-90 days", "owner_role": "Reviewer",
             "effort": "fixture", "outcome_measure": "resolution"},
            {"recommendation_id": "R-2", "finding_ids": ["F-MISSING"], "action": "Request missing source",
             "rationale": "Cannot invent citation", "phase": "0-90 days", "owner_role": "Custodian",
             "effort": "fixture", "outcome_measure": "source supplied or remains open"},
        ],
        "source_inventory": [],
        "executive_summary": {"finding_ids": ["F-A", "F-B", "F-MISSING"], "recommendation_ids": ["R-1", "R-2"]},
        "limits": "fixture",
    }


class GraphTests(unittest.TestCase):
    def test_shared_exact_source_is_one_node(self):
        graph = build_graph(trace_fixture(), [("F-A", "F-B")])
        sources = [n for n in graph["nodes"] if n["kind"] == "source"]
        self.assertEqual(2, len(sources))
        shared = [n for n in sources if n["source_id"] == "SRC-1"]
        self.assertEqual(1, len(shared))
        self.assertEqual(1, graph["counts"]["shared_sources"])
        incoming = [e for e in graph["edges"] if e["target"] == shared[0]["id"]]
        self.assertEqual(2, len(incoming))

    def test_unresolved_reference_is_retained_with_diagnostic(self):
        graph = build_graph(trace_fixture(), [("F-A", "F-B")])
        obs = next(n for n in graph["nodes"] if n.get("citation_id") == "F-MISSING-C1")
        self.assertFalse(obs["resolved"])
        self.assertEqual(["MISSING_SOURCE_ID"], obs["diagnostics"])
        edge = next(e for e in graph["edges"] if e["source"] == obs["id"])
        self.assertEqual("requests_source", edge["relation"])
        self.assertEqual(1, graph["counts"]["unresolved_observations"])

    def test_contradiction_is_explicit_and_deduplicated(self):
        graph = build_graph(trace_fixture(), [("F-B", "F-A"), ("F-A", "F-B")])
        contradictions = [e for e in graph["edges"] if e["relation"] == "contradicts"]
        self.assertEqual(1, len(contradictions))
        self.assertTrue(contradictions[0]["bidirectional"])
        self.assertEqual(1, graph["counts"]["contradictions"])

    def test_full_trace_is_preserved_without_mutation(self):
        trace = trace_fixture()
        before = copy.deepcopy(trace)
        graph = build_graph(trace, [("F-A", "F-B")])
        self.assertEqual(before, trace)
        self.assertEqual(before, graph["trace"])

    def test_bad_recommendation_and_contradiction_fail_closed(self):
        trace = trace_fixture()
        trace["recommendations"][0]["finding_ids"].append("NOPE")
        with self.assertRaises(GraphError):
            build_graph(trace)
        with self.assertRaises(GraphError):
            build_graph(trace_fixture(), [("F-A", "NOPE")])

    def test_static_html_is_self_contained_and_safe(self):
        trace = trace_fixture()
        trace["findings"][0]["statement"] = "</script><b>not markup</b>"
        graph = build_graph(trace, [("F-A", "F-B")])
        page = render_html(graph)
        self.assertEqual(1, page.count('<script type="application/json" id="graph-data">'))
        self.assertNotIn("</script><b>not markup</b>", page)
        payload = page.split('<script type="application/json" id="graph-data">', 1)[1].split("</script>", 1)[0]
        parsed = json.loads(payload.replace("<\\/", "</"))
        self.assertEqual(graph, parsed)
        self.assertNotIn("https://", page)
        self.assertNotIn("<script src=", page)
        self.assertNotIn("<link rel=", page)


if __name__ == "__main__":
    unittest.main()
