#!/usr/bin/env python3
"""host/hf_export.py — make Titan's file HuggingFace-COMPATIBLE (owner 07-13).

Step 1 (this): emit a standard HF `config.json` from a GGUF's architecture metadata, so the SGS artifact reads as a
HuggingFace model (AutoConfig / AutoModel.from_pretrained, benchmarkable vs other LLMs). Step 2 (next): dequant the
curated tensor set -> `model.safetensors` + copy the tokenizer = a fully loadable HF model. Proves the GGUF->HF path on
Titan's own material. The SGM runtime (per-tick model assembly, INV-139) builds FROM this static, standard artifact.

Usage:  python host/hf_export.py <model.gguf> [out_dir]
"""
import json, os, sys
from gguf import GGUFReader


def scalar(r, key, default=None):
    """Read a scalar metadata value from a GGUF field."""
    f = r.fields.get(key)
    if f is None:
        return default
    try:
        v = f.parts[f.data[0]]
        v = v.tolist() if hasattr(v, "tolist") else v
        return v[0] if isinstance(v, list) and len(v) == 1 else v
    except Exception:
        return default


def gstr(r, key, default=""):
    """Read a string metadata value from a GGUF field."""
    f = r.fields.get(key)
    if f is None:
        return default
    try:
        return bytes(f.parts[f.data[-1]]).decode("utf-8", "replace")
    except Exception:
        return default


def gguf_to_hf_config(path):
    r = GGUFReader(path)
    a = gstr(r, "general.architecture", "llama")           # the arch prefix for arch-specific keys
    tok = r.fields.get("tokenizer.ggml.tokens")
    n_vocab = len(tok.data) if tok is not None else scalar(r, f"{a}.vocab_size")
    return {
        "architectures": [a[:1].upper() + a[1:] + "ForCausalLM"],
        "model_type": a,
        "hidden_size": scalar(r, f"{a}.embedding_length"),
        "num_hidden_layers": scalar(r, f"{a}.block_count"),
        "num_attention_heads": scalar(r, f"{a}.attention.head_count"),
        "num_key_value_heads": scalar(r, f"{a}.attention.head_count_kv"),
        "intermediate_size": scalar(r, f"{a}.feed_forward_length"),
        "max_position_embeddings": scalar(r, f"{a}.context_length"),
        "rms_norm_eps": scalar(r, f"{a}.attention.layer_norm_rms_epsilon", 1e-5),
        "rope_theta": scalar(r, f"{a}.rope.freq_base", 10000.0),
        "vocab_size": n_vocab,
        "bos_token_id": scalar(r, "tokenizer.ggml.bos_token_id"),
        "eos_token_id": scalar(r, "tokenizer.ggml.eos_token_id"),
        "torch_dtype": "float16",
        "transformers_version": "4.44.0",
        "_titan": "exported from GGUF by host/hf_export.py; the SGM runtime builds per-tick models from this artifact",
    }


def main():
    if len(sys.argv) < 2:
        print("usage: python host/hf_export.py <model.gguf> [out_dir]"); return
    path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(path))[0] + "_hf"
    cfg = gguf_to_hf_config(path)
    os.makedirs(out, exist_ok=True)
    json.dump(cfg, open(os.path.join(out, "config.json"), "w"), indent=2)
    print(f"wrote {out}/config.json:\n" + json.dumps(cfg, indent=2))
    ok = all(cfg[k] for k in ("hidden_size", "num_hidden_layers", "num_attention_heads", "vocab_size"))
    print(f"\nHF config valid (core fields present): {ok}")
    print("[next] dequant the curated tensors -> model.safetensors + copy the tokenizer = a loadable HF model.")


if __name__ == "__main__":
    main()
