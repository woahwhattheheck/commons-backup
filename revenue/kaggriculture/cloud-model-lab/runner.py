"""LiteRT-LM runner: fixed checkpoint, backend, sampler and state, with real counters.

Everything that could move between arms is pinned here so the operator surface is
the only variable: the same engine instance, the same backend, the same sampler,
the same max_num_tokens, thinking disabled, one fresh conversation per card so no
arm inherits another's KV state.

Counters come from the engine's own BenchmarkInfo (init time, time to first token,
prefill/decode token counts and rates). Where a counter is not populated it is
recorded as None and stays unknown -- never estimated.
"""

import json
import time

MODEL_SHA256 = "0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0"
MODEL_BYTES = 3659530240

# Measured on litert-lm 0.16.1: a loose JSON schema whose array `items` are
# unconstrained does NOT bind the content -- the model emitted
# {"farmer":[{"name":"Farmer Giles", ...}]}, valid against the schema and useless.
# The regex format over the exact turn grammar binds op names, arity and nesting,
# so that is what the codec arm uses. The schema is kept for the A/B.


def _response_text(resp):
    """send_message returns {'role':..., 'content':[{'type':'text','text':...}, ...]}."""
    if isinstance(resp, str):
        return resp
    if hasattr(resp, "texts") and resp.texts:
        return "".join(resp.texts)
    content = resp.get("content") if isinstance(resp, dict) else None
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        if parts:
            return "".join(parts)
    if isinstance(content, str):
        return content
    return str(resp)


class Runner:
    def __init__(self, model_path, max_num_tokens=4096, temperature=0.0, top_k=1,
                 seed=0, thinking=False, max_output_tokens=192):
        import litert_lm as L
        self.L = L
        self.model_path = model_path
        self.cfg = {
            "backend": "CPU",
            "max_num_tokens": max_num_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "sampler_seed": seed,
            "thinking": thinking,
            "max_output_tokens": max_output_tokens,
            "model_sha256": MODEL_SHA256,
        }
        t0 = time.perf_counter()
        self.engine = L.Engine(
            model_path,
            backend=L.Backend.CPU(),
            max_num_tokens=max_num_tokens,
            enable_benchmark=True,
        )
        self.cold_load_s = time.perf_counter() - t0
        self.sampler = L.SamplerConfig(top_k=top_k, temperature=temperature, seed=seed)
        self.thinking_cfg = L.ThinkingConfig(enable_thinking=thinking)
        self.max_output_tokens = max_output_tokens

    def _bench(self, conv):
        try:
            b = conv.get_benchmark_info()
        except Exception:
            return {}
        out = {}
        for f in ("init_time_in_second", "time_to_first_token_in_second",
                  "last_prefill_token_count", "last_prefill_tokens_per_second",
                  "last_decode_token_count", "last_decode_tokens_per_second"):
            v = getattr(b, f, None)
            out[f] = v
        return out

    def ask(self, text, constrained=False, binder="regex"):
        """One fresh-conversation decision. Returns the exact input, output and counters."""
        L = self.L
        kwargs = dict(sampler_config=self.sampler, thinking_config=self.thinking_cfg,
                      max_output_tokens=self.max_output_tokens)
        if constrained:
            # response_format is refused unless the provider is LL_GUIDANCE explicitly;
            # enable=True alone raises. Measured against litert-lm 0.16.1.
            kwargs["constrained_decoding_config"] = L.ConstrainedDecodingConfig(
                enable=True, provider=L.LiteRtLmConstraintProviderType.LL_GUIDANCE)
        conv = self.engine.create_conversation(**kwargs)
        rf = None
        if constrained:
            import codec
            rf = (L.ResponseFormat.regex(codec.turn_regex()) if binder == "regex"
                  else L.ResponseFormat.json(codec.TIGHT_SCHEMA))
        t0 = time.perf_counter()
        try:
            if rf is not None:
                resp = conv.send_message(text, response_format=rf)
            else:
                resp = conv.send_message(text)
            wall = time.perf_counter() - t0
            out = _response_text(resp)
            err = None
        except Exception as exc:
            wall = time.perf_counter() - t0
            out, err = "", f"{type(exc).__name__}: {exc}"
        bench = self._bench(conv)
        try:
            tok = conv.token_count
        except Exception:
            tok = None
        try:
            conv.close()
        except Exception:
            pass
        return {"input": text, "output": out, "error": err, "wall_s": wall,
                "token_count": tok, "benchmark": bench,
                "constrained": (binder if constrained else False)}

    def ask_regex(self, text, pattern):
        """Decode bound to an explicit regex -- used for the per-card admissible grammar."""
        L = self.L
        conv = self.engine.create_conversation(
            sampler_config=self.sampler, thinking_config=self.thinking_cfg,
            max_output_tokens=self.max_output_tokens,
            constrained_decoding_config=L.ConstrainedDecodingConfig(
                enable=True, provider=L.LiteRtLmConstraintProviderType.LL_GUIDANCE))
        t0 = time.perf_counter()
        try:
            resp = conv.send_message(text, response_format=L.ResponseFormat.regex(pattern))
            wall = time.perf_counter() - t0
            out, err = _response_text(resp), None
        except Exception as exc:
            wall = time.perf_counter() - t0
            out, err = "", f"{type(exc).__name__}: {exc}"
        bench = self._bench(conv)
        try:
            conv.close()
        except Exception:
            pass
        return {"input": text, "output": out, "error": err, "wall_s": wall,
                "token_count": None, "benchmark": bench, "constrained": "card_regex"}

    def tokenize_len(self, text):
        try:
            return len(self.engine.tokenize(text))
        except Exception:
            return None

    def close(self):
        try:
            self.engine.close()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", default="Reply with exactly: OK")
    ap.add_argument("--constrained", action="store_true")
    a = ap.parse_args()
    r = Runner(a.model)
    print(f"cold_load_s={r.cold_load_s:.2f}")
    res = r.ask(a.prompt, constrained=a.constrained)
    print(json.dumps({k: v for k, v in res.items() if k != "input"}, indent=1, default=str))
    r.close()
