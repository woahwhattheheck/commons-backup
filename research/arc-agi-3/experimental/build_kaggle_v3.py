"""Build an experimental one-file ARC-AGI-3 Kaggle agent from the stable v2 drop-in.

In Commons this script lives under research/arc-agi-3/experimental and reads the
byte-current stable ../kaggle_my_agent.py plus this directory's object-transfer
module. It writes a new file; it never mutates the stable v2 source.
"""
from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BASE = HERE.parent / "kaggle_my_agent.py"
DEFAULT_EXTENSION = HERE / "arc3_object_transfer.py"

ADAPTER = r'''

_BaseMyAgent = MyAgent


class MyAgent(_BaseMyAgent):
    """Experimental object-transfer v3 layered on the stable one-file adapter."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.policy = ObjectTransferExplorer()

    @property
    def name(self) -> str:
        return f"{super().name}.object-transfer-v3"

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            return GameAction.RESET
        decision = self.policy.choose(
            latest_frame.frame,
            latest_frame.available_actions,
            state=latest_frame.state,
            levels_completed=latest_frame.levels_completed,
        )
        action = GameAction.from_id(decision.action_id)
        if decision.action_id == 6:
            action.set_data(decision.as_action_data())
        diagnostics = self.policy.diagnostics()
        action.reasoning = {
            "policy": diagnostics["policy"],
            "reason": decision.reason,
            "unique_states": diagnostics["unique_states"],
            "object_plans": diagnostics["object_plans"],
            "movement_models": diagnostics["movement_models"],
            "blocked_predictions": diagnostics["blocked_predictions"],
            "decisions": diagnostics["total_decisions"],
        }
        return action
'''


def build(base: Path, extension: Path, output: Path) -> Path:
    base_text = base.read_text()
    extension_text = extension.read_text()
    marker = "Fingerprint = tuple[int, int, int, tuple[tuple[int, int], ...]]"
    start = extension_text.find(marker)
    if start < 0:
        raise ValueError(f"extension marker not found in {extension}")
    inline_extension = extension_text[start:]
    generated = (
        base_text.rstrip()
        + "\n\n# --- SOL-ARC3 experimental object-transfer v3 extension ---\n"
        + inline_extension.rstrip()
        + ADAPTER
    )
    # The generated one-file deployment must not depend on Commons-local modules.
    if "from arc3_baseline import" in generated or "from arc3_object_transfer import" in generated:
        raise ValueError("generated file still has a local project import")
    output.write_text(generated)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--extension", type=Path, default=DEFAULT_EXTENSION)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.base, args.extension, args.output))


if __name__ == "__main__":
    main()
