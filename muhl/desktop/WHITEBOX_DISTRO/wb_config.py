#!/usr/bin/env python3
"""wb_config.py — WHERE THIS MACHINE KEEPS ITS MODELS. The one module that makes White Box installable.

The lab was written with `C:/llm/models/...` and `C:/Users/lucys/OneDrive/Desktop/...` spelled out literally, which is
correct on the author's box and unrunnable anywhere else. This module resolves every one of those roots. It is ADDITIVE:
it extends the author's existing `pfc_paths.PFC_ROOT` convention rather than replacing it, and on a machine where
`C:/llm/models` exists it returns exactly the old literals — unchanged behaviour, nothing to relearn.

RESOLUTION ORDER (first hit wins), per setting:
    1. environment variable        e.g.  set WHITEBOX_MODELS_DIR=D:/ai/models
    2. config file (JSON)                whitebox.config.json  -> {"models_dir": "D:/ai/models"}
    3. auto-discovery / default          the first plausible folder that actually exists

CONFIG FILE is looked for, in order:
    $WHITEBOX_CONFIG                     an explicit path to the json
    ./whitebox.config.json               the current working directory
    <this folder>/whitebox.config.json   next to the app
    ~/.whitebox/config.json              per-user

SETTINGS
    models_dir     WHITEBOX_MODELS_DIR    folder scanned for *.gguf (the Import dropdown)
    out_dir        WHITEBOX_OUT_DIR       where Export writes json+md       (default <app>/whitebox_out)
    archive_dir    WHITEBOX_ARCHIVE_DIR   where the Researcher Archive goes (default <out_dir>/research_archive)
    default_model  WHITEBOX_MODEL         prefilled model for tool args     (default: first *.gguf in models_dir)
    clean_model    WHITEBOX_CLEAN_MODEL   the "clean control" tool defaults (default: default_model)
    titan_model    WHITEBOX_TITAN_MODEL   the model the pfc/wf tools were written against
    port           WHITEBOX_PORT          White Box 1.0 UI                  (default 7862)
    port_v2        WHITEBOX_PORT_V2       White Box V2 UI                   (default 7864)

Nothing here opens a model, evaluates anything, or writes to a model file. It resolves strings and (only when the app
explicitly asks, via save_models_dir) writes the small json config.

    python wb_config.py            # print what this machine resolves to, and whether it exists
"""
import json, os, glob

HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}


# --------------------------------------------------------------------------- config file
def config_path(for_write=False):
    """The config file this machine uses. for_write=True returns where a NEW config should be created."""
    env = os.environ.get("WHITEBOX_CONFIG")
    if env:
        return os.path.abspath(env)
    cands = [os.path.join(os.getcwd(), "whitebox.config.json"),
             os.path.join(HERE, "whitebox.config.json"),
             os.path.join(os.path.expanduser("~"), ".whitebox", "config.json")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return cands[1]


def load():
    """The config dict (empty if there is no config file). Cached; call reload() after a write."""
    if "cfg" in _CACHE:
        return _CACHE["cfg"]
    cfg = {}
    p = config_path()
    try:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                cfg = d
    except Exception:
        cfg = {}                                   # a broken config must never stop the app from starting
    _CACHE["cfg"] = cfg
    return cfg


def reload():
    _CACHE.clear()
    return load()


def _norm(p):
    return str(p).replace("\\", "/").rstrip("/") if p else p


def _get(key, env, default=None):
    """env var -> config file -> default."""
    v = os.environ.get(env)
    if v:
        return _norm(v)
    v = load().get(key)
    if v:
        return _norm(v)
    return default


# --------------------------------------------------------------------------- models_dir
def _pfc_root():
    """The author's existing convention: PFC_ROOT (default C:/llm). Kept so his box resolves to the old literals."""
    return _norm(os.environ.get("PFC_ROOT", "C:/llm"))


def _discover_models_dir():
    """No env, no config: pick the first folder that EXISTS. On the author's box this is C:/llm/models, so behaviour is
    unchanged. Elsewhere it lands on a folder next to the app, which the first-run picker can then point somewhere else."""
    for c in (_pfc_root() + "/models",                          # the author's box / PFC_ROOT override
              os.path.join(HERE, "models"),                     # models dropped next to the distro
              os.path.join(os.path.expanduser("~"), "models"),
              os.path.join(os.path.expanduser("~"), ".cache", "whitebox", "models")):
        if os.path.isdir(c):
            return _norm(c)
    return _norm(os.path.join(HERE, "models"))                  # nothing exists yet -> where the picker will create it


def models_dir():
    return _get("models_dir", "WHITEBOX_MODELS_DIR") or _discover_models_dir()


def save_models_dir(d):
    """Persist a models folder chosen in the UI (the first-run picker). Writes the small json config; creates nothing else.
    Returns {"ok":True,...} or {"error":...}. Never touches a model file."""
    d = _norm(d)
    if not d or not os.path.isdir(d):
        return {"error": f"not a folder: {d}"}
    p = config_path(for_write=True)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        cfg = {}
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    cfg = json.load(f) or {}
            except Exception:
                cfg = {}
        cfg["models_dir"] = d                                   # merge: never drop a setting the user already had
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        reload()
        return {"ok": True, "config": _norm(p), "models_dir": d, "models": len(list_models(d))}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def list_models(d=None):
    """Basenames of every *.gguf in the models folder, sorted. Empty list if the folder does not exist."""
    d = d or models_dir()
    try:
        return sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*.gguf")))
    except Exception:
        return []


def model(name):
    """Resolve a model reference: an absolute path is returned as-is; a bare filename resolves against models_dir."""
    if not name:
        return name
    n = _norm(name)
    return n if os.path.isabs(n) else _norm(os.path.join(models_dir(), n))


def default_model():
    """The model that prefills tool argument boxes. Explicit setting wins; else the first *.gguf found; else '' (the UI
    shows an empty args box rather than a path that does not exist on this machine)."""
    v = _get("default_model", "WHITEBOX_MODEL")
    if v:
        return model(v)
    fs = list_models()
    return _norm(os.path.join(models_dir(), fs[0])) if fs else ""


def named_model(key, env, preferred=()):
    """A model a specific tool was written against (e.g. the author's 'titan.gguf' or his clean SmolLM2 control).
    Explicit setting -> a preferred basename that actually exists here -> the default model -> ''."""
    v = _get(key, env)
    if v:
        return model(v)
    d = models_dir()
    for b in preferred:
        c = os.path.join(d, b)
        if os.path.exists(c):
            return _norm(c)
    return default_model()


def titan_model():
    """The model the pfc_*/wf_* and several fable_* tools were originally written against (the author's titan.gguf)."""
    return named_model("titan_model", "WHITEBOX_TITAN_MODEL", ("titan.gguf",))


def clean_model():
    """The small 'verified-clean control' the fable_* defaults were written against."""
    return named_model("clean_model", "WHITEBOX_CLEAN_MODEL",
                       ("SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf", "SmolLM2-360M-Instruct-Q8_0.gguf"))


def circuits_registry():
    """titan_circuits.json — the circuit registry pfc_atlas enumerates. Author's box: <models>/titan_circuits.json."""
    v = _get("circuits_registry", "WHITEBOX_CIRCUITS_JSON")
    return v or _norm(os.path.join(models_dir(), "titan_circuits.json"))


# --------------------------------------------------------------------------- output roots
def out_dir():
    """Where Export writes whitebox_<model>.json/.md."""
    v = _get("out_dir", "WHITEBOX_OUT_DIR")
    if v:
        return v
    legacy = "C:/Users/lucys/OneDrive/Desktop/TitanSDC"          # the author's box: unchanged behaviour
    if os.path.isdir(legacy):
        return legacy
    return _norm(os.path.join(HERE, "whitebox_out"))


def archive_dir():
    """Where the Researcher Archive (weights + all analysis) is written."""
    v = _get("archive_dir", "WHITEBOX_ARCHIVE_DIR")
    if v:
        return v
    legacy = "C:/Users/lucys/OneDrive/Desktop/WhiteBox_Research_Archive"
    if os.path.isdir(legacy):
        return legacy
    return _norm(os.path.join(out_dir(), "research_archive"))


def results_json():
    """Where whitebox_sweep.py appends its operator x model matrix."""
    v = _get("results_json", "WB_RESULTS")
    return v or _norm(os.path.join(out_dir(), "whitebox_matrix.json"))


def port():
    try:
        return int(_get("port", "WHITEBOX_PORT") or 7862)
    except Exception:
        return 7862


def port_v2():
    try:
        return int(_get("port_v2", "WHITEBOX_PORT_V2") or 7864)
    except Exception:
        return 7864


def summary():
    md = models_dir()
    return {"config_file": _norm(config_path()), "config_exists": os.path.isfile(config_path()),
            "models_dir": md, "models_dir_exists": os.path.isdir(md), "models_found": len(list_models(md)),
            "default_model": default_model(), "out_dir": out_dir(), "archive_dir": archive_dir(),
            "port": port(), "port_v2": port_v2()}


if __name__ == "__main__":
    s = summary()
    print("White Box - resolved configuration for this machine\n")
    for k, v in s.items():
        print(f"  {k:<20} {v}")
    if not s["models_dir_exists"]:
        print("\n  models_dir does not exist yet. Set one with either:")
        print("    set WHITEBOX_MODELS_DIR=D:/path/to/your/ggufs")
        print(f'    or create {_norm(config_path(for_write=True))} containing: '
              '{"models_dir": "D:/path/to/your/ggufs"}')
    elif s["models_found"] == 0:
        print(f"\n  no *.gguf found in {s['models_dir']} (put a .gguf there, or point models_dir elsewhere)")
