"""Shared helpers for backtest tests."""

from unittest.mock import patch

from backtest.engine import DataValidationResult


def dummy_coverage(prices_df):
    """Minimal DataValidationResult that passes is_valid checks.

    Used by tests that mock `validate_data_coverage` so the engine doesn't
    try to fetch real ticker inception dates.
    """
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


def run_backtest(engine, prices, strategy_func, *, initial_first_ticker_pct: float = 100):
    """Run engine.run_dynamic against synthetic prices via mocked data fetcher.

    Mocks `engine.data_fetcher.fetch_prices` to return `prices` directly and
    `engine.validate_data_coverage` to a passing dummy. Initial weights put
    `initial_first_ticker_pct`% on the first column of `prices`.
    """
    with patch.object(engine.data_fetcher, "fetch_prices", return_value=prices), \
         patch.object(engine, "validate_data_coverage", return_value=dummy_coverage(prices)):
        return engine.run_dynamic(
            tickers=list(prices.columns),
            initial_weights={prices.columns[0]: initial_first_ticker_pct},
            strategy_func=strategy_func,
        )
