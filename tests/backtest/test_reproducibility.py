"""
Reproducibility tests.

Backtests must be deterministic given the same code, data, and config —
otherwise A/B comparing strategy edits (roadmap item #3) is meaningless.
The RNG is the obvious non-determinism source for any strategy that uses
np.random; BacktestConfig.random_seed lets the user pin it.
"""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, BacktestConfig
from tests._helpers import run_backtest


def _seeded_config(start, end, *, random_seed):
    return BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        rebalance_freq="daily",
        commission_fixed=0.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
        random_seed=random_seed,
    )


def _random_strategy(ctx, d):
    """Picks one of the two tickers at random each rebalance bar."""
    if np.random.rand() < 0.5:
        return {ctx.tickers[0]: 100.0, ctx.tickers[1]: 0.0}
    return {ctx.tickers[0]: 0.0, ctx.tickers[1]: 100.0}


def test_same_seed_produces_identical_equity_curve(synthetic_prices):
    """Two backtests with the same random_seed and the same RNG-using
    strategy must produce byte-identical portfolio_values series."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()

    cfg_a = _seeded_config(start, end, random_seed=42)
    cfg_b = _seeded_config(start, end, random_seed=42)

    r_a = run_backtest(BacktestEngine(cfg_a), synthetic_prices, _random_strategy)
    r_b = run_backtest(BacktestEngine(cfg_b), synthetic_prices, _random_strategy)

    pd.testing.assert_series_equal(r_a.portfolio_values, r_b.portfolio_values)


def test_different_seeds_produce_different_equity_curves(synthetic_prices):
    """Sanity check: with a strategy that genuinely uses np.random, two
    different seeds must produce different equity curves. Otherwise the
    same-seed determinism test could pass trivially (e.g. if the engine
    accidentally re-seeded to a constant)."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()

    cfg_a = _seeded_config(start, end, random_seed=1)
    cfg_b = _seeded_config(start, end, random_seed=99999)

    r_a = run_backtest(BacktestEngine(cfg_a), synthetic_prices, _random_strategy)
    r_b = run_backtest(BacktestEngine(cfg_b), synthetic_prices, _random_strategy)

    # At least one bar must differ — same first bar (initial_capital) is fine.
    assert not r_a.portfolio_values.equals(r_b.portfolio_values), (
        "Different seeds produced identical equity curves — random_seed is "
        "not actually being used, or the strategy isn't reading from it."
    )
