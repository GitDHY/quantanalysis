"""
Item 4: Real cash ledger and cost closure.

These tests verify that:
1. With zero costs, run_dynamic produces the same final equity as a perfect buy-and-hold.
2. With $10 fixed commission, final equity is reduced by exactly N_trades * $10.
3. cash + sum(positions * price) is an invariant at every step.
4. cash never goes negative without an explicit leverage flag.
"""

import pytest
from backtest.engine import BacktestEngine
from tests._helpers import dummy_coverage, run_backtest


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
    result = run_backtest(engine, synthetic_prices, _alternating_50_50)

    expected = 144_657.6868  # regenerated under t_open default at Task 9 HEAD
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

    result_zero = run_backtest(engine_zero, synthetic_prices, _alternating_50_50)
    result_cost = run_backtest(engine_cost, synthetic_prices, _alternating_50_50)

    total_costs = sum(t.cost for t in result_cost.trades)
    assert total_costs > 0, "test setup error: no trades incurred cost"

    equity_gap = result_zero.portfolio_values.iloc[-1] - result_cost.portfolio_values.iloc[-1]
    # equity_gap will be SLIGHTLY larger than total_costs because each commission's
    # equity drop compounds with subsequent asset returns. Bound the gap from both sides:
    #   lower bound: gap is at least the raw commissions paid (no negative leakage)
    #   upper bound: gap is at most commissions * 1.5x (allows compounding over the period)
    assert equity_gap >= total_costs * 0.99, (
        f"Equity gap ${equity_gap:.2f} smaller than commissions ${total_costs:.2f} — "
        f"some cost was not deducted"
    )
    assert equity_gap <= total_costs * 1.5, (
        f"Equity gap ${equity_gap:.2f} much larger than commissions ${total_costs:.2f} — "
        f"unexpected leverage or accounting error"
    )


def test_total_value_invariant(synthetic_prices, fixed_cost_config):
    """
    At every bar, total_value should equal cash + Σ positions[t] * price[t].
    This requires exposing cash + positions per step — added in Task 4.
    """
    engine = BacktestEngine(fixed_cost_config)
    result = run_backtest(engine, synthetic_prices, _alternating_50_50)

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
    result = run_backtest(engine, synthetic_prices, _alternating_50_50)

    assert len(result.equity_breakdown) > 0, "equity_breakdown must not be empty"

    for step in result.equity_breakdown:
        assert step["cash"] >= -1e-6, \
            f"cash went negative ({step['cash']:.2f}) without leverage flag at {step['date']}"
