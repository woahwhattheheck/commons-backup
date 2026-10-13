"""Deterministic synthetic comparison: one-step evidence choice vs bounded lookahead.

This benchmark is a wiring/regression hook only.  It is not ARC/Kaggle leaderboard
evidence and makes no claim about hidden competition performance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from sage_symbolic_planner import ActionHypothesis, SymbolicState, plan


def h(text: str) -> str:
    return sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Token:
    name: str
    @property
    def key(self): return self.name


class FixtureAdapter:
    def __init__(self, graph, start):
        self.graph = graph
        self.start = start
        self._model_digest = h(json.dumps(graph, sort_keys=True))
    @property
    def model_digest(self): return self._model_digest
    def root_state(self):
        row = self.graph[self.start]
        return SymbolicState(h(self.start), tuple(sorted(row.get("actions", {}))), row.get("terminal", "NOT_FINISHED"), 0)
    def hypotheses(self, state):
        label = next((k for k in self.graph if h(k) == state.digest), None)
        if label is None: return ()
        out=[]
        for action, edge in sorted(self.graph[label].get("actions", {}).items()):
            conf=edge.get("confidence",9000)
            out.append(ActionHypothesis(Token(action), action, h(label+action), 9, 10, conf, 10000-conf, 10000, edge.get("progress",0), self.graph[edge["to"]].get("terminal","NOT_FINISHED"), 0, edge.get("risk",1000), "SYNTHETIC"))
        return tuple(out)
    def simulate(self,state,hyp):
        label=next(k for k in self.graph if h(k)==state.digest)
        edge=self.graph[label]["actions"][hyp.action_key]
        target=edge["to"]
        row=self.graph[target]
        return SymbolicState(h(target),tuple(sorted(row.get("actions",{}))),row.get("terminal","NOT_FINISHED"),state.cumulative_progress+hyp.progress)


def one_step(adapter):
    root=adapter.root_state()
    choices=adapter.hypotheses(root)
    # Deliberately mirrors a local progress/confidence preference, not the planner score.
    return max(choices,key=lambda x:(x.progress,x.confidence_bps,-x.risk_bps,x.action_key)).action_key


def run():
    cases=[]
    lookahead_wins=0
    one_step_wins=0
    for i in range(24):
        # Immediate-progress decoy vs a two-action terminal route.  Action names are
        # permuted to ensure success is not a lexical artifact.
        decoy=f"ACTION{1+(i%3)}"
        route=f"ACTION{4+(i%3)}"
        finish=f"ACTION{7+(i%3)}"
        graph={
            "S":{"actions":{decoy:{"to":"D","progress":1},route:{"to":"R"}}},
            "D":{"actions":{}},
            "R":{"actions":{finish:{"to":"W"}}},
            "W":{"terminal":"WIN","actions":{}},
        }
        adapter=FixtureAdapter(graph,"S")
        local=one_step(adapter)
        planned=plan(adapter,actions_left=3).selected_prefix
        local_terminal = graph[graph["S"]["actions"][local]["to"]].get("terminal") == "WIN"
        planned_terminal = planned[:2] == (route,finish)
        one_step_wins += int(local_terminal)
        lookahead_wins += int(planned_terminal)
        cases.append({"case":i,"one_step":local,"planner":list(planned),"one_step_terminal":local_terminal,"planner_terminal":planned_terminal})
    result={
        "schema":"commons.arc3-sage-symbolic-planner-benchmark/v1",
        "cases":len(cases),
        "one_step_terminal":one_step_wins,
        "bounded_planner_terminal":lookahead_wins,
        "note":"synthetic deterministic wiring benchmark only; not ARC/Kaggle score evidence",
        "case_digest":h(json.dumps(cases,sort_keys=True,separators=(",",":"))),
    }
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    return result


if __name__ == "__main__":
    run()
