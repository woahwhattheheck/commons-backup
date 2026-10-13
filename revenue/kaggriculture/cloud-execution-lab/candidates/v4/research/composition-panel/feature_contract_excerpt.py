# Test-only literal Features class excerpt from titan_runtime.py Git b952c9c2.
from dataclasses import dataclass

@dataclass(frozen=True)
class Features:
    consumer: str = 'frozen'
    seed: bool = True
    funding: bool = True
    redundant_hire: bool = False
    terminal_route: bool = False
    committed: bool = True
    budget_seconds: float = 1.0
    reserve_seconds: float = 0.01
    terminal_history: bool = False
    history_hypotheses: dict | None = None
    terminal_tie_break: str = 'baseline'
    spatial_pathing: bool = False
    spatial_tempo: bool = False
    fourth_quadrant: bool = False
    market_pressure: bool = False
    committed_seed_retry: bool = False
    operating_stock: bool = False
    idle_fertilizer: bool = False
    crop_release: bool = False
    early_capital: bool = False

    def __post_init__(self):
        if self.consumer not in ('frozen', 'ordered', 'parent'):
            raise ValueError('consumer must be frozen, ordered or parent')
        if self.terminal_route and self.consumer != 'frozen':
            raise ValueError('terminal_route is the tested frozen SELL composition')
        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')
        if (self.spatial_pathing or self.spatial_tempo or self.fourth_quadrant or self.idle_fertilizer or self.crop_release) and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('spatial routes require nonterminal frozen SELL')
        if self.terminal_history and (self.consumer == 'parent' or self.history_hypotheses is None):
            raise ValueError('terminal_history needs a SELL snapshot and explicit scenario hypotheses')
        if not 0 <= self.reserve_seconds < self.budget_seconds <= 1:
            raise ValueError('invalid action deadline')
