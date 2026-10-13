# SPDX-License-Identifier: Apache-2.0
"""Source-bound scratch composer for the existing W2 CAREBANK service lane.

This does not create a second policy authority or change production defaults. It
materializes the already-reviewed ``dead_feed_care.py`` helper into an exact
current-V5 package, behind the existing ``r04_dead_feed_care`` feature key, so
matched official-engine engagement/economics can be measured before promotion.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

MAIN_BLOB = "9cf8feaa9a755ffdf85d8878baa07b1fc7940192"
RUNTIME_BLOB = "922c99a571e4ba49726a753739f95afe86e72290"
CONFIG_BLOB = "ef0bfb1dfa1ce65103a0b178647fc16bc9c7e791"
HELPER_BLOB = "a93f7fbc3054aaeb2d04878dc620aec66d8a3377"
HELPER_RELATIVE = Path("candidates/v4/repairs/gameplay/dead-feed-care/dead_feed_care.py")

FEATURE_BEFORE = (
    "    early_capital: bool = False\n"
    "    exec_pace: bool = False\n\n"
    "    def __post_init__(self):"
)
FEATURE_AFTER = (
    "    early_capital: bool = False\n"
    "    exec_pace: bool = False\n"
    "    r04_dead_feed_care: bool = False\n\n"
    "    def __post_init__(self):"
)
BOOL_BEFORE = "        bool_fields = (*bool_fields, 'exec_pace')"
BOOL_AFTER = "        bool_fields = (*bool_fields, 'exec_pace', 'r04_dead_feed_care')"
COMPAT_BEFORE = (
    "        if self.exec_pace and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('exec_pace is the tested nonterminal frozen SELL composition')\n"
    "        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')"
)
COMPAT_AFTER = (
    "        if self.exec_pace and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('exec_pace is the tested nonterminal frozen SELL composition')\n"
    "        if self.r04_dead_feed_care and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('r04_dead_feed_care requires nonterminal frozen SELL')\n"
    "        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')"
)
SELECT_BEFORE = (
    "                selected = self.production.act(obs)\n"
    "                self.selected = deepcopy(selected)"
)
SELECT_AFTER = (
    "                selected = self.production.act(obs)\n"
    "                # W2-V5 scratch seam: keep the completed parent as the deadline fallback.\n"
    "                if self.features.r04_dead_feed_care:\n"
    "                    parent_checkpoint = (deepcopy(selected), self.controller.cur)\n"
    "                    fallback = parent_checkpoint[0]\n"
    "                    selected_checkpoint = parent_checkpoint\n"
    "                    self.selected = parent_checkpoint[0]\n"
    "                    stage = 'r04_dead_feed_care'\n"
    "                    care = load('_titan_dead_feed_care',\n"
    "                                HERE/'r04_dead_feed_care.py', cache=True)\n"
    "                    selected = care.apply_dead_feed_care(\n"
    "                        selected, obs, cfg, enabled=True)\n"
    "                    selected = care.apply_carebank_feed_swap(\n"
    "                        selected, obs, cfg, self.controller.R[self.controller.cur],\n"
    "                        enabled=True)\n"
    "                self.selected = deepcopy(selected)"
)


def git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"{label} seam drifted: expected exactly one anchor")
    return text.replace(before, after, 1)


def patch_runtime(text: str) -> str:
    """Add the existing W2 feature/hook to the exact current V5 runtime."""
    if "r04_dead_feed_care" in text:
        raise ValueError("runtime already contains r04_dead_feed_care; explicit rebind required")
    text = replace_once(text, FEATURE_BEFORE, FEATURE_AFTER, "feature")
    text = replace_once(text, BOOL_BEFORE, BOOL_AFTER, "exact-bool")
    text = replace_once(text, COMPAT_BEFORE, COMPAT_AFTER, "consumer-contract")
    text = replace_once(text, SELECT_BEFORE, SELECT_AFTER, "selected-checkpoint")
    ast.parse(text)
    return text


def patch_config(text: str, *, enabled: bool) -> str:
    data = json.loads(text)
    if type(data) is not dict:
        raise ValueError("TITAN-CONFIG.json must be an object")
    if "r04_dead_feed_care" in data:
        raise ValueError("config already contains r04_dead_feed_care")
    if type(enabled) is not bool:
        raise TypeError("enabled must be bool")
    data["r04_dead_feed_care"] = enabled
    return json.dumps(data, indent=2) + "\n"


def _helper_functions(source: bytes) -> set[str]:
    return {
        node.name for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }


def _current_entrypoint_shape(source: bytes) -> None:
    text = source.decode("utf-8")
    town = "town_enabled = _town_procurement_enabled(feature_data)"
    strip = "feature_data.pop('town_procurement', None)"
    bind = "features = Features(**feature_data)"
    if text.count(town) != 1 or text.count(strip) != 1 or text.count(bind) != 1:
        raise ValueError("current entrypoint town/runtime feature seam drifted")
    if not text.index(town) < text.index(strip) < text.index(bind):
        raise ValueError("town_procurement must be consumed before Features binding")


def _copy_ignore(package_root: Path):
    authenticated = {"main.py", "titan_runtime.py", "TITAN-CONFIG.json"}

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
        if Path(directory).resolve() == package_root:
            ignored.update(authenticated.intersection(names))
        return ignored

    return ignore


def materialize(source_root: Path, package_root: Path, output: Path, *, enabled: bool = False) -> dict:
    """Create an isolated authenticated V5 control/treatment package."""
    source_root = source_root.resolve()
    package_root = package_root.resolve()
    output = output.resolve()
    if output.exists() or output == package_root or package_root in output.parents:
        raise ValueError("output must be a new path outside the input package")

    main = package_root / "main.py"
    runtime = package_root / "titan_runtime.py"
    config = package_root / "TITAN-CONFIG.json"
    helper = source_root / HELPER_RELATIVE
    expected = {
        "main.py": (main, MAIN_BLOB),
        "titan_runtime.py": (runtime, RUNTIME_BLOB),
        "TITAN-CONFIG.json": (config, CONFIG_BLOB),
        str(HELPER_RELATIVE): (helper, HELPER_BLOB),
    }
    actual = {}
    captured = {}
    source_sha256s = {}
    for label, (path, expected_blob) in expected.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or non-regular authenticated source: {label}")
        payload = path.read_bytes()
        blob = git_blob_id(payload)
        actual[label] = blob
        captured[label] = payload
        source_sha256s[label] = sha256(payload)
        if blob != expected_blob:
            raise ValueError(f"source authentication failed for {label}: {blob}")

    main_bytes = captured["main.py"]
    runtime_bytes = captured["titan_runtime.py"]
    config_bytes = captured["TITAN-CONFIG.json"]
    helper_label = str(HELPER_RELATIVE)
    helper_bytes = captured[helper_label]

    _current_entrypoint_shape(main_bytes)
    base_config = json.loads(config_bytes.decode("utf-8"))
    if type(base_config) is not dict:
        raise ValueError("TITAN-CONFIG.json must be an object")
    for key in ("town_procurement", "exec_pace"):
        if type(base_config.get(key)) is not bool:
            raise ValueError(f"current package requires exact-bool {key}")

    funcs = _helper_functions(helper_bytes)
    required = {"apply_dead_feed_care", "apply_carebank_feed_swap"}
    if not required.issubset(funcs):
        raise ValueError("authenticated W2 helper is missing required public APIs")
    if (package_root / "r04_dead_feed_care.py").exists():
        raise ValueError("input package already contains W2 helper; explicit composition required")

    runtime_after = patch_runtime(runtime_bytes.decode("utf-8"))
    config_after = patch_config(config_bytes.decode("utf-8"), enabled=enabled)
    runtime_after_bytes = runtime_after.encode("utf-8")
    config_after_bytes = config_after.encode("utf-8")

    shutil.copytree(package_root, output, ignore=_copy_ignore(package_root))
    (output / "main.py").write_bytes(main_bytes)
    (output / "titan_runtime.py").write_bytes(runtime_after_bytes)
    (output / "TITAN-CONFIG.json").write_bytes(config_after_bytes)
    (output / "r04_dead_feed_care.py").write_bytes(helper_bytes)

    return {
        "schema": "titan-v5-carebank-current-native/v1",
        "authority": "candidates/v4/repairs/gameplay/dead-feed-care",
        "source_blobs": actual,
        "source_sha256s": source_sha256s,
        "outputs": {
            "main.py": {
                "git_blob": git_blob_id(main_bytes),
                "sha256": sha256(main_bytes),
            },
            "titan_runtime.py": {
                "git_blob": git_blob_id(runtime_after_bytes),
                "sha256": sha256(runtime_after_bytes),
            },
            "TITAN-CONFIG.json": {
                "git_blob": git_blob_id(config_after_bytes),
                "sha256": sha256(config_after_bytes),
            },
            "r04_dead_feed_care.py": {
                "git_blob": git_blob_id(helper_bytes),
                "sha256": sha256(helper_bytes),
            },
        },
        "feature_key": "r04_dead_feed_care",
        "enabled_in_scratch_only": enabled,
        "production_default_changed": False,
        "strict_feature_types": True,
        "consumer_contract": "frozen_nonterminal_only",
        "entrypoint_contract": "current_main_strips_town_procurement_before_Features",
        "selected_pipeline": ["apply_dead_feed_care", "apply_carebank_feed_swap"],
        "deadline_fallback": "completed_parent_selected_action",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--enable", action="store_true", help="enable only in the scratch output")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    receipt = materialize(args.source_root, args.package_root, args.output, enabled=args.enable)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt is not None:
        args.receipt.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
