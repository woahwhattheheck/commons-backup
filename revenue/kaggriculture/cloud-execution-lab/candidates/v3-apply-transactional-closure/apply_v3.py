"""Apply the V3 integration edits to an extracted canonical TITAN package.

    python apply_v3.py <package_dir>           edit the package in place
    from apply_v3 import apply; apply(path)    same, as a library call (build_v3.py)

The lane modules and the check live in overlay/ and are copied in by build_v3.py; this
script only edits canonical files.  Every edit is an exact-string replacement asserted
to match exactly once, so it fails loudly if the canonical base moves.

Seams (from the ARGUS semantic audit, candidates/v3-g01-argus-safe/AUDIT.md):
  E11  seller-owned seam BEFORE pending accounting, in both seller variants
       (scheduler.SellScheduler.act and frozen_selected.FrozenSelected.transform)
  O01 / E20  TitanAgent._v3_post on the completed path, before _finish_production,
       so the early_capital ordering stage sees any appended land / blanked hire
  SHOP no production seam (A7); shop_arb.py ships as a tested callable only
Flags travel as deterministic TITAN-CONFIG.json keys carried in cfg['titan_v3'];
nothing reads the environment.
"""
import io
import json
import os
import stat
import sys
import tempfile

PARAMS = {
    "rival_dump_price_drop": 15.0,
    "rival_dump_lookback_steps": 8,
    "e11_min_future_absorption": 2,
    "e20_max_hires_per_day": 3,
    "e20_min_unwatered_crops": 3,
    "g01_early_expander_step": 144,
    "g01_land_cash_floor": 0,
}

FIELDS = (
    "    # V3 integration (candidates/v3): fleet lanes behind deterministic package keys.\n"
    "    e11_rival_sell: bool = False\n"
    "    rival_model: bool = False\n"
    "    e20_hire_guard: bool = False\n"
    "    rival_dump_price_drop: float = 15.0\n"
    "    rival_dump_lookback_steps: int = 8\n"
    "    e11_min_future_absorption: int = 2\n"
    "    e20_max_hires_per_day: int = 3\n"
    "    e20_min_unwatered_crops: int = 3\n"
    "    g01_early_expander_step: int = 144\n"
    "    g01_land_cash_floor: float = 0.0\n"
    "    # L01 leader mechanisms (Grok Build #5, PR #11459) as keys; tape patches at _initialize.\n"
    "    l01_land: bool = False\n"
    "    l01_sheep: bool = False\n"
    "    l01_day0buy: bool = False\n"
    "    l01_tranche: bool = False\n"
    "    l01_leanplant: bool = False\n"
)

L01_KEYS = ("l01_land", "l01_sheep", "l01_day0buy", "l01_tranche", "l01_leanplant")

RUNTIME_METHODS = (
    "    # ------------------------------------------------------------ V3 lanes\n"
    "    def _v3_active(self):\n"
    "        f = self.features\n"
    "        return bool(f.e11_rival_sell or f.rival_model or f.e20_hire_guard\n"
    "                    or f.l01_land or f.l01_sheep or f.l01_day0buy or f.l01_tranche or f.l01_leanplant)\n\n"
    "    def _v3_config(self):\n"
    "        \"\"\"Deterministic package keys for the V3 lanes, carried inside the game config.\"\"\"\n"
    "        f = self.features\n"
    "        return {'e11_rival_sell': bool(f.e11_rival_sell), 'rival_model': bool(f.rival_model),\n"
    "                'e20_hire_guard': bool(f.e20_hire_guard),\n"
    "                'params': {'rival_dump_price_drop': float(f.rival_dump_price_drop),\n"
    "                           'rival_dump_lookback_steps': int(f.rival_dump_lookback_steps),\n"
    "                           'e11_min_future_absorption': int(f.e11_min_future_absorption),\n"
    "                           'e20_max_hires_per_day': int(f.e20_max_hires_per_day),\n"
    "                           'e20_min_unwatered_crops': int(f.e20_min_unwatered_crops),\n"
    "                           'g01_early_expander_step': int(f.g01_early_expander_step),\n"
    "                           'g01_land_cash_floor': float(f.g01_land_cash_floor)}}\n\n"
    "    def _v3_post(self, obs, cfg, output):\n"
    "        \"\"\"V3 lanes O01 (queue-safe BUY_LAND append) and E20 (low-demand HIRE limiter).\n\n"
    "        Runs on the completed path before _finish_production so the early_capital\n"
    "        ordering stage sees the edited queue.  Identity when both keys are off.  A\n"
    "        raised error keeps the selected action and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        v3 = cfg.get('titan_v3') or {}\n"
    "        if not (v3.get('rival_model') or v3.get('e20_hire_guard')):\n"
    "            return output\n"
    "        params = dict(cfg)\n"
    "        params.update(v3.get('params') or {})\n"
    "        report = {}\n"
    "        try:\n"
    "            if v3.get('rival_model'):\n"
    "                from rival_model import apply_rival_model\n"
    "                previous = getattr(self, '_v3_prev_prices', None)\n"
    "                output, report['rival_model'] = apply_rival_model(obs, output, previous, params, enabled=True)\n"
    "                self._v3_prev_prices = dict((obs.get('market') or {}).get('prices') or {})\n"
    "            if v3.get('e20_hire_guard'):\n"
    "                from e20_hire_guard import apply_hire_guard\n"
    "                output, report['e20_hire_guard'] = apply_hire_guard(obs, output, params, enabled=True)\n"
    "        except Exception as error:\n"
    "            report['error'] = type(error).__name__\n"
    "        self.diagnostics['v3'] = report\n"
    "        return output\n\n"
    "    def _v3_l01_install(self):\n"
    "        \"\"\"V3 lane L01: patch the route tapes once (land / sheep / day0buy / leanplant keys).\n\n"
    "        Runs at the end of _initialize, after the controller and its tapes exist.  With\n"
    "        every l01 key off the tapes are untouched and the reason L01_noop:flag_off is\n"
    "        recorded.  A raised error keeps the canonical tapes and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        try:\n"
    "            from l01_mechanics import flags_from_features, install\n"
    "            state = install(self, flags_from_features(self.features))\n"
    "            self.diagnostics['v3_l01'] = {'activations': dict(state['activations']),\n"
    "                                          'reasons': list(state['reasons'])}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_l01'] = {'activations': {}, 'reasons': ['V3_L01_ERROR_' + type(error).__name__]}\n\n"
    "    def _v3_post_final(self, obs, cfg, output):\n"
    "        \"\"\"V3 lane L01 tranche: live SELL enlargement after _finish_production (as measured).\"\"\"\n"
    "        if not self.features.l01_tranche:\n"
    "            return output\n"
    "        try:\n"
    "            from collections import Counter\n"
    "            from l01_mechanics import apply_tranche, flags_from_features, shed_snapshot\n"
    "            activations = Counter()\n"
    "            output = apply_tranche(output, obs, flags_from_features(self.features), activations,\n"
    "                                   shed=shed_snapshot(self, obs))\n"
    "            self.diagnostics['v3_l01_tranche'] = {'activations': dict(activations)}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_l01_tranche'] = {'activations': {}, 'error': type(error).__name__}\n"
    "        return output\n\n"
)

SELLER_METHOD = (
    "    def _v3_e11_before_pending(self, obs, config, out, now):\n"
    "        \"\"\"V3 lane E11 at the seller-owned seam before pending accounting (ARGUS A3).\"\"\"\n"
    "        v3=config.get('titan_v3') if isinstance(config,dict) else None\n"
    "        if not v3 or not v3.get('e11_rival_sell'):return out\n"
    "        try:\n"
    "            from e11_rival_sell import apply_e11\n"
    "            cfg=dict(config);cfg.update(v3.get('params') or {})\n"
    "            history=list(getattr(self,'_v3_price_history',[]))\n"
    "            out,report=apply_e11(obs,out,history,cfg,absorption,enabled=True)\n"
    "            self.diagnostics['v3_e11']=report\n"
    "            prices=dict((obs.get('market') or {}).get('prices') or {})\n"
    "            history.append((int(now),prices))\n"
    "            lookback=max(0,int(cfg.get('rival_dump_lookback_steps',8)))\n"
    "            self._v3_price_history=[entry for entry in history if 0<=int(now)-int(entry[0])<=lookback]\n"
    "            return out\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_e11']={'enabled':True,'changed':False,'reason':'V3_E11_ERROR_'+type(error).__name__}\n"
    "            return out\n\n"
)

RELEASE_NOTE = (
    "\n## V3 integration lanes (candidates/v3)\n\n"
    "The V3 tree carries the fleet lanes inside this one package behind deterministic\n"
    "`TITAN-CONFIG.json` keys, all shipped off: `e11_rival_sell` (defer a SELL of a\n"
    "product whose public price dropped, when exact future absorption ticks still cover\n"
    "it; seller-owned seam before pending accounting in both seller variants),\n"
    "`rival_model` (public-state rival archetype; appends one BUY_LAND only into a free\n"
    "market slot, never edits SELLs) and `e20_hire_guard` (blanks every HIRE beyond the\n"
    "remaining low-demand allowance, preserving queue positions). Parameters:\n"
    "`rival_dump_price_drop`, `rival_dump_lookback_steps`, `e11_min_future_absorption`,\n"
    "`e20_max_hires_per_day`, `e20_min_unwatered_crops`, `g01_early_expander_step`,\n"
    "`g01_land_cash_floor`. The lanes descend from the TESSERA designs, the G01 patches\n"
    "(PR #11371) and the ARGUS semantic-safety repair (candidates/v3-g01-argus-safe).\n"
    "The shop multiplier ships as a scoring-only callable with no production seam. A\n"
    "panel variant is a copy of this tree with keys flipped in `TITAN-CONFIG.json`; no\n"
    "environment variable selects anything. With every key off the runtime path is the\n"
    "canonical archive's. Wiring and contract checks: `checks/test_v3_features.py`.\n"
    "Playing strength per key is measured by the V25 fleet panels recorded in\n"
    "`candidates/v3/V3-MANIFEST.json`; no strength claim accompanies these bytes.\n"
    "\n"
    "L01 leader mechanisms (Grok Build #5, PR #11459) ride the same tree as keys, all\n"
    "shipped off: `l01_land` (BUY_LAND posted at tape steps 74 and 98, the 150/265 posts\n"
    "kept), `l01_sheep` (COW purchases after step 1 become SHEEP), `l01_day0buy` (the\n"
    "step-0 market becomes the SpaTaro product basket), `l01_leanplant` (the last 92\n"
    "PLANT WHEAT units become PASS) and `l01_tranche` (from day 28 the returned queue\n"
    "sells WHEAT up to 57 and CARROT up to 32 and packs the other shed products). The\n"
    "four tape keys patch the Arlene MAIN routes once at `TitanAgent._initialize`; the\n"
    "tranche edits the queue after `_finish_production`. Checks: `checks/test_v3_l01.py`.\n"
)


def _replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, "%s: expected 1 match, found %d" % (label, count)
    return text.replace(old, new)


TARGET_FILES = (
    "titan_runtime.py",
    "scheduler.py",
    "frozen_selected.py",
    "TITAN-CONFIG.json",
    "TITAN-RELEASE.md",
)


class ApplyTransactionError(RuntimeError):
    """A commit failed and one or more original files could not be restored."""


def _load_source_set(src):
    """Read and validate the complete five-file input set before rendering.

    The canonical integration operation is deliberately limited to regular files.
    Replacing a symlink would mutate a different ownership boundary than the package
    tree named by ``src``.
    """
    source = {}
    modes = {}
    for name in TARGET_FILES:
        path = os.path.join(src, name)
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("%s: expected a regular file" % name)
        with open(path, "rb") as handle:
            raw = handle.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("%s: expected UTF-8 source" % name) from error
        source[name] = (raw, text)
        modes[name] = stat.S_IMODE(info.st_mode)
    return source, modes


def _render_source_set(source):
    """Return every edited file in memory; no package byte is mutated here."""
    rendered = {name: pair[1] for name, pair in source.items()}

    runtime = rendered["titan_runtime.py"]
    runtime = _replace_once(runtime, "\n\n    def __post_init__(self):", "\n" + FIELDS + "\n    def __post_init__(self):", "Features fields")
    runtime = _replace_once(
        runtime,
        "        cfg = dict(configuration or {})\n        obs = dict(observation)\n",
        "        cfg = dict(configuration or {})\n"
        "        if self._v3_active():\n"
        "            # V3 lanes travel with the package configuration, never the environment.\n"
        "            cfg['titan_v3'] = self._v3_config()\n"
        "        obs = dict(observation)\n",
        "cfg injection",
    )
    runtime = _replace_once(
        runtime,
        "        self._commit_seller_state(seller_checkpoint)\n"
        "        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,\n"
        "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
        "        output = self._finish_production(obs, output, cfg)\n"
        "        return output\n",
        "        self._commit_seller_state(seller_checkpoint)\n"
        "        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,\n"
        "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
        "        output = self._v3_post(obs, cfg, output)\n"
        "        output = self._finish_production(obs, output, cfg)\n"
        "        output = self._v3_post_final(obs, cfg, output)\n"
        "        return output\n",
        "post hook",
    )
    runtime = _replace_once(
        runtime,
        "        self._restore_seller_state()\n        self.ready = True\n",
        "        self._restore_seller_state()\n        self._v3_l01_install()\n        self.ready = True\n",
        "l01 install seam",
    )
    runtime = _replace_once(runtime, "    __call__ = act\n", RUNTIME_METHODS + "    __call__ = act\n", "v3 methods")
    rendered["titan_runtime.py"] = runtime

    sched = rendered["scheduler.py"]
    sched = _replace_once(sched, "    def act(self, obs, config=None):\n", SELLER_METHOD + "    def act(self, obs, config=None):\n", "scheduler method")
    sched = _replace_once(
        sched,
        "        out['market']=market\n        for item,q in targets.items():\n",
        "        out['market']=market\n        out=self._v3_e11_before_pending(obs,config,out,now)\n        for item,q in targets.items():\n",
        "scheduler pre-pending seam",
    )
    rendered["scheduler.py"] = sched

    frozen = rendered["frozen_selected.py"]
    frozen = _replace_once(
        frozen,
        "        if funding is not None:self.diagnostics['same_turn_funding']=funding\n        for item,q in targets.items():\n",
        "        if funding is not None:self.diagnostics['same_turn_funding']=funding\n"
        "        out=self._v3_e11_before_pending(obs,config,out,now)\n"
        "        for item,q in targets.items():\n",
        "frozen pre-pending seam",
    )
    rendered["frozen_selected.py"] = frozen

    data = json.loads(rendered["TITAN-CONFIG.json"])
    for key in ("e11_rival_sell", "rival_model", "e20_hire_guard") + L01_KEYS:
        if key in data:
            raise AssertionError(key)
        data[key] = False
    for key, value in PARAMS.items():
        if key in data:
            raise AssertionError(key)
        data[key] = value
    rendered["TITAN-CONFIG.json"] = json.dumps(data, indent=2) + "\n"
    rendered["TITAN-RELEASE.md"] = rendered["TITAN-RELEASE.md"] + RELEASE_NOTE
    return rendered


def _temp_file(path, payload, mode, role):
    """Durably stage one file beside its target and return the temporary path."""
    directory = os.path.dirname(path) or "."
    prefix = ".%s.v3-%s-" % (os.path.basename(path), role)
    fd, temporary = tempfile.mkstemp(prefix=prefix, dir=directory)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return temporary


def _unlink(path):
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _fsync_directory(path):
    """Best-effort directory durability; unsupported platforms remain functional."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path or ".", flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _commit_source_set(src, source, modes, rendered):
    """Replace all five files, restoring exact originals after any BaseException.

    Stages and backups are created before the first replacement. A process crash can
    still interrupt a portable multi-file transaction, but every synchronous failure
    (including KeyboardInterrupt/SystemExit) is rollback-safe and leaves recovery
    bytes on disk if rollback itself cannot complete.
    """
    staged = {}
    backups = {}
    committed = []
    directories = set()
    try:
        for name in TARGET_FILES:
            target = os.path.join(src, name)
            directories.add(os.path.dirname(target) or ".")
            staged[name] = _temp_file(target, rendered[name].encode("utf-8"), modes[name], "stage")
            backups[name] = _temp_file(target, source[name][0], modes[name], "backup")

        for name in TARGET_FILES:
            target = os.path.join(src, name)
            os.replace(staged[name], target)
            staged[name] = None
            committed.append(name)
        for directory in directories:
            _fsync_directory(directory)
    except BaseException as commit_error:
        rollback_errors = []
        for name in reversed(committed):
            target = os.path.join(src, name)
            try:
                os.replace(backups[name], target)
                backups[name] = None
            except BaseException as rollback_error:
                rollback_errors.append((name, rollback_error))
        for directory in directories:
            _fsync_directory(directory)
        for path in staged.values():
            _unlink(path)
        # Keep any backup that could not be restored as an explicit recovery artifact.
        for name, path in backups.items():
            if name not in {failed_name for failed_name, _ in rollback_errors}:
                _unlink(path)
        if rollback_errors:
            details = ", ".join("%s:%s" % (name, type(error).__name__) for name, error in rollback_errors)
            raise ApplyTransactionError("commit failed and rollback was incomplete: " + details) from commit_error
        raise
    else:
        for path in backups.values():
            _unlink(path)
        for path in staged.values():
            _unlink(path)


def apply(src):
    """Validate, render, and transactionally install the V3 five-file edit set."""
    source, modes = _load_source_set(src)
    rendered = _render_source_set(source)
    _commit_source_set(src, source, modes, rendered)
    return src


if __name__ == "__main__":
    print("V3 edits applied to", apply(sys.argv[1]))
