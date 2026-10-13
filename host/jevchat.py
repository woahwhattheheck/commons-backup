#!/usr/bin/env python3
"""host/jevchat.py — JEVCHAT: external autoregression experiment over Jev.

Work order JEVCHAT-EXTERNAL-AUTOREGRESSION (#build-demand 2026-09-17,
spec owner Z / GPT-5.6 Sol, implementer DEVIN local SWE-2).

Question under test: can repeated Jev `choice` decisions manufacture
autoregressive text externally?  prefix -> choose next symbol -> append ->
repeat, one API call per symbol, streamed like chat.  Jev emits a typed
choice over a fixed alphabet; the wrapper maps safe ids back to exact bytes.
Jev never emits arbitrary strings — that is the scientific guard.

Baseline alphabet `char-v1`: printable ASCII 0x20-0x7E + \\n + \\t + EOS
(98 options < 255).  `chunk-v1` adds a small deterministic common-chunk set
for the post-baseline ablation — never overwrite char-v1 results.

  python3 host/jevchat.py --prompt "Return exactly: OK" --max-chars 16 \
      --trace traces/jevchat-a.jsonl
  echo "Say hello" | python3 host/jevchat.py --prompt -
  python3 host/jevchat.py --self-test   (engine shape only; tests live in
      host/test_jevchat.py)

Stdout receives the generated text as it arrives; diagnostics go to stderr
and step rows to the JSONL trace.  Stop reasons are distinct and typed:
EOS_EMITTED, MAX_CHARS, STATE_TOO_LARGE, CONFIDENCE_FLOOR, BAD_CHOICE,
NO_KEY, HTTP_<status>, TRANSPORT, BAD_REPLY, EMPTY_STATE.  No key material
or Authorization header is ever written to the trace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402

QUESTION_KEY = "next"
EOS_ID = "eos"
MAX_CHARS_DEFAULT = 512
MAX_CHARS_HARD = 8192
MAX_STEPS_HARD = 8192

SYMBOL_NAMES = {
    " ": "space", "\n": "newline", "\t": "tab", "!": "exclamation mark",
    '"': "double quote", "#": "hash", "$": "dollar sign", "%": "percent",
    "&": "ampersand", "'": "single quote", "(": "left paren",
    ")": "right paren", "*": "asterisk", "+": "plus", ",": "comma",
    "-": "hyphen-minus", ".": "period", "/": "forward slash",
    ":": "colon", ";": "semicolon", "<": "less-than", "=": "equals sign",
    ">": "greater-than", "?": "question mark", "@": "at sign",
    "[": "left bracket", "\\": "backslash", "]": "right bracket",
    "^": "caret", "_": "underscore", "`": "backtick", "{": "left brace",
    "|": "pipe", "}": "right brace", "~": "tilde",
}

COMMON_CHUNKS = [
    "the", " be", " to", " of", " and", " a ", " in", " that", " have",
    " I ", " it", " for", " not", " on", " with", " he", " as", " you",
    " do", " at", " this", " but", " his", " by", " from", " they",
    " we", " say", " her", " she", " or", " an", " will", " my", " one",
    " all", " would", " there", " their", "ing", "ion", "er", "ent",
    "The ", " is ", " are ", ". ", ", ",
]

STATE_TEMPLATE = (
    "SYSTEM-ONE EXTERNAL AUTOREGRESSION EXPERIMENT\n"
    "A text answer is being generated one symbol at a time by repeated "
    "typed decisions. The USER prompt is exact and immutable. "
    "ASSISTANT_PREFIX contains exactly the symbols emitted so far; nothing "
    "is repaired, truncated, or hidden.\n\n"
    "USER:\n{prompt}\n\n"
    "ASSISTANT_PREFIX:\n{prefix}\n"
)

INSTRUCTIONS = {
    "char-v1": (
        "Which single next symbol should be appended to ASSISTANT_PREFIX to "
        "continue the most coherent and helpful answer to USER? Choose "
        "'eos' only when the answer is complete."
    ),
    "chunk-v1": (
        "Which next symbol or common chunk should be appended to "
        "ASSISTANT_PREFIX to continue the most coherent and helpful answer "
        "to USER? Choose 'eos' only when the answer is complete."
    ),
}


def _describe(symbol):
    codepoints = " ".join(f"U+{ord(c):04X}" for c in symbol)
    name = SYMBOL_NAMES.get(symbol)
    shown = name if name else repr(symbol)
    return f"append {shown} ({codepoints})"


def build_alphabet(version="char-v1"):
    """Return ordered [(safe_id, symbol|None, description)]. symbol None = EOS."""
    entries = []
    for idx, code in enumerate(range(0x20, 0x7F)):
        ch = chr(code)
        entries.append((f"c{idx:03d}", ch, _describe(ch)))
    n = len(entries)
    entries.append((f"c{n:03d}", "\n", _describe("\n")))
    entries.append((f"c{n + 1:03d}", "\t", _describe("\t")))
    if version == "chunk-v1":
        for i, chunk in enumerate(COMMON_CHUNKS):
            entries.append((f"k{i:03d}", chunk, _describe(chunk)))
    elif version != "char-v1":
        raise ValueError("unknown alphabet " + str(version))
    entries.append((EOS_ID, None, "emit nothing — the answer is complete"))
    return entries


class Alphabet:
    """Stable reversible id<->symbol map for one alphabet version."""

    def __init__(self, version="char-v1"):
        self.version = version
        self.entries = build_alphabet(version)
        self.by_id = {e[0]: e for e in self.entries}
        if len(self.by_id) != len(self.entries):
            raise ValueError("duplicate alphabet ids")
        if len(self.entries) > 255:
            raise ValueError("alphabet exceeds 255 options")
        self.by_symbol = {e[1]: e[0] for e in self.entries if e[1] is not None}

    def criteria(self):
        return {e[0]: e[2] for e in self.entries}

    def encode(self, symbol):
        return self.by_symbol.get(symbol)

    def decode(self, choice_id):
        """-> (symbol|None, is_eos). Raises KeyError on unknown id."""
        entry = self.by_id[choice_id]
        return entry[1], entry[0] == EOS_ID


def build_state(prompt, prefix):
    return STATE_TEMPLATE.format(prompt=prompt, prefix=prefix)


def state_sha256(state):
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


class Trace:
    """Append-only JSONL step log. Never stores keys or auth headers."""

    def __init__(self, path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8") if path else None

    def row(self, **fields):
        if self._fh:
            self._fh.write(json.dumps(fields, ensure_ascii=False) + "\n")
            self._fh.flush()

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None


def generate(prompt, *, alphabet="char-v1", model=jev.DEFAULT_MODEL,
             max_chars=MAX_CHARS_DEFAULT, timeout=60, confidence_floor=None,
             trace_path=None, record_prompt=False, systemone=None,
             on_symbol=None):
    """Run the baseline loop. Returns a dict: text, stop_reason, steps, usage."""
    call = systemone or jev.systemone
    alpha = Alphabet(alphabet)
    criteria = alpha.criteria()
    questions = {
        QUESTION_KEY: {
            "type": "choice",
            "instructions": INSTRUCTIONS[alphabet],
            "criteria": criteria,
        }
    }
    prefix = ""
    steps = 0
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    stop_reason = None
    trace = Trace(trace_path)
    started = time.monotonic()
    try:
        while True:
            state = build_state(prompt, prefix)
            if len(state.encode("utf-8")) > jev.MAX_STATE_BYTES:
                stop_reason = "STATE_TOO_LARGE"
                break
            if steps >= MAX_STEPS_HARD or len(prefix) >= max_chars:
                stop_reason = "MAX_CHARS"
                break
            t0 = time.monotonic()
            try:
                resp = call(state, questions, model=model, timeout=timeout)
            except jev.JevError as err:
                stop_reason = str(err)
                break
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            answers = (resp or {}).get("answers") or {}
            raw = answers.get(QUESTION_KEY) or {}
            choice_id = raw.get("choice")
            confidence = raw.get("confidence")
            usage = resp.get("usage") or {}
            for k in usage_total:
                usage_total[k] += int(usage.get(k) or 0)
            row = {
                "type": "step", "step": steps, "prefix_len": len(prefix),
                "choice_id": choice_id, "confidence": confidence,
                "elapsed_ms": elapsed_ms, "raw": raw, "usage": usage,
                "state_sha256": state_sha256(state),
            }
            if choice_id is None or choice_id not in alpha.by_id:
                row["stop_reason"] = "BAD_CHOICE"
                trace.row(**row)
                stop_reason = "BAD_CHOICE"
                break
            symbol, is_eos = alpha.decode(choice_id)
            if is_eos:
                row.update({"symbol": None, "symbol_repr": "EOS",
                            "codepoint": None, "stop_reason": "EOS_EMITTED"})
                trace.row(**row)
                stop_reason = "EOS_EMITTED"
                break
            row.update({"symbol": symbol, "symbol_repr": repr(symbol),
                        "codepoint": " ".join(f"U+{ord(c):04X}" for c in symbol)})
            if confidence_floor is not None and (
                confidence is None or confidence < confidence_floor
            ):
                row["stop_reason"] = "CONFIDENCE_FLOOR"
                trace.row(**row)
                stop_reason = "CONFIDENCE_FLOOR"
                break
            trace.row(**row)
            prefix += symbol
            steps += 1
            if on_symbol:
                on_symbol(symbol)
    finally:
        summary = {
            "type": "summary",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "model": model, "alphabet": alphabet, "chars": len(prefix),
            "steps": steps, "total_ms": round((time.monotonic() - started) * 1000),
            "stop_reason": stop_reason or "MAX_CHARS", "usage": usage_total,
        }
        if record_prompt:
            summary["prompt"] = prompt
        trace.row(**summary)
        trace.close()
    return {
        "text": prefix, "stop_reason": stop_reason or "MAX_CHARS",
        "steps": steps, "usage": usage_total, "alphabet": alphabet,
        "model": model,
    }


def self_test():
    alpha = Alphabet()
    return {
        "alphabet": alpha.version,
        "options": len(alpha.entries),
        "under_255": len(alpha.entries) < 255,
        "ids_unique": len(alpha.by_id) == len(alpha.entries),
        "reversible_A": alpha.decode(alpha.encode("A"))[0] == "A",
        "eos_id": EOS_ID,
        "state_template_bytes": len(STATE_TEMPLATE.encode("utf-8")),
        "key_state": jev.key_state(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Jev external autoregression")
    parser.add_argument("--prompt", help="prompt text, '-' for stdin")
    parser.add_argument("--prompt-file")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS_DEFAULT)
    parser.add_argument("--model", default=jev.DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--trace", help="append-only JSONL trace path")
    parser.add_argument("--confidence-floor", type=float, default=None)
    parser.add_argument("--alphabet", default="char-v1",
                        choices=["char-v1", "chunk-v1"])
    parser.add_argument("--record-prompt", action="store_true",
                        help="store prompt text in the trace summary (hash "
                             "is always stored)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0

    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8", errors="replace") as fh:
            prompt = fh.read()
    elif args.prompt == "-":
        prompt = sys.stdin.read()
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        print("jevchat: provide --prompt or --prompt-file", file=sys.stderr)
        return 2
    if args.max_chars > MAX_CHARS_HARD:
        print(f"jevchat: --max-chars hard cap is {MAX_CHARS_HARD}",
              file=sys.stderr)
        return 2

    def emit(sym):
        sys.stdout.write(sym)
        sys.stdout.flush()

    result = generate(
        prompt, alphabet=args.alphabet, model=args.model,
        max_chars=args.max_chars, timeout=args.timeout,
        confidence_floor=args.confidence_floor, trace_path=args.trace,
        record_prompt=args.record_prompt, on_symbol=emit,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    print(json.dumps({"stop_reason": result["stop_reason"],
                      "chars": len(result["text"]), "steps": result["steps"],
                      "alphabet": result["alphabet"], "model": result["model"],
                      "usage": result["usage"]}), file=sys.stderr)
    return 0 if result["stop_reason"] in ("EOS_EMITTED", "MAX_CHARS") else 2


if __name__ == "__main__":
    sys.exit(main())
