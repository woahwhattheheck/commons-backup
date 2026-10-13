#!/usr/bin/env python3
"""Lambda-shaped adapter. Source exists; no AWS deployment or account authority is implied."""
from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np

from visual_gate import GateError, compile_trace

MAX_ENCODED = 8_000_000


def handler(event: Any, context: Any = None) -> dict[str, Any]:
    if not isinstance(event, dict) or set(event) != {"image_base64", "observed_ms", "now_ms", "requested_action_class"}:
        return {"statusCode": 400, "body": {"error": "INVALID_EVENT"}}
    raw64 = event["image_base64"]
    if not isinstance(raw64, str) or not raw64 or len(raw64) > MAX_ENCODED:
        return {"statusCode": 400, "body": {"error": "INVALID_IMAGE"}}
    try:
        raw = base64.b64decode(raw64, validate=True)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise GateError("decode failed")
        receipt = compile_trace(
            image,
            observed_ms=event["observed_ms"],
            now_ms=event["now_ms"],
            requested_action_class=event["requested_action_class"],
        )
    except (ValueError, TypeError, GateError):
        return {"statusCode": 400, "body": {"error": "INVALID_IMAGE_OR_INPUT"}}
    return {
        "statusCode": 200,
        "body": receipt,
        "aws_truth": {
            "handler_source_present": True,
            "deployment_evidenced": False,
            "cloudwatch_evidenced": False,
            "stepfunctions_evidenced": False,
        },
    }
