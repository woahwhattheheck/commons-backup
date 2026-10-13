#!/usr/bin/env python3
"""host/devour.py — DEVOUR: Titan eats ANY file or text (INCLUDING models) INTO its own weights, reversibly.

Owner's spec (07-14, tightened): devour "should allow you to put source into the text field and it will be devoured
meaning put into titan's digital storage; once it's in the weights it can generate it precisely", "devour should be able
to eat models too", "any file type or text", and — the binding constraint — "ALL features should be accomplished via
WEIGHT MODIFICATION using the white box". So devour is NOT a sidecar store and NOT context injection (both rejected): it
is a reversible WHITE-BOX WEIGHT EDIT to Titan's own model file (`host/wbedit.py`, genome-journaled byte edits → byte-exact
undo). The only sidecar is the genome (the reversal). This is the EXTEND leg of the bare-file computer (TITAN_SYSTEM §1.6
INV-146 / §5): spend now to write a component into the weights so future generation is cheap.

Routes by type, every route ending in a reversible wbedit weight edit into `TITAN`:
  - MODEL (.gguf/.safetensors) → blend every COMPATIBLE tensor (same name+shape) toward Titan's → Titan ABSORBS its params
    (`wbedit.blend_tensor`, proven byte-exact reversible). "Eat a model."
  - CODE / TEXT / IMAGE / APK / any file or pasted text → STUDY it in: extract the salient concept tokens and nudge the
    corresponding embedding rows toward the content's meaning (`wbedit.edit_token`, reversible). Honest scope: this writes
    the content's CONCEPTS into the weights now; precise lossless recall of a large arbitrary program is the depth of the
    bake KEYSTONE (task #49) — the mechanism (reversible weight edit) is proven; fidelity is the frontier, measured not
    asserted.

Reversal: `undevour(into, n)` = wbedit.revert (undo the last n devour edits); `devour_log(into)` = the genome.
Safety: never edit a file a llama-server has mmap'd (wbedit's rule); Titan must not be served while devouring into it.
"""
import os, re
import gguf
import wbedit

HERE = os.path.dirname(os.path.abspath(__file__))
TITAN = "C:/llm/models/titan.gguf"

_EXT_KIND = {".py": "python", ".js": "javascript", ".ts": "typescript", ".c": "c", ".cpp": "cpp", ".h": "c",
             ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin", ".html": "web", ".css": "web",
             ".sh": "shell", ".json": "data", ".md": "doc", ".txt": "text", ".xml": "data", ".toml": "data"}


def _classify(source, is_path):
    if not is_path:
        return "text"
    ext = os.path.splitext(source)[1].lower()
    if ext in (".gguf", ".safetensors"):
        return "model"
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        return "image"
    if ext == ".apk":
        return "android-app"
    return _EXT_KIND.get(ext, "binary")


def devour(source, name=None, into=TITAN, amount=0.35, max_tensors=None):
    """Eat `source` (a file path OR pasted text) into Titan's weights, reversibly, via the White Box."""
    if not os.path.exists(into):
        return {"error": f"Titan model not found at {into}"}
    is_path = isinstance(source, str) and len(source) < 1024 and os.path.exists(source)
    kind = _classify(source, is_path)
    if kind == "model":
        return devour_model(source, into, amount, max_tensors)
    if is_path:
        try:
            content = open(source, encoding="utf-8", errors="replace").read()
        except Exception:
            content = ""
        name = name or os.path.splitext(os.path.basename(source))[0]
        if not content:
            content = f"{kind} {os.path.basename(source)}"
    else:
        content = str(source)
        name = name or "text"
    return devour_content(name, content, kind, into, amount)


def devour_model(src_path, into=TITAN, amount=0.35, max_tensors=None):
    """Absorb a source model's parameters into Titan by blending every COMPATIBLE tensor (same name + shape), each a
    reversible White-Box weight edit. Returns the plan + the edits applied (bounded by max_tensors if given, since a full
    40 GB blend is heavy — but every applied edit is byte-exact reversible via the genome)."""
    try:
        tgt = {t.name: [int(x) for x in t.shape] for t in gguf.GGUFReader(into).tensors}
        src = {t.name: [int(x) for x in t.shape] for t in gguf.GGUFReader(src_path).tensors}
    except Exception as e:
        return {"error": f"open failed: {e}"}
    compat = [n for n in src if n in tgt and tgt[n] == src[n]]
    # prefer the FFN bulk (the capacity that carries behavior; DS4-safe) over norms/embeddings
    compat.sort(key=lambda n: (0 if "ffn" in n else 1, n))
    plan = compat if max_tensors is None else compat[:int(max_tensors)]
    applied, errors = [], []
    for n in plan:
        r = wbedit.blend_tensor(into, n, src_path, n, amount)
        (applied if "ok" in r else errors).append({"tensor": n, **({"seq": r["seq"]} if "ok" in r else {"error": r.get("error")})})
    return {"kind": "model", "source": os.path.basename(src_path), "into": os.path.basename(into),
            "compatible": len(compat), "blended": len(applied), "amount": amount,
            "errors": errors[:5], "applied": applied[:20],
            "note": f"Titan absorbed {len(applied)}/{len(compat)} compatible tensors of {os.path.basename(src_path)} "
                    f"at {int(amount*100)}% (reversible via the genome). "
                    + ("" if max_tensors is None else f"Bounded to {max_tensors} this pass — repeat to absorb more.")}


_TOK = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


def _salient_tokens(content, k=12):
    """the content's most-salient identifier tokens (the concepts to study into the weights)."""
    words = _TOK.findall(content)
    if not words:
        return []
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    # rank by frequency but drop the ultra-common; keep distinctive identifiers
    common = {"the", "and", "for", "return", "def", "int", "self", "this", "var", "let", "const", "function", "import"}
    ranked = sorted((w for w in freq if w.lower() not in common), key=lambda w: -freq[w])
    return ranked[:k]


def devour_content(name, content, kind, into=TITAN, amount=0.3):
    """STUDY content into the weights: pull the salient concept tokens and nudge each token's embedding row toward the
    content's dominant concept (a reversible White-Box weight edit per token). Honest scope: this writes the content's
    concepts into the weights; precise lossless recall of a large program is the bake KEYSTONE (mechanism proven, fidelity
    is the frontier — measured, not asserted)."""
    toks = _salient_tokens(content)
    if len(toks) < 2:
        return {"error": "no salient tokens to study (empty/opaque content)"}
    anchor = toks[0]                        # the dominant concept; study the rest toward it (bind the concept cluster)
    applied, skipped = [], []
    for w in toks[1:8]:
        r = wbedit.edit_token(into, w, toward=anchor, amount=amount)
        (applied if "ok" in r else skipped).append(w if "ok" in r else f"{w}:{r.get('error','')[:24]}")
    return {"kind": kind, "name": name, "anchor": anchor, "tokens": toks[:8],
            "studied": len(applied), "skipped": skipped[:4], "amount": amount,
            "note": f"studied '{name}' ({kind}) into Titan — bound {len(applied)} concept tokens toward '{anchor}' "
                    f"(reversible via the genome). Precise recall of a large program is the bake frontier."}


def undevour(into=TITAN, n=1):
    return wbedit.revert(into, n)


def devour_log(into=TITAN):
    return wbedit.genome_log(into)


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) >= 2:
        print(json.dumps(devour(sys.argv[1], max_tensors=(int(sys.argv[2]) if len(sys.argv) > 2 else 3)), indent=2)[:1200])
    else:
        print(json.dumps(devour_log(), indent=2)[:800])
