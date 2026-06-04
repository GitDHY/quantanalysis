"""Data-snapshot reproducibility tests.

A backtest result must record enough metadata about the inputs that
two BacktestResults can be compared meaningfully — same code + same
hash = same equity curve; different hashes = "those numbers aren't
comparable, the data changed under you".
"""

import sys
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, BacktestConfig
from tests._helpers import run_backtest


def _zero_cost_config(start, end):
    return BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        rebalance_freq="daily",
        commission_fixed=0.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
    )


def _passthrough_strategy(ctx, d):
    """No-op strategy: always reproduce current weights."""
    return {t: ctx.current_weights.get(t, 0) for t in ctx.tickers}


def test_result_records_data_snapshot_fields(synthetic_prices):
    """BacktestResult must expose: prices_hash (str), bars_count (int),
    pandas_version, numpy_version, python_version (all str)."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()
    cfg = _zero_cost_config(start, end)

    r = run_backtest(BacktestEngine(cfg), synthetic_prices, _passthrough_strategy)

    assert isinstance(r.prices_hash, str) and len(r.prices_hash) >= 16, (
        f"prices_hash must be a non-empty string, got {r.prices_hash!r}"
    )
    assert r.bars_count == len(synthetic_prices), (
        f"bars_count {r.bars_count} != input bars {len(synthetic_prices)}"
    )
    assert r.pandas_version == pd.__version__
    assert r.python_version.startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")


def test_same_prices_produce_same_hash(synthetic_prices):
    """Two backtests on identical prices must produce identical prices_hash.
    Without this, you can't reliably compare two BacktestResults."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()
    cfg = _zero_cost_config(start, end)

    r_a = run_backtest(BacktestEngine(cfg), synthetic_prices, _passthrough_strategy)
    r_b = run_backtest(BacktestEngine(cfg), synthetic_prices.copy(), _passthrough_strategy)

    assert r_a.prices_hash == r_b.prices_hash


def test_different_prices_produce_different_hashes(synthetic_prices):
    """Mutating one cell must change prices_hash. If not, the hash isn't
    actually capturing the data and 'same hash' tells you nothing."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()
    cfg = _zero_cost_config(start, end)

    perturbed = synthetic_prices.copy()
    perturbed.iloc[10, 0] = perturbed.iloc[10, 0] + 0.01

    r_orig = run_backtest(BacktestEngine(cfg), synthetic_prices, _passthrough_strategy)
    r_pert = run_backtest(BacktestEngine(cfg), perturbed, _passthrough_strategy)

    assert r_orig.prices_hash != r_pert.prices_hash, (
        "Single-cell change didn't move the hash — hash isn't covering the data."
    )
