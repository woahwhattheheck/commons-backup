"""Optional AWS Bedrock backend for SpoilerShield.

The Fire TV app remains functional without this service.  If BEDROCK_MODEL_ID is
set, the handler uses Bedrock Converse; otherwise it returns a deterministic
answer.  The server independently re-checks the no-future timestamp boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

PACKET_VERSION = "spoilershield/context-v1"
QUESTION_KINDS = {"WHO", "WHY", "CATCH_UP"}


def _canonical(value: Any) -> str:
    if value is None or isinstance(value, (bool, str)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("integer outside JavaScript safe range")
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _canonical(value[k])
            for k in sorted(value)
        ) + "}"
    raise ValueError("unsupported canonical value")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_string(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError(f"invalid {name}")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError(f"control character in {name}")
    return value


def validate_packet(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("packet must be object")
    if packet.get("version") != PACKET_VERSION:
        raise ValueError("unsupported packet version")
    position_ms = packet.get("positionMs")
    if not isinstance(position_ms, int) or isinstance(position_ms, bool) or not (0 <= position_ms <= 86_400_000):
        raise ValueError("invalid positionMs")
    question = packet.get("questionKind")
    if question not in QUESTION_KINDS:
        raise ValueError("invalid questionKind")
    transcript_sha = packet.get("transcriptSha256")
    if not isinstance(transcript_sha, str) or len(transcript_sha) != 64 or any(c not in "0123456789abcdef" for c in transcript_sha):
        raise ValueError("invalid transcriptSha256")
    pinned = os.getenv("ALLOWED_TRANSCRIPT_SHA256", "").strip()
    if pinned and transcript_sha != pinned:
        raise ValueError("transcript generation is not allowed")

    context = packet.get("context")
    if not isinstance(context, list) or len(context) > 8:
        raise ValueError("invalid context")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    prior_start = -1
    for raw in context:
        if not isinstance(raw, dict):
            raise ValueError("cue must be object")
        cue_id = _validate_string("cue id", raw.get("id"), 80)
        speaker = _validate_string("speaker", raw.get("speaker"), 80)
        text = _validate_string("text", raw.get("text"), 600)
        start = raw.get("startMs")
        end = raw.get("endMs")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError("cue timestamps must be integers")
        if start < 0 or end <= start or end > position_ms:
            raise ValueError("future cue crosses spoiler boundary")
        if start < prior_start:
            raise ValueError("cue order is not monotone")
        prior_start = start
        if cue_id in seen:
            raise ValueError("duplicate cue id")
        seen.add(cue_id)
        clean.append({"id": cue_id, "startMs": start, "endMs": end, "speaker": speaker, "text": text})

    max_end = max((cue["endMs"] for cue in clean), default=0)
    if packet.get("maxCueEndMs") != max_end:
        raise ValueError("maxCueEndMs mismatch")
    signed = {
        "version": PACKET_VERSION,
        "positionMs": position_ms,
        "questionKind": question,
        "transcriptSha256": transcript_sha,
        "context": clean,
    }
    if packet.get("contextSha256") != _sha256(_canonical(signed)):
        raise ValueError("context digest mismatch")
    return {**signed, "maxCueEndMs": max_end, "contextSha256": packet["contextSha256"]}


def _clock(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def offline_answer(packet: dict[str, Any]) -> str:
    ctx = packet["context"]
    if not ctx:
        return "Nothing completed yet — ask again after the first line."
    if packet["questionKind"] == "WHO":
        cue = ctx[-1]
        return f"{cue['speaker']} is the most recent speaker you have reached. Last known context: “{cue['text']}”"
    if packet["questionKind"] == "WHY":
        recent = ctx[-3:]
        return "Why this matters so far: " + " • ".join(f"{cue['speaker']}: {cue['text']}" for cue in recent)
    return f"Catch-up through {_clock(packet['positionMs'])}: " + " ".join(cue["text"] for cue in ctx[-5:])


def _bedrock_answer(packet: dict[str, Any]) -> str:
    model_id = os.getenv("BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        return offline_answer(packet)
    import boto3  # imported only when the optional cloud path is configured

    context_text = "\n".join(
        f"[{_clock(cue['endMs'])}] {cue['speaker']}: {cue['text']}" for cue in packet["context"]
    )
    instruction = (
        "You are SpoilerShield, a television co-viewing context assistant. "
        "Use ONLY the supplied completed transcript cues. Never use outside plot knowledge, "
        "future scenes, franchise memory, or web knowledge. If evidence is insufficient, say so. "
        f"Viewer playhead: {_clock(packet['positionMs'])}. Question mode: {packet['questionKind']}. "
        "Answer in at most 70 words for a television screen."
    )
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=model_id,
        system=[{"text": instruction}],
        messages=[{"role": "user", "content": [{"text": context_text or "No completed cues."}]}],
        inferenceConfig={"maxTokens": 180, "temperature": 0.0},
    )
    text = response["output"]["message"]["content"][0]["text"].strip()
    if not text:
        raise RuntimeError("empty Bedrock answer")
    return text


def _response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
    }


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        raw_body = event.get("body", event)
        packet = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        # Browser app may send a human-readable instruction field. It is never trusted;
        # only the canonical packet fields below drive validation and model prompting.
        if isinstance(packet, dict):
            packet = {k: v for k, v in packet.items() if k != "instruction"}
        clean = validate_packet(packet)
        answer = _bedrock_answer(clean)
        return _response(200, {
            "version": PACKET_VERSION,
            "mode": "bedrock" if os.getenv("BEDROCK_MODEL_ID", "").strip() else "offline",
            "answer": answer,
            "contextSha256": clean["contextSha256"],
            "maxCueEndMs": clean["maxCueEndMs"],
        })
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _response(400, {"error": "INVALID_CONTEXT", "detail": str(exc)})
    except Exception:
        # Do not leak provider internals; the client can fail safely to its local provider.
        return _response(503, {"error": "MODEL_UNAVAILABLE"})
