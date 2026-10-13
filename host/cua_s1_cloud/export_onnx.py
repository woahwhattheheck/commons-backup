"""Export the pinned official checkpoint to portable ONNX logits."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from cua_s1.model import ChoiceExample, load_checkpoint
from torch import nn

from host.cua_s1_cloud.server import ensure_checkpoint


INPUTS = ("context_ids", "context_mask", "option_ids", "option_mask", "option_token_mask")
MAX_CONTEXT = 224
MAX_OPTIONS = 32
MAX_OPTION_TOKENS = 96


def pad_batch(batch):
    """Pad official collator output to one static shape for reliable ONNX export."""
    if (batch["context_ids"].shape[1] > MAX_CONTEXT or
            batch["option_ids"].shape[1] > MAX_OPTIONS or
            batch["option_ids"].shape[2] > MAX_OPTION_TOKENS):
        raise ValueError("input exceeds fixed ONNX dimensions")
    outputs = {}
    for name, shape in {
        "context_ids": (1, MAX_CONTEXT), "context_mask": (1, MAX_CONTEXT),
        "option_ids": (1, MAX_OPTIONS, MAX_OPTION_TOKENS),
        "option_mask": (1, MAX_OPTIONS),
        "option_token_mask": (1, MAX_OPTIONS, MAX_OPTION_TOKENS),
    }.items():
        source = batch[name]
        target = torch.zeros(shape, dtype=source.dtype)
        slices = tuple(slice(0, width) for width in source.shape)
        target[slices] = source
        outputs[name] = target
    return outputs


class Forward(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, context_ids, context_mask, option_ids, option_mask, option_token_mask):
        return self.model(dict(zip(INPUTS, (context_ids, context_mask, option_ids,
                                            option_mask, option_token_mask))))


def export(checkpoint: Path, output: Path) -> None:
    # Disable PyTorch's fused inference op, which has no ONNX symbolic.
    torch.backends.mha.set_fastpath_enabled(False)
    model, collator, _config = load_checkpoint(checkpoint, "cpu")
    sample = pad_batch(collator([ChoiceExample("ELEMENT Edit Phone", ("fill 555-0142", "skip"), 0)]))
    wrapped = Forward(model).eval()
    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        torch.onnx.export(
            wrapped, tuple(sample[name] for name in INPUTS), str(output),
            input_names=list(INPUTS), output_names=["logits"], opset_version=17,
            dynamo=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, default=Path("host/cua_s1_cloud/cua-s1-forms.onnx"))
    args = parser.parse_args()
    export(args.checkpoint or ensure_checkpoint(Path(".cache/cua-s1-forms")), args.output)


if __name__ == "__main__":
    main()
