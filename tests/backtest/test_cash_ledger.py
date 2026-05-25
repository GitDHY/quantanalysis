"""
Item 4: Real cash ledger and cost closure.

These tests verify that:
1. With zero costs, run_dynamic produces the same final equity as a perfect buy-and-hold.
2. With $10 fixed commission, final equity is reduced by exactly N_trades * $10.
3. cash + sum(positions * price) is an invariant at every step.
4. cash never goes negative without an explicit leverage flag.
"""

import pytest
from unittest.mock import patch
from backtest.engine import BacktestEngine
from tests._helpers import dummy_coverage


def _run(engine, prices, strategy_func):
    with patch.object(engine.data_fetcher, "fetch_prices", return_value=prices), \
         patch.object(engine, "validate_data_coverage", return_value=dummy_coverage(prices)):
        return engine.run_dynamic(
            tickers=list(prices.columns),
            initial_weights={prices.columns[0]: 100},
            strategy_func=strategy_func,
        )


def _alternating_50_50(ctx, _d):
    """Force a rebalance at every call: 50/50 target weights."""
    return {t: 50.0 for t in ctx.tickers}


def test_zero_cost_preserves_equity(synthetic_prices, cost_free_config):
    """
    With commission=0 and slippage=0, the (post-fix) cash-ledger path must
    produce the same equity as the legacy engine. The cost-deduction logic
    must be a no-op when costs are zero.

    Pinned to the legacy engine's zero-cost monthly-rebalance output for
    our synthetic_prices fixture: 145,271.4470. If this value drifts after
    Task 5, the cost-ledger refactor changed behavior on the zero-cost path
    (which it must not).
    """
    engine = BacktestEngine(cost_free_config)
    result = _run(engine, synthetic_prices, _alternating_50_50)

    expected = 145_271.4470  # from BacktestEngine(cost_free_config).run_dynamic(...) at HEAD before Task 5; if Task 5 changes this value the zero-cost path is no longer a no-op.
    final_value = result.portfolio_values.iloc[-1]
    assert abs(final_value - expected) < 1.0, (
        f"Zero-cost engine drifted from legacy reference: "
        f"got {final_value:.4f}, expected ~{expected:.4f}"
    )


def test_fixed_cost_subtracts_from_equity(synthetic_prices, cost_free_config, fixed_cost_config):
    """
    With $10 fixed commission, the gap between zero-cost and $10-cost equity
    must equal Σ trade_costs (which is reported in metrics).
    Today this FAILS because costs are reported but never deducted.
    """
    engine_zero = BacktestEngine(cost_free_config)
    engine_cost = BacktestEngine(fixed_cost_config)

    result_zero = _run(engine_zero, synthetic_prices, _alternating_50_50)
    result_cost = _run(engine_cost, synthetic_prices, _alternating_50_50)

    total_costs = sum(t.cost for t in result_cost.trades)
    assert total_costs > 0, "test setup error: no trades incurred cost"

    equity_gap = result_zero.portfolio_values.iloc[-1] - result_cost.portfolio_values.iloc[-1]
    # Allow 1% tolerance because cost-induced position-size differences compound slightly.
    assert equity_gap == pytest.approx(total_costs, rel=0.01), \
        f"Cost ${total_costs:.2f} not reflected in equity gap ${equity_gap:.2f}"


def test_total_value_invariant(synthetic_prices, fixed_cost_config):
    """
    At every bar, total_value should equal cash + Σ positions[t] * price[t].
    This requires exposing cash + positions per step — added in Task 4.
    """
    engine = BacktestEngine(fixed_cost_config)
    result = _run(engine, synthetic_prices, _alternating_50_50)

    # New attribute introduced in Task 5: result.equity_breakdown is a list of dicts.
    assert hasattr(result, "equity_breakdown"), \
        "BacktestResult must expose equity_breakdown after Task 5"
    assert len(result.equity_breakdown) == len(result.portfolio_values), (
        f"equity_breakdown length ({len(result.equity_breakdown)}) must match "
        f"portfolio_values length ({len(result.portfolio_values)})"
    )

    for step in result.equity_breakdown:
        cash = step["cash"]
        positions = step["positions"]   # dict[ticker, shares]
        prices = step["prices"]         # dict[ticker, price]
        recomputed = cash + sum(positions[t] * prices[t] for t in positions)
        assert step["total_value"] == pytest.approx(recomputed, rel=1e-9, abs=1e-6), \
            f"Invariant broken at {step['date']}: " \
            f"reported {step['total_value']} vs recomputed {recomputed}"


def test_cash_never_negative_without_leverage_flag(synthetic_prices, fixed_cost_config):
    """
    Without explicit leverage (normalize_weights=True), cash must remain >= -tolerance.
    Negative cash means leverage and should require an explicit opt-in.
    """
    engine = BacktestEngine(fixed_cost_config)
    result = _run(engine, synthetic_prices, _alternating_50_50)

    assert len(result.equity_breakdown) > 0, "equity_breakdown must not be empty"

    for step in result.equity_breakdown:
        assert step["cash"] >= -1e-6, \
            f"cash went negative ({step['cash']:.2f}) without leverage flag at {step['date']}"
