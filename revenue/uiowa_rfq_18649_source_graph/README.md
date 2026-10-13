# UIOWA-104 — finding-to-source relationship graph

This is a presentation and navigation layer over the existing UIOWA-036 citation resolver already carried on this branch. It does not create a second evidence model and does not turn a resolved link into source authenticity, a verified finding, maturity, or recommendation approval.

The graph presents four layers: recommendation → finding → observation/citation → exact source identity. Several observations that cite the same `(source_id, version, SHA-256)` converge on one source node. Unresolved references stay visible with resolver diagnostics. Explicit disagreement is rendered as a contradiction edge while both source finding records remain intact. The complete resolver trace is embedded in the graph artifact so the visualization cannot hide the underlying records.

Run the focused tests normally and under optimization. The checked `examples/graph.html` is a self-contained portable acceptance example; `build_graph(trace, contradictions)` consumes complete resolver traces and `render_html(graph)` produces the offline inspector.

The worked data are fictional preparation fixtures. This graph demonstrates traceability behavior; it does not assert University of Iowa practices, evidence authenticity, or approval of any recommendation.
