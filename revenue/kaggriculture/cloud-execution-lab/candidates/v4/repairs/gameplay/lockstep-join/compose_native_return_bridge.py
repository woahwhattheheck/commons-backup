"""Source-bound composer for the canonical V5 native lockstep return bridge.

This is the current-V5 successor of the reviewed V4 RETURNBRIDGE materializer.
It patches an authenticated current package in place only when every consumed
production surface matches the exact audited Git blobs.  The reviewed native
bridge and ESTUARY/CROSSCURRENT authorities stay byte-identical; this composer
only rebinds their existing default-OFF integration seam to the current V5
entrypoint/runtime and preserves V5's exact feature-type contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# Exact canonical package generation at the V5 rebind.  These are Git blob IDs,
# not commit IDs.  Any later source movement fails closed until deliberately
# reviewed/rebound rather than silently composing against a different runtime.
MAIN_BLOB = "9cf8feaa9a755ffdf85d8878baa07b1fc7940192"
RUNTIME_BLOB = "f35444f8cc5ca853d84cb90fa8602abc33c41644"
FROZEN_BLOB = "0f65045c137412d6bfa5c22950e6fff6a1275c7d"
SCHEDULER_BLOB = "fcfed4d59e17f211e6744e246e86167ea82a0b87"
CONFIG_BLOB = "86c18cee3cec97bbd0e35791fa90b48ecb8925f1"
FLOW_BLOB = "e24dd03a88a71ba4cf6f8d5da1082b89490b5a94"
QUEUE_BLOB = "ac91d3c65deeabadaa60ee83c4a7a84286849150"


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require_blob(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    actual = git_blob_id(data)
    if actual != expected:
        raise ValueError(f"{path}: source drift {actual} != {expected}")
    return data


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact anchor, found {count}")
    return text.replace(old, new, 1)


def patch_runtime(text: str) -> str:
    text = replace_once(
        text,
        "    early_capital: bool = False\n\n    def __post_init__(self):",
        "    early_capital: bool = False\n    lockstep_join: bool = False\n\n    def __post_init__(self):",
        "runtime-feature",
    )
    # V5 #13262 made feature type annotations an enforced public boundary.
    # Every newly composed toggle must enter the exact-bool tuple too; adding a
    # dataclass field alone would accept 1/'false' until later policy checks.
    text = replace_once(
        text,
        "            'operating_stock', 'idle_fertilizer', 'crop_release', 'early_capital',\n"
        "        )",
        "            'operating_stock', 'idle_fertilizer', 'crop_release', 'early_capital',\n"
        "            'lockstep_join',\n"
        "        )",
        "runtime-exact-bool-contract",
    )
    text = replace_once(
        text,
        "        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):\n"
        "            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')\n"
        "        if (self.spatial_pathing or self.spatial_tempo or self.fourth_quadrant or self.idle_fertilizer or self.crop_release) and (self.consumer != 'frozen' or self.terminal_route):",
        "        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):\n"
        "            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')\n"
        "        if self.lockstep_join and (self.consumer != 'frozen' or self.terminal_route):\n"
        "            raise ValueError('lockstep_join requires nonterminal frozen SELL')\n"
        "        if (self.spatial_pathing or self.spatial_tempo or self.fourth_quadrant or self.idle_fertilizer or self.crop_release) and (self.consumer != 'frozen' or self.terminal_route):",
        "runtime-feature-contract",
    )
    return text


def patch_main(text: str) -> str:
    # Current V5 owns town_procurement outside Features.  Construct the bridge
    # only after both public feature binding and that compatibility check have
    # completed; no policy bytes execute during config parsing.
    text = replace_once(
        text,
        "    if town_enabled and (features.consumer != 'frozen' or features.terminal_route):\n"
        "        raise ValueError('town_procurement is the tested nonterminal frozen composition')\n\n"
        "    class FinalPressureAgent(TitanAgent):",
        "    if town_enabled and (features.consumer != 'frozen' or features.terminal_route):\n"
        "        raise ValueError('town_procurement is the tested nonterminal frozen composition')\n"
        "    bridge = None\n"
        "    if features.lockstep_join:\n"
        "        from native_return_bridge import ReturnBridge, load_authorities\n"
        "        flow_bounds, confirmed_net_sells, certify_join_queue = load_authorities(root)\n"
        "        bridge = ReturnBridge(flow_bounds, confirmed_net_sells, certify_join_queue)\n\n"
        "    class FinalPressureAgent(TitanAgent):",
        "main-bridge-construction",
    )
    text = replace_once(
        text,
        "    return FinalPressureAgent(features, fourth_quadrant_admission=admission)",
        "    instance = FinalPressureAgent(features, fourth_quadrant_admission=admission)\n"
        "    instance._return_bridge = bridge\n"
        "    return instance",
        "main-bridge-attachment",
    )
    text = replace_once(
        text,
        "            stage = 'entrypoint_runtime'\n"
        "            output = instance.act(observation, cfg, entry_started=entry_started)\n"
        "            # Publish only after a complete inner return. A foreign exception or",
        "            stage = 'entrypoint_runtime'\n"
        "            bridge = getattr(instance, '_return_bridge', None)\n"
        "            if bridge is not None:\n"
        "                bridge.observe(observation, cfg)\n"
        "            output = instance.act(observation, cfg, entry_started=entry_started)\n"
        "            if bridge is not None:\n"
        "                stage = 'lockstep_join'\n"
        "                baseline_output = output\n"
        "                proposed_output, proposal = bridge.propose(\n"
        "                    instance, observation, cfg, baseline_output)\n"
        "                output = bridge.commit(\n"
        "                    instance, observation, cfg, baseline_output, proposed_output, proposal)\n"
        "            # Publish only after a complete inner return. A foreign exception or",
        "main-exact-return-boundary",
    )
    return text


def patch_config(text: str) -> str:
    parsed = json.loads(text)
    if "lockstep_join" in parsed:
        raise ValueError("config already contains lockstep_join")
    if parsed.get("early_capital") is not True:
        raise ValueError("unexpected current config anchor")
    if parsed.get("town_procurement") is not True:
        raise ValueError("unexpected V5 town-procurement anchor")
    parsed["lockstep_join"] = False
    return json.dumps(parsed, indent=2) + "\n"


def compose(source_root: Path, package_root: Path, component_dir: Path) -> dict:
    source_root = source_root.resolve(); package_root = package_root.resolve()
    component_dir = component_dir.resolve()
    package_inputs = {
        "main.py": MAIN_BLOB,
        "titan_runtime.py": RUNTIME_BLOB,
        "frozen_selected.py": FROZEN_BLOB,
        "scheduler.py": SCHEDULER_BLOB,
        "TITAN-CONFIG.json": CONFIG_BLOB,
    }
    before = {}
    for relative, expected in package_inputs.items():
        data = require_blob(package_root / relative, expected)
        before[relative] = git_blob_id(data)

    flow_source = source_root / "candidates/v4/research/lockstep-scale/effective_flow_bounds.py"
    queue_source = source_root / "candidates/v4/research/lockstep-scale/join_queue_contract.py"
    flow_bytes = require_blob(flow_source, FLOW_BLOB)
    queue_bytes = require_blob(queue_source, QUEUE_BLOB)

    main = (package_root / "main.py").read_text()
    runtime = (package_root / "titan_runtime.py").read_text()
    config = (package_root / "TITAN-CONFIG.json").read_text()
    patched = {
        "main.py": patch_main(main).encode(),
        "titan_runtime.py": patch_runtime(runtime).encode(),
        "TITAN-CONFIG.json": patch_config(config).encode(),
        "native_return_bridge.py": (component_dir / "native_return_bridge.py").read_bytes(),
        "lockstep_effective_flow_bounds.py": flow_bytes,
        "lockstep_join_queue_contract.py": queue_bytes,
    }
    # All validation completes before the first package mutation.
    for relative, data in patched.items():
        (package_root / relative).write_bytes(data)
    return {
        "schema": "titan-v5-lockstep-return-bridge-composition/v1",
        "source_blobs": before,
        "authority_blobs": {
            "effective_flow_bounds.py": FLOW_BLOB,
            "join_queue_contract.py": QUEUE_BLOB,
        },
        "outputs": {name: git_blob_id(data) for name, data in patched.items()},
        "default_enabled": False,
        "strict_feature_types": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path,
                        help="canonical cloud-execution-lab source root")
    parser.add_argument("--package-root", required=True, type=Path,
                        help="authenticated current V5 package root to patch in place")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    receipt = compose(args.source_root, args.package_root, Path(__file__).resolve().parent)
    raw = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(raw)
    print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
