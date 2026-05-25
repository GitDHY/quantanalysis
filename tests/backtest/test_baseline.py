"""
Baseline tests — capture current behavior of run_dynamic before fixes.
Some assertions in this file will be UPDATED in later tasks once bugs are fixed.
Each updated assertion has a TODO comment pointing to the task that updates it.
"""

import pytest
from unittest.mock import patch
from backtest.engine import BacktestEngine


def _stub_data_fetcher(prices_df):
    """Patch BacktestEngine to return our synthetic prices instead of yfinance."""
    return patch.object(
        BacktestEngine,
        "_BacktestEngine__placeholder_unused",  # not real; we patch fetch_prices below
        create=True,
    )


def test_run_dynamic_returns_result(synthetic_prices, cost_free_config):
    """Smoke: run_dynamic against synthetic prices returns a BacktestResult."""
    engine = BacktestEngine(cost_free_config)

    # Inject synthetic prices by patching the data_fetcher
    with patch.object(
        engine.data_fetcher,
        "fetch_prices",
        return_value=synthetic_prices,
    ), patch.object(
        engine,
        "validate_data_coverage",
        return_value=_dummy_coverage(synthetic_prices),
    ):
        def hold_aaa(ctx, d):
            return {"AAA": 100.0, "BBB": 0.0}

        result = engine.run_dynamic(
            tickers=["AAA", "BBB"],
            initial_weights={"AAA": 100, "BBB": 0},
            strategy_func=hold_aaa,
        )

    assert result.success is True
    assert len(result.portfolio_values) > 0


def _dummy_coverage(prices_df):
    """Minimal DataValidationResult that passes is_valid checks."""
    from backtest.engine import DataValidationResult
    return DataValidationResult(
        is_valid=True,
        has_warnings=False,
        all_tickers_have_full_coverage=True,
        coverage_info={},
        effective_start_date=prices_df.index[0].date(),
        effective_end_date=prices_df.index[-1].date(),
        excluded_tickers=[],
        partial_tickers=[],
        full_coverage_tickers=list(prices_df.columns),
        warnings=[],
    )
