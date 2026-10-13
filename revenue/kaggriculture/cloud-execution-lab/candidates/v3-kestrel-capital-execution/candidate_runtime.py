# SPDX-License-Identifier: Apache-2.0
"""Isolated Titan runtime binding for the KESTREL early-capital candidate."""
from titan_runtime import TitanAgent
from lockstep_early_capital import order_early_capital


class KestrelTitanAgent(TitanAgent):
    """Canonical Titan with only the final early-capital call overridden."""

    def _early_capital_selected(self, obs, cfg, selected):
        if (not getattr(self.features, 'early_capital', False)
                or self.features.consumer != 'frozen'
                or self.features.terminal_route):
            return selected
        import mechanics as mechanics_mod
        from scheduler import parent

        # Bind only a captured FrozenSelected post-unit pair. The PASS-only
        # shortcut in TitanAgent._selected_snapshot returns the raw observation
        # when no pair exists; that is not a completed snapshot, so the safety
        # wrapper reconstructs the official atomic unit stage instead.
        pair = getattr(getattr(self, 'consumer', None), 'selected_post_units', None)
        post_unit = (
            self._selected_snapshot(obs, selected) if pair is not None else None
        )
        result, report = order_early_capital(
            mechanics_mod,
            obs,
            cfg,
            selected,
            self.controller.R[self.controller.cur],
            parent.DECISIONS,
            post_unit=post_unit,
        )
        report['runtime_binding'] = (
            'selected_post_units' if post_unit is not None
            else 'official_atomic_unit_replay'
        )
        self.diagnostics['early_capital'] = report
        return result
