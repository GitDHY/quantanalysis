"""
Baseline smoke test for BacktestEngine.run_dynamic.

Exercises the engine end-to-end against synthetic prices via mocked data fetcher.
Assertions are pinned to the AAA-only buy-and-hold case, which is invariant
across the cash-ledger and t+1 fill fixes that follow in Tasks 5 and 9.
Also exposes the `_dummy_coverage` helper for downstream test files.
"""

from unittest.mock import patch
from backtest.engine import BacktestEngine, DataValidationResult


def _dummy_coverage(prices_df):
    """Minimal DataValidationResult that passes is_valid checks."""
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


def test_run_dynamic_returns_result(synthetic_prices, cost_free_config):
    """Smoke: AAA buy-and-hold produces deterministic equity curve."""
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
        def hold_aaa(ctx, _):
            return {"AAA": 100.0, "BBB": 0.0}

        result = engine.run_dynamic(
            tickers=["AAA", "BBB"],
            initial_weights={"AAA": 100, "BBB": 0},
            strategy_func=hold_aaa,
        )

    assert result.success is True
    assert len(result.portfolio_values) == 50
    assert len(result.trades) == 1, "AAA-only hold should produce exactly one initial trade"
    expected_final = 100_000.0 * (1.01 ** 49)
    final_equity = result.portfolio_values.iloc[-1]
    rel_err = abs(final_equity - expected_final) / expected_final
    assert rel_err < 1e-6, (
        f"Final equity {final_equity:.2f} drifted from expected {expected_final:.2f} "
        f"(rel err {rel_err:.2e})"
    )
