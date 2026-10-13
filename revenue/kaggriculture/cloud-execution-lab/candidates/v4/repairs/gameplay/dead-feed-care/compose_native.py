# SPDX-License-Identifier: Apache-2.0
"""W2 pre-consumer native integration; CARE then optional guarded starvation.

Consumes the canonical dead-feed-care helper and, when explicitly supplied,
the existing uncared-EOD starvation helper. Both run behind the one existing
``r04_dead_feed_care`` feature and one completed-parent checkpoint. No second
feature key, controller, or production default is created.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

FEATURE_BEFORE = "    early_capital: bool = False\n"
FEATURE_AFTER = FEATURE_BEFORE + "    r04_dead_feed_care: bool = False\n"
SELECT_BEFORE = """                selected = self.production.act(obs)
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                fallback = selected_checkpoint[0]
"""
SELECT_AFTER = """                selected = self.production.act(obs)
                # W2-BEGIN: optional CARE completes before unit-snapshot capture.
                if self.features.r04_dead_feed_care:
                    # Retain the completed parent if import/rewrite is cancelled.
                    parent_checkpoint = (deepcopy(selected), self.controller.cur)
                    fallback = parent_checkpoint[0]
                    selected_checkpoint = parent_checkpoint
                    self.selected = parent_checkpoint[0]
                    stage = 'dead_feed_care'
                    care = load('_titan_dead_feed_care',
                                HERE/'r04_dead_feed_care.py', cache=True)
                    selected = care.apply_dead_feed_care(
                        selected, obs, cfg, enabled=True)
                # W2-END: existing detached selected checkpoint and consumers.
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                fallback = selected_checkpoint[0]
"""
FAST_CHECKPOINT = (
    "                if self.features.r04_fast_tape_clone:\n"
    "                    from r04_fast_tape_clone import apply_fast_tape_clone\n"
    "                    self.selected = apply_fast_tape_clone(selected)\n"
    "                else:\n"
    "                    self.selected = deepcopy(selected)\n"
)
SELECT_BEFORE_FAST = (
    "                selected = self.production.act(obs)\n" + FAST_CHECKPOINT +
    "                selected_checkpoint = (self.selected, self.controller.cur)\n"
    "                fallback = selected_checkpoint[0]\n"
)

SELECT_AFTER_STARVATION = """                selected = self.production.act(obs)
                # W2-BEGIN: one service lane; CARE salvage precedes starvation.
                if self.features.r04_dead_feed_care:
                    # Retain the completed parent if either optional pass is cancelled.
                    parent_checkpoint = (deepcopy(selected), self.controller.cur)
                    fallback = parent_checkpoint[0]
                    selected_checkpoint = parent_checkpoint
                    self.selected = parent_checkpoint[0]
                    stage = 'dead_feed_care'
                    care = load('_titan_dead_feed_care',
                                HERE/'r04_dead_feed_care.py', cache=True)
                    selected = care.apply_dead_feed_care(
                        selected, obs, cfg, enabled=True)
                    stage = 'guarded_starvation_skip'
                    starvation = load('_titan_uncared_eod_feed_skip',
                                      HERE/'r04_uncared_eod_feed_skip.py', cache=True)
                    selected = starvation.apply_guarded_uncared_eod_feed_skip(
                        selected, obs, cfg, self.controller.R[self.controller.cur], enabled=True)
                # W2-END: existing detached selected checkpoint and consumers.
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                fallback = selected_checkpoint[0]
"""


SELECT_AFTER_STARVATION_FAST = (
    "                selected = self.production.act(obs)\n"
    "                # W2-BEGIN: one service lane; CARE salvage precedes starvation.\n"
    "                if self.features.r04_dead_feed_care:\n"
    "                    # Retain the completed parent if either optional pass is cancelled.\n"
    "                    parent_checkpoint = (deepcopy(selected), self.controller.cur)\n"
    "                    fallback = parent_checkpoint[0]\n"
    "                    selected_checkpoint = parent_checkpoint\n"
    "                    self.selected = parent_checkpoint[0]\n"
    "                    stage = 'dead_feed_care'\n"
    "                    care = load('_titan_dead_feed_care',\n"
    "                                HERE/'r04_dead_feed_care.py', cache=True)\n"
    "                    selected = care.apply_dead_feed_care(\n"
    "                        selected, obs, cfg, enabled=True)\n"
    "                    stage = 'guarded_starvation_skip'\n"
    "                    starvation = load('_titan_uncared_eod_feed_skip',\n"
    "                                      HERE/'r04_uncared_eod_feed_skip.py', cache=True)\n"
    "                    selected = starvation.apply_guarded_uncared_eod_feed_skip(\n"
    "                        selected, obs, cfg, self.controller.R[self.controller.cur], enabled=True)\n"
    "                # W2-END: existing detached selected checkpoint and consumers.\n"
    + FAST_CHECKPOINT +
    "                selected_checkpoint = (self.selected, self.controller.cur)\n"
    "                fallback = selected_checkpoint[0]\n"
)


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {name} class")
    return found[0]


def _segment(text: str, node: ast.AST) -> str:
    return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])


def compose_runtime(text: str, *, starvation: bool = False) -> str:
    """Modify only verified native seams; optionally extend the same W2 hook.

    ``starvation=False`` is backward-compatible with the original W2 composer.
    ``starvation=True`` adds the existing guarded starvation helper under the
    SAME feature field/checkpoint after CARE salvage. Unknown/partial seams fail.
    """
    tree = ast.parse(text)
    features = _class(tree, 'Features')
    agent = _class(tree, 'TitanAgent')
    acts = [n for n in agent.body if isinstance(n, ast.FunctionDef) and n.name == 'act']
    if len(acts) != 1:
        raise ValueError('expected exactly one TitanAgent.act')
    ftext, atext = _segment(text, features), _segment(text, acts[0])

    has_feature = 'r04_dead_feed_care: bool' in text
    has_starvation = 'guarded_starvation_skip' in text or 'r04_uncared_eod_feed_skip.py' in text
    has_w2 = 'W2-BEGIN:' in text
    has_fast = 'r04_fast_tape_clone: bool' in text
    if has_w2 or has_feature or has_starvation:
        if text.count(FEATURE_AFTER) != 1 or FEATURE_AFTER not in ftext:
            raise ValueError('partial or drifted W2 feature integration')
        if has_starvation:
            if text.count(SELECT_AFTER_STARVATION_FAST) == 1 and SELECT_AFTER_STARVATION_FAST in atext:
                restored = text.replace(SELECT_AFTER_STARVATION_FAST, SELECT_BEFORE_FAST, 1).replace(
                    FEATURE_AFTER, FEATURE_BEFORE, 1)
            elif text.count(SELECT_AFTER_STARVATION) == 1 and SELECT_AFTER_STARVATION in atext:
                restored = text.replace(SELECT_AFTER_STARVATION, SELECT_BEFORE, 1).replace(
                    FEATURE_AFTER, FEATURE_BEFORE, 1)
            else:
                raise ValueError('partial or drifted starvation integration')
            if compose_runtime(restored, starvation=True) != text:
                raise ValueError('noncanonical W2 starvation integration')
            return text
        if text.count(SELECT_AFTER) != 1 or SELECT_AFTER not in atext:
            raise ValueError('partial or drifted W2 integration')
        if starvation:
            result = text.replace(SELECT_AFTER, SELECT_AFTER_STARVATION, 1)
            ast.parse(result)
            return result
        restored = text.replace(SELECT_AFTER, SELECT_BEFORE, 1).replace(
            FEATURE_AFTER, FEATURE_BEFORE, 1)
        if compose_runtime(restored, starvation=False) != text:
            raise ValueError('noncanonical W2 integration')
        return text

    if has_fast:
        if not starvation:
            raise ValueError('CARE-only W2 composition over fast-tape requires explicit starvation/current composition')
        if (text.count(SELECT_BEFORE_FAST) != 1 or SELECT_BEFORE_FAST not in atext
                or text.count(FEATURE_BEFORE) != 1 or FEATURE_BEFORE not in ftext):
            raise ValueError('fast-tape selected checkpoint seam drifted')
        result = text.replace(SELECT_BEFORE_FAST, SELECT_AFTER_STARVATION_FAST, 1).replace(
            FEATURE_BEFORE, FEATURE_AFTER, 1)
        ast.parse(result)
        return result
    if (text.count(SELECT_BEFORE) != 1 or SELECT_BEFORE not in atext
            or text.count(FEATURE_BEFORE) != 1 or FEATURE_BEFORE not in ftext):
        raise ValueError('native production/checkpoint or feature seam drifted')
    selected_after = SELECT_AFTER_STARVATION if starvation else SELECT_AFTER
    result = text.replace(SELECT_BEFORE, selected_after, 1).replace(
        FEATURE_BEFORE, FEATURE_AFTER, 1)
    ast.parse(result)
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _helper_functions(path: Path) -> set[str]:
    return {n.name for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)}


def materialize(package: Path, helper: Path, output: Path, runtime_sha: str,
                helper_sha: str, *, enable: bool = False,
                starvation_helper: Path | None = None,
                starvation_sha: str | None = None) -> dict:
    """Create an isolated W2 candidate; never overwrite the input package."""
    package, helper, output = package.resolve(), helper.resolve(), output.resolve()
    starvation_helper = None if starvation_helper is None else starvation_helper.resolve()
    if output.exists() or output == package or package in output.parents:
        raise ValueError('output must be a new path outside the input package')
    runtime = package/'titan_runtime.py'
    if digest(runtime) != runtime_sha or digest(helper) != helper_sha:
        raise ValueError('runtime/helper source authentication failed')
    if (package/'r04_dead_feed_care.py').exists() or (package/'r04_uncared_eod_feed_skip.py').exists():
        raise ValueError('input already contains a W2 helper; explicit composition required')
    if 'apply_dead_feed_care' not in _helper_functions(helper):
        raise ValueError('missing SECONDHELP public API')
    starvation = starvation_helper is not None
    if starvation:
        if not starvation_sha or digest(starvation_helper) != starvation_sha:
            raise ValueError('starvation helper source authentication failed')
        funcs = _helper_functions(starvation_helper)
        if 'apply_guarded_uncared_eod_feed_skip' not in funcs:
            raise ValueError('missing guarded starvation public API')
    elif starvation_sha is not None:
        raise ValueError('starvation_sha requires starvation_helper')

    before = runtime.read_text()
    after = compose_runtime(before, starvation=starvation)
    config = json.loads((package/'TITAN-CONFIG.json').read_text())
    if 'r04_dead_feed_care' in config:
        raise ValueError('input has existing W2 config; explicit composition required')
    shutil.copytree(package, output, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (output/'titan_runtime.py').write_text(after)
    shutil.copyfile(helper, output/'r04_dead_feed_care.py')
    if starvation:
        shutil.copyfile(starvation_helper, output/'r04_uncared_eod_feed_skip.py')
    if enable:
        config['r04_dead_feed_care'] = True
        (output/'TITAN-CONFIG.json').write_text(json.dumps(config, indent=2)+'\n')
    if starvation and SELECT_AFTER_STARVATION_FAST in after:
        restored = after.replace(SELECT_AFTER_STARVATION_FAST, SELECT_BEFORE_FAST, 1).replace(
            FEATURE_AFTER, FEATURE_BEFORE, 1)
    else:
        restored = after.replace(SELECT_AFTER_STARVATION if starvation else SELECT_AFTER,
                                 SELECT_BEFORE, 1).replace(FEATURE_AFTER, FEATURE_BEFORE, 1)
    return {
        'runtime_input_sha256': runtime_sha,
        'runtime_output_sha256': digest(output/'titan_runtime.py'),
        'helper_sha256': helper_sha,
        'starvation_helper_sha256': starvation_sha if starvation else None,
        'starvation_composed': starvation,
        'shared_feature_key': 'r04_dead_feed_care',
        'new_feature_key_added': False,
        'enabled_in_scratch_only': enable,
        'untouched_runtime_bytes': restored == before,
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--helper', type=Path, required=True)
    p.add_argument('--runtime-sha256', required=True)
    p.add_argument('--helper-sha256', required=True)
    p.add_argument('--starvation-helper', type=Path)
    p.add_argument('--starvation-sha256')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--enable', action='store_true', help='enable only the new scratch copy')
    a = p.parse_args()
    print(json.dumps(materialize(
        a.package, a.helper, a.output, a.runtime_sha256, a.helper_sha256,
        enable=a.enable, starvation_helper=a.starvation_helper,
        starvation_sha=a.starvation_sha256), indent=2))
