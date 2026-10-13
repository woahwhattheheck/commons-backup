"""Compare exported logits to the official PyTorch checkpoint on varied forms."""

import os
import unittest
from pathlib import Path

from host.cua_s1_cloud.export_onnx import INPUTS, pad_batch
from host.cua_s1_cloud.runtime_onnx import collate


class OnnxParityTests(unittest.TestCase):
    def test_logits_and_choice_parity(self):
        import onnxruntime as ort
        import torch
        from cua_s1.model import ChoiceExample, load_checkpoint

        checkpoint = os.environ.get("CUA_S1_CHECKPOINT")
        if not checkpoint:
            self.skipTest("Set CUA_S1_CHECKPOINT to the official safetensors file")
        model, collator, _config = load_checkpoint(Path(checkpoint), "cpu")
        session = ort.InferenceSession("host/cua_s1_cloud/cua-s1-forms.onnx",
                                       providers=["CPUExecutionProvider"])
        cases = [
            ("ELEMENT Edit Phone value empty", ("fill 555-0142", "skip")),
            ("ELEMENT CheckBox I agree checked false", ("check", "skip", "click")),
            ("TASK fill user form\nELEMENT Edit E-mail", ("fill a@example.com", "fill other", "skip", "click")),
            ("α" * 150 + "🙂" * 20, ("fill " + "é" * 55, "skip")),
            ("TASK review\n" + "A" * 220, ("fill " + "🙂" * 30, "click", "check", "skip")),
            ("ELEMENT Edit \ud800 replacement", ("fill \ud800", "skip")),
            ("ELEMENT Edit Multiple choices", tuple(f"fill candidate {i}" for i in range(29)) + ("check", "click", "skip")),
        ]
        for context, options in cases:
            with self.subTest(context=context):
                batch = collator([ChoiceExample(context, options, 0)])
                padded = pad_batch(batch)
                hosted = collate(context, list(options))
                for name in INPUTS:
                    self.assertEqual(hosted[name].tolist(), padded[name].numpy().tolist())
                with torch.inference_mode():
                    expected = model(batch).numpy()
                actual = session.run(["logits"], {name: padded[name].numpy() for name in INPUTS})[0][:, :len(options)]
                self.assertEqual(actual.argmax(axis=1).tolist(), expected.argmax(axis=1).tolist())
                self.assertLess(abs(actual - expected).max(), 0.001)


if __name__ == "__main__":
    unittest.main()
