"""Score form choices and run bounded plans with the official CUA-S1 checkpoint.

The CLI is scoring-only. ``run_with_driver`` requires an explicitly injected
driver and defaults to a dry run with submission disabled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class ModelBackend:
    """Adapt the published option scorer to upstream Cua-S1 Decisions."""

    def __init__(self, checkpoint: Path, device: str = "auto") -> None:
        from cua_s1.model import load_checkpoint, select_device

        self.model, self.collator, self.config = load_checkpoint(checkpoint, select_device(device))
        self.device = next(self.model.parameters()).device

    def plan(self, form_title: str, elements: list[Any], entities: list[Any]) -> list[Any]:
        from cua_s1.model import ChoiceExample
        from cua_s1.schema import Decision, decode, render_context, render_options
        import torch

        if not elements:
            return []
        options = render_options(entities)
        examples = [
            ChoiceExample(render_context(form_title, element), tuple(options), 0)
            for element in elements
        ]
        batch = {key: value.to(self.device) for key, value in self.collator(examples).items()}
        with torch.inference_mode():
            rows = self.model(batch).softmax(dim=-1).tolist()
        decisions = []
        for element, row in zip(elements, rows):
            distribution = row[: len(options)]
            winner = max(range(len(options)), key=distribution.__getitem__)
            action, entity_index = decode(winner, entities)
            decisions.append(Decision(element, action, entity_index, distribution[winner], distribution))
        return decisions


def run_with_driver(
    *,
    checkpoint: Path,
    driver: Any,
    target: Any,
    form_title: str,
    entities: list[Any],
    device: str = "auto",
    min_confidence: float = 0.5,
    execute: bool = False,
    submit: bool = False,
    delivery_mode: str = "background",
    backend: Any = None,
) -> dict[str, Any]:
    """Plan against one exact window; return a typed report or typed failure.

    ``backend`` permits a deterministic scorer for validation. In production,
    omit it to load the published checkpoint. No driver is created implicitly.
    """
    from cua_s1.driver import BaseDriver, DriverError
    from cua_s1.planner import Planner, PlannerError, order_decisions, run_form

    class VerifiedDriver(BaseDriver):
        def __init__(self, wrapped: Any) -> None:
            super().__init__()
            self.wrapped = wrapped
            self.timings = wrapped.timings
            self.elements_by_token: dict[str, Any] = {}

        def window_state(self, window: Any) -> Any:
            snapshot = self.wrapped.window_state(window)
            if execute:
                snapshot.require_executable()
            self.elements_by_token = {
                element.element_token: element
                for element in snapshot.elements
                if element.element_token
            }
            return snapshot

        def supports_value_mutation(self) -> bool:
            return self.wrapped.supports_value_mutation()

        def set_value(self, window: Any, token: str, value: str) -> Any:
            original = self.elements_by_token[token]
            mutation = self.wrapped.set_value(window, token, value)
            if mutation.action.get("effect") != "confirmed":
                return mutation
            current = mutation.observation.element_for(original)
            if current.value != value:
                raise DriverError(
                    "fill_postcondition_failed",
                    "The observed field value does not match the requested value",
                    tool="set_value",
                    details={"element_index": original.index},
                    outcome_unknown=True,
                )
            self.elements_by_token = {
                element.element_token: element
                for element in mutation.observation.elements if element.element_token
            }
            return mutation

        def click(self, window: Any, token: str, *, delivery_mode: str) -> Any:
            mutation = self.wrapped.click(window, token, delivery_mode=delivery_mode)
            self.elements_by_token = {
                element.element_token: element
                for element in mutation.observation.elements if element.element_token
            }
            return mutation

    class PreflightBackend:
        def __init__(self, scorer: Any, wrapped: Any) -> None:
            self.scorer = scorer
            self.wrapped = wrapped

        def plan(self, title: str, elements: list[Any], values: list[Any]) -> list[Any]:
            decisions = self.scorer.plan(title, elements, values)
            if execute:
                ordered = order_decisions(decisions, min_confidence, allow_submit=submit)
                if any(item.action == "fill" for item in ordered) and not self.wrapped.supports_value_mutation():
                    raise PlannerError(
                        "unsupported_driver_capability",
                        "The connected driver does not advertise token-based value mutation",
                        capability="set_value",
                    )
                missing = [item.element.index for item in ordered if not item.element.element_token]
                if missing:
                    raise PlannerError("element_token_missing", "Planned actions lack snapshot-bound tokens", indices=missing)
            return decisions

    try:
        scorer = backend if backend is not None else ModelBackend(checkpoint, device)
        report = run_form(
            Planner(PreflightBackend(scorer, driver)), VerifiedDriver(driver), entities,
            target=target, form_title=form_title, min_confidence=min_confidence,
            execute=execute, submit=submit, delivery_mode=delivery_mode,
        )
        return {"ok": not report["stopped_after_error"], **report}
    except (PlannerError, DriverError) as exc:
        return {"ok": False, "error": exc.to_dict(), "execution_order": []}
    except (OSError, ValueError, RuntimeError) as exc:
        return {"ok": False, "error": {"code": "model_error", "message": str(exc)}, "execution_order": []}


def score(request: dict[str, Any], checkpoint: Path, device: str = "auto") -> dict[str, Any]:
    """Return one probability per supplied choice, preserving their order."""
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    context = request.get("context")
    options = request.get("options")
    if not isinstance(context, str) or not context.strip():
        raise ValueError("context must be a non-empty string")
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError("options must contain at least two strings")
    if any(not isinstance(option, str) or not option.strip() for option in options):
        raise ValueError("every option must be a non-empty string")
    if len(set(options)) != len(options):
        raise ValueError("options must be distinct")

    from cua_s1.model import ChoiceExample, load_checkpoint, select_device
    import torch

    model, collator, config = load_checkpoint(checkpoint, select_device(device))
    batch = collator([ChoiceExample(context, tuple(options), 0)])
    target = next(model.parameters()).device
    batch = {key: value.to(target) for key, value in batch.items()}
    with torch.inference_mode():
        probabilities = model(batch).softmax(dim=-1)[0, : len(options)].tolist()
    choices = [
        {"index": index, "option": option, "probability": probability}
        for index, (option, probability) in enumerate(zip(options, probabilities))
    ]
    winner = max(choices, key=lambda choice: choice["probability"])
    return {
        "model": "cua-ai/cua-s1-forms",
        "selected_index": winner["index"],
        "choices": choices,
        "device": str(target),
        "context_tokens": config["context_tokens"],
        "option_tokens": config["option_tokens"],
        "executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True, help="Official .safetensors file with matching .json sidecar")
    parser.add_argument("--input", type=Path, help="JSON request file; stdin when omitted")
    parser.add_argument("--device", default="auto", help="PyTorch device (default: auto)")
    args = parser.parse_args(argv)
    try:
        content = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        result = score(json.loads(content), args.checkpoint, args.device)
    except (OSError, ValueError, ImportError, RuntimeError, KeyError) as exc:
        print(f"cua-s1-forms: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
