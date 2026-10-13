"""Regenerate the two-page method note; requires reportlab and DejaVu Sans."""
from pathlib import Path
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

root = Path(__file__).resolve().parent
summary = json.loads((root / "benchmark/summary.json").read_text())
for name, file in [("Body", "DejaVuSans.ttf"), ("Strong", "DejaVuSans-Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, "/usr/share/fonts/truetype/dejavu/" + file))
navy, teal, grey = [colors.HexColor(x) for x in ["#163147", "#006d77", "#52616d"]]
styles = {
    "eye": ParagraphStyle("eye", fontName="Strong", fontSize=8, leading=11, textColor=teal, spaceAfter=10),
    "title": ParagraphStyle("title", fontName="Strong", fontSize=22, leading=27, textColor=navy, spaceAfter=16),
    "h": ParagraphStyle("h", fontName="Strong", fontSize=10.5, leading=14, textColor=navy, spaceBefore=10, spaceAfter=5),
    "body": ParagraphStyle("body", fontName="Body", fontSize=9.3, leading=13, textColor=navy, spaceAfter=8),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8, leading=11, textColor=grey, spaceAfter=6),
}
story = []
def p(text, style="body"):
    story.append(Paragraph(text, styles[style]))

p("ROADEF/EURO 2026 / CANDIDATE METHOD / 7 SEPTEMBER 2026", "eye")
p("Budget-preserving<br/>adaptive routing search", "title")
p("SEDGE / TokenJunkieLabs - C++20 implementation", "small")
p("The solver chooses waypoint lists for traffic demands over a maintenance horizon. It aims to reduce the sorted vector of link utilizations while satisfying the segment limit and the reconfiguration budget at every transition. This is a heuristic candidate; no optimality or competition-rank claim is made.")
p("1. Forwarding model", "h")
p("For each time and destination, reverse Dijkstra builds the shortest-path forwarding DAG after removing that time's offline links. A unit demand splits equally among outgoing shortest-path arcs at each visited node. Sparse coefficients express a segment's contribution to link utilization. Coefficients are cached, with the segment cache cleared at 300,000 entries. A waypoint route adds its constituent segment flows.")
p("2. Feasible initialization and neighborhood", "h")
p("The initial solution uses no waypoints and has zero reconfiguration cost. Search first changes a demand's route throughout the horizon, preserving its transition costs. Later, a move may cover one slot, a prefix or a suffix. The exact symmetric difference of successive segment sets gives the change cost. Every affected transition is checked before a move is accepted.")
p("Moves remove, replace, prepend or append waypoints, using at most three waypoints and respecting a smaller input segment limit. Demands are prioritized by contribution to a highly loaded link/time pair. Waypoints combine nearby nodes and a seeded sample. Several demands can improve before congestion priorities are rebuilt. This neighborhood is not exhaustive.")
p("3. Acceptance and execution", "h")
p("A move compares the sorted multiset of changed loads; unchanged elements cancel in lexicographic comparison. The checker truncates decimal output. Conservative bounds around changed loads at six decimal places reduce sensitivity to floating-point accumulation noise. Only an improving comparison is accepted.")
p("The four-argument run.sh executes the native binary directly. A zero-waypoint incumbent is written immediately. Later checkpoints use atomic rename. SIGTERM ends search and saves the incumbent. The default allowance is 565 seconds. A fixed seed produces repeatable fixed-round runs; wall-time cutoffs can stop at different search points on different hardware.")
p("No runtime network, commercial solver, GPU or model API is required. RapidJSON is bundled under its upstream license. Input metrics and capacities are positive in all tested supplied instances.", "small")
story.append(PageBreak())
p("PUBLIC-INSTANCE EVIDENCE", "eye")
p("Twelve valid improvements", "title")
p("Each public set-B instance ran with a 15-second allowance, with two independent processes at a time. The unmodified official checker v1.2.2 accepted every output and ranked it above empty-waypoint routing. The table reports its six-decimal maximum link utilization (MLU).")
rows = [["Instance", "Baseline MLU", "Candidate MLU", "MLU reduction"]]
for item in summary["instances"]:
    rows.append([item["instance"], f'{item["baseline_mlu_6"]:.6f}', f'{item["final_mlu_6"]:.6f}', f'{100 * item["relative_mlu_reduction"]:.2f}%'])
table = Table(rows, colWidths=[95, 116, 125, 110], repeatRows=1, hAlign="LEFT")
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Strong"), ("FONTNAME", (0, 1), (-1, -1), "Body"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEADING", (0, 0), (-1, -1), 11),
    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f1f5f7"), colors.white]),
]))
story.append(table)
story.append(Spacer(1, 10))
p("Seven cases reduce the worst load. Five improve later entries in the sorted vector, which also counts as a strict improvement under the ranking rule. Hidden-instance performance is unknown.", "small")
p("Independent checks", "h")
p("All 369,960 predicted link/time values agree with the checker within approximately 1.001e-12. Transition-cost totals match. Further checks cover unequal-branch ECMP, noncontiguous node IDs, maintenance changes, zero budgets, fixed-round repeatability, quoted filenames and SIGTERM. The signal test saved a valid result and exited in approximately 0.017 seconds.")
p("Execution status and continuation", "h")
p("Native and Ubuntu 24.04 Docker execution are verified. GitHub Actions run 34080604676 built the exact published package and ran setB-01 with networking disabled. The official checker accepted all 10,368 load values (error below 1.001e-12); MLU fell from 0.999998 to 0.532975 in 20 seconds. Actual team registration, team ID and organizer submission remain outstanding.")
p("Provenance", "h")
p("Challenge source: d84d319a7fdb8de3b1866830d2eaa2937871e5ae. Networktools: aebafc9ee91891e5d721bb86725e8cf1533877d1. Exact input, source, binary and solution hashes are in benchmark/summary.json. Source, build instructions and retained checker outputs accompany this note.", "small")
p('<link href="https://roadef.org/challenge/2026/en/">Official challenge and rules</link> | <link href="https://gitlab.com/Orange-OpenSource/network-optimization-tools/challenge-roadef-2026/">Official specification, instances and checker</link>', "small")

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d6dfe4"))
    canvas.line(48, 42, A4[0] - 48, 42)
    canvas.setFont("Body", 7)
    canvas.setFillColor(grey)
    canvas.drawString(48, 29, "SEDGE / TokenJunkieLabs - candidate implementation, not a submitted entry")
    canvas.drawRightString(A4[0] - 48, 29, str(doc.page))
    canvas.restoreState()

doc = SimpleDocTemplate(str(root / "method.pdf"), pagesize=A4, rightMargin=48, leftMargin=48,
                        topMargin=44, bottomMargin=54, title="SEDGE routing solver - ROADEF/EURO 2026 method",
                        author="TokenJunkieLabs / SEDGE")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
