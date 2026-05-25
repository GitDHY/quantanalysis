"""Shared pytest fixtures for backtest tests."""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# Ensure quant_platform is importable when running pytest from project root
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import date
from backtest.engine import BacktestConfig


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """
    Two-asset price DataFrame with known, simple dynamics.
    AAA: rises 1% per bar deterministically (50 bars: 100 -> ~164).
    BBB: alternates +2% / -1% per bar.
    Index is business days starting 2024-01-02.
    """
    n = 50
    idx = pd.bdate_range("2024-01-02", periods=n)
    aaa = 100.0 * (1.01 ** np.arange(n))
    bbb_returns = np.where(np.arange(n) % 2 == 0, 0.02, -0.01)
    bbb = 100.0 * np.cumprod(1 + bbb_returns)
    return pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=idx)


@pytest.fixture
def cost_free_config() -> BacktestConfig:
    """Backtest config with all transaction costs zeroed."""
    return BacktestConfig(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 15),
        initial_capital=100_000.0,
        rebalance_freq="monthly",
        commission_fixed=0.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
    )


@pytest.fixture
def fixed_cost_config() -> BacktestConfig:
    """Backtest config with $10 fixed commission per trade, no slippage."""
    return BacktestConfig(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 15),
        initial_capital=100_000.0,
        rebalance_freq="monthly",
        commission_fixed=10.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
    )
