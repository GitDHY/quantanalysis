"""Shared helpers for backtest tests."""

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
