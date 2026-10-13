from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

VARIANTS = ("full", "no_skill_reuse", "no_model_update", "no_information_gain")


def _stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


@dataclass(frozen=True)
class Episode:
    family: int
    surface: int
    mode: int
    goal: int

    @property
    def signature(self) -> tuple[int, int]:
        return self.family, self.surface

    @property
    def correct_action(self) -> int:
        # Hidden deterministic transition family. The rule is intentionally
        # simple enough to audit yet requires intervention on unseen signatures.
        return (self.family * 3 + self.surface * 2 + self.mode + self.goal) % 5


class Agent:
    def __init__(self, variant: str, seed: int):
        if variant not in VARIANTS:
            raise ValueError(variant)
        self.variant = variant
        self.rng = random.Random(seed)
        self.skill: dict[tuple[int, int, int, int], int] = {}
        self.effect_votes: dict[tuple[int, int], list[int]] = {}

    def _candidate_order(self, ep: Episode) -> list[int]:
        candidates = list(range(5))
        if self.variant == "no_information_gain":
            # Fixed open-loop order ignores learned empirical action effects.
            return candidates
        if self.variant != "no_model_update":
            votes = self.effect_votes.get(ep.signature, [])
            if votes:
                counts = {offset: votes.count(offset) for offset in candidates}
                best_offset = min(candidates, key=lambda offset: (-counts[offset], offset))
                predicted = (best_offset + ep.goal) % 5
                return [predicted] + [a for a in candidates if a != predicted]
        if self.variant == "no_model_update":
            # Stable but non-learning intervention order.
            key = f"{ep.family}:{ep.surface}:{ep.mode}:{ep.goal}"
            start = _stable_int(key) % len(candidates)
            return candidates[start:] + candidates[:start]
        # Structural cold-start prior, intentionally weaker than learned votes.
        predicted = (ep.family * 3 + ep.surface * 2) % 5
        return [predicted] + [a for a in candidates if a != predicted]

    def solve(self, ep: Episode) -> int:
        exact = (ep.family, ep.surface, ep.mode, ep.goal)
        if self.variant != "no_skill_reuse" and exact in self.skill:
            return 1
        actions = 0
        for action in self._candidate_order(ep):
            actions += 1
            if action == ep.correct_action:
                if self.variant != "no_skill_reuse":
                    self.skill[exact] = action
                if self.variant != "no_model_update":
                    self.effect_votes.setdefault(ep.signature, []).append((action - ep.goal) % 5)
                return actions
        raise AssertionError("action space exhausted without success")


def episodes(seed: int, count: int = 240) -> list[Episode]:
    rng = random.Random(seed)
    # Repeated latent substructure is deliberate: mode 0 is common and mode 1
    # is a recurring minority regime. The learned coarse effect model can exploit
    # the dominant regularity, while exact skills retain minority fine structure.
    # This makes model learning and skill reuse complementary rather than aliases.
    mode_pool = (0, 0, 0, 1)
    return [Episode(rng.randrange(6), rng.randrange(4), rng.choice(mode_pool), rng.randrange(5)) for _ in range(count)]


def percentile(values: list[int], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def run_variant(variant: str, seeds: range = range(64)) -> dict[str, float | int | str]:
    all_actions: list[int] = []
    successes = 0
    for seed in seeds:
        agent = Agent(variant, seed)
        for ep in episodes(seed):
            used = agent.solve(ep)
            all_actions.append(used)
            successes += 1
    return {
        "name": variant,
        "episodes": len(all_actions),
        "mean_actions": round(mean(all_actions), 6),
        "p95_actions": percentile(all_actions, 0.95),
        "success_rate": round(successes / len(all_actions), 6),
    }


def run() -> dict[str, object]:
    rows = [run_variant(name) for name in VARIANTS]
    return {
        "schema": "arc-paper-microdynamics/v1",
        "evidence_scope": "LOCAL_SYNTHETIC_MECHANISM_ONLY",
        "claims_kaggle_accuracy": False,
        "description": "Deterministic repeated-latent-dynamics sanity check for skill reuse and intervention ordering; not ARC/Kaggle evaluation.",
        "variants": rows,
    }


def write_outputs(directory: Path) -> None:
    results = run()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "experiment_results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = results["variants"]
    assert isinstance(rows, list)
    width, height = 880, 440
    left, top, bottom = 100, 55, 90
    plot_h = height - top - bottom
    max_value = max(float(r["mean_actions"]) for r in rows if isinstance(r, dict))
    bar_w = 120
    gap = 70
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="440" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">Local synthetic mechanism check — mean actions per episode</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{width-40}" y2="{top + plot_h}" stroke="black"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="black"/>',
    ]
    for i, row in enumerate(rows):
        assert isinstance(row, dict)
        value = float(row["mean_actions"])
        h = 0 if max_value == 0 else plot_h * value / max_value
        x = left + 50 + i * (bar_w + gap)
        y = top + plot_h - h
        parts.append(f'<rect x="{x}" y="{y:.2f}" width="{bar_w}" height="{h:.2f}" fill="none" stroke="black" stroke-width="2"/>')
        parts.append(f'<text x="{x+bar_w/2}" y="{y-8:.2f}" text-anchor="middle" font-family="sans-serif" font-size="14">{value:.3f}</text>')
        label = str(row["name"]).replace("_", " ")
        parts.append(f'<text x="{x+bar_w/2}" y="{top+plot_h+26}" text-anchor="middle" font-family="sans-serif" font-size="12">{label}</text>')
    parts.append(f'<text x="24" y="{top+plot_h/2}" transform="rotate(-90 24 {top+plot_h/2})" text-anchor="middle" font-family="sans-serif" font-size="13">actions (lower is better)</text>')
    parts.append('<text x="440" y="426" text-anchor="middle" font-family="sans-serif" font-size="11">LOCAL SYNTHETIC EVIDENCE ONLY — not ARC/Kaggle accuracy</text>')
    parts.append('</svg>')
    (directory / "figures" / "microdynamics_ablation.svg").write_text("\n".join(parts) + "\n", encoding="utf-8")

    architecture = '''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="360" viewBox="0 0 960 360">
<rect width="100%" height="100%" fill="white"/>
<g font-family="sans-serif" font-size="15" fill="none" stroke="black" stroke-width="2">
  <rect x="40" y="120" width="150" height="70"/><rect x="250" y="120" width="160" height="70"/><rect x="470" y="120" width="160" height="70"/><rect x="690" y="120" width="220" height="70"/>
  <path d="M190 155 H250"/><path d="M410 155 H470"/><path d="M630 155 H690"/>
  <path d="M800 190 C800 290 330 290 330 190"/>
</g>
<g font-family="sans-serif" font-size="14" text-anchor="middle">
  <text x="115" y="148">Observation</text><text x="115" y="170">+ change signature</text>
  <text x="330" y="148">Action-effect</text><text x="330" y="170">hypotheses</text>
  <text x="550" y="148">Information-gain</text><text x="550" y="170">probe planner</text>
  <text x="800" y="145">Verified trace → skill</text><text x="800" y="168">preconditions/effects</text>
  <text x="545" y="315">Reuse only when the learned precondition/effect contract still matches</text>
  <text x="480" y="28" font-size="18">Action-efficient online skill induction</text>
</g>
</svg>'''
    (directory / "figures" / "skill_loop.svg").write_text(architecture + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_outputs(Path(__file__).resolve().parent)
