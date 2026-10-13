# SPDX-License-Identifier: Apache-2.0
"""Two-source, exact-preimage repair for current TITAN snapshot/fallback custody.

Pure functions return source bytes. The CLI creates a NEW staging directory;
there is deliberately no in-place writer or default/config/archive mutation.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import stat

RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
INTEGRATED_BLOB = "defa9b84c77fff28ae107bce291b6235bec5d26c"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _source(data: bytes, expected: str, filename: str) -> str:
    if not isinstance(data, bytes) or git_blob(data) != expected:
        raise ValueError(f"{filename}: exact source pin mismatch")
    text = data.decode("utf-8")
    ast.parse(text, filename=filename)
    return text


def _once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("repair anchor must occur exactly once")
    return source.replace(before, after, 1)


def repair_runtime(data: bytes) -> bytes:
    source = _source(data, RUNTIME_BLOB, "titan_runtime.py")
    source = _once(source, """        if self.features.consumer == 'ordered':
            packet = self.consumer.last_packet
            return None if packet is None else packet['post_unit_observation']
""", """        if self.features.consumer == 'ordered':
            packet = getattr(self.consumer, 'last_packet', None)
            if not isinstance(packet, dict):
                return None
            binding = packet.get('selected_post_units_binding')
            if (not isinstance(binding, tuple) or len(binding) != 4
                    or binding[:2] != (int(obs['step']), int(obs['player']))):
                return None
            action = self.selected if returned is None else returned
            if (not isinstance(action, dict) or binding[2:] !=
                    (action.get('farmer', ['PASS']), action.get('hands', []))):
                return None
            post = packet.get('post_unit_observation')
            if (not isinstance(post, dict) or
                    (post.get('step'), post.get('player')) != binding[:2]):
                return None
            return post
""")
    source = _once(source, """            self.consumer.selected_post_units_binding = None
        self.diagnostics = {'consumer': self.features.consumer, 'parent_calls': 0,
""", """            self.consumer.selected_post_units_binding = None
            if self.features.consumer == 'ordered':
                self.consumer.last_packet = None
        self.diagnostics = {'consumer': self.features.consumer, 'parent_calls': 0,
""")
    # A local latch distinguishes a completed initialization from partially
    # constructed controller/consumer state. self.ready is reset on ANY timeout.
    source = _once(source, """        timer = deadline._DeadlineTimer(seconds)
        try:
""", """        timer = deadline._DeadlineTimer(seconds)
        initialization_completed = False
        try:
""")
    source = _once(source, """                if not self.ready:
                    self._initialize()
                if self.history is not None:
""", """                if not self.ready:
                    self._initialize()
                initialization_completed = True
                if self.history is not None:
""")
    source = _once(source, """                    self.post = self._selected_snapshot(obs)
""", """                    self.post = self._selected_snapshot(obs, output)
""")
    source = _once(source, """            output = self._finish_production(obs, output, cfg)
            # Include the reserved fallback/finalizer window in the receipt.
""", """            if initialization_completed:
                output = self._finish_production(obs, output, cfg)
            # Include the reserved fallback/finalizer window in the receipt.
""")
    compile(source, "titan_runtime.py", "exec")
    return source.encode("utf-8")


def repair_integrated(data: bytes) -> bytes:
    source = _source(data, INTEGRATED_BLOB, "integrated_selected.py")
    source = _once(source, """class IntegratedSelectedAgent:
""", """def _snapshot_units(action):
    # Do not inspect market rows: market-only fallback/reordering preserves the
    # completed unit stage, including raw market suffixes and empty slots.
    if not isinstance(action, dict):
        return None
    return (action.get('farmer', ['PASS']), action.get('hands', []))


class IntegratedSelectedAgent:
""")
    source = _once(source, """        cfg = dict(cfg or {}); obs = dict(obs)
        now = absolute_step(obs, cfg); obs['step'] = now
""", """        # Invalidate before even normalization: direct transform callers may
        # retry or supply a new observation without going through TitanAgent.act.
        self.last_packet = None
        self.last_selected = self.last_seeded = None
        cfg = dict(cfg or {}); obs = dict(obs)
        now = absolute_step(obs, cfg); obs['step'] = now
""")
    source = _once(source, """            self.last_seeded = deepcopy(seeded)
""", """            if _snapshot_units(seeded) != _snapshot_units(selected):
                raise ValueError('Seed queue selector changed selected unit rows')
            self.last_seeded = deepcopy(seeded)
""")
    source = _once(source, """            self.last_packet = {'post_unit_observation':post, 'projection':projection,
                                'arrival_contract':contract, 'snapshot':snapshot}
""", """            self.last_packet = {'post_unit_observation':post, 'projection':projection,
                                'arrival_contract':contract, 'snapshot':snapshot,
                                'selected_post_units_binding':
                                    (now, int(obs['player']),
                                     *deepcopy(_snapshot_units(selected)))}
""")
    source = _once(source, """            return out
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
            self.diagnostics['reason'] = str(error)
            return deepcopy(fallback)
""", """            if _snapshot_units(out) != _snapshot_units(selected):
                self.last_packet = None
            return out
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
            self.diagnostics['reason'] = str(error)
            if _snapshot_units(fallback) != _snapshot_units(selected):
                self.last_packet = None
            return deepcopy(fallback)
""")
    compile(source, "integrated_selected.py", "exec")
    return source.encode("utf-8")


def repair(runtime: bytes, integrated: bytes) -> dict[str, bytes]:
    """Return the complete two-source composition, or fail without any writes."""
    return {"titan_runtime.py": repair_runtime(runtime),
            "integrated_selected.py": repair_integrated(integrated)}


def _read_regular(path: Path) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"expected regular input: {path}")
    return path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--integrated", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        inputs = {"titan_runtime.py": _read_regular(args.runtime),
                  "integrated_selected.py": _read_regular(args.integrated)}
        outputs = repair(inputs["titan_runtime.py"], inputs["integrated_selected.py"])
        receipt = {"schema": "titan.return-lifecycle.source-repair/v1",
                   "sources": {name: {"input_blob": git_blob(inputs[name]),
                                      "output_blob": git_blob(data),
                                      "output_sha256": hashlib.sha256(data).hexdigest(),
                                      "output_bytes": len(data)}
                               for name, data in outputs.items()},
                   "default_changes": False, "production_write": False,
                   "gameplay_acceptance": "NOT_RUN"}
        # Refuse all existing output directories, including aliases/symlinks.
        args.output_dir.mkdir(parents=False, exist_ok=False)
        for name, data in outputs.items():
            with (args.output_dir / name).open("xb") as stream:
                stream.write(data)
        with (args.output_dir / "SOURCE-REPAIR.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        parser.exit(2, f"return-lifecycle: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
