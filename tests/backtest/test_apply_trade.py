"""Direct unit tests for BacktestEngine._apply_trade.

Exercises the helper in isolation so that sign / math errors surface as
focused failures here rather than as confusing drifts in integration tests.
"""

import pytest
from backtest.engine import BacktestEngine, BacktestConfig, Trade


def _engine(commission_fixed: float = 0.0, commission_pct: float = 0.0,
            slippage_pct: float = 0.0) -> BacktestEngine:
    return BacktestEngine(BacktestConfig(
        commission_fixed=commission_fixed,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    ))


def test_buy_subtracts_value_and_cost_from_cash():
    engine = _engine(commission_fixed=10.0)
    positions, cash, cost, trade = engine._apply_trade(
        positions={"AAA": 0.0},
        cash=100_000.0,
        ticker="AAA",
        target_value=10_000.0,
        current_value=0.0,
        price=100.0,
    )
    assert cost == pytest.approx(10.0)
    assert positions["AAA"] == pytest.approx(100.0)  # 10_000 / 100
    assert cash == pytest.approx(100_000.0 - 10_000.0 - 10.0)
    assert trade is not None and trade.action == "BUY"
    assert trade.value == pytest.approx(10_000.0)
    assert trade.shares == pytest.approx(100.0)
    assert trade.cost == pytest.approx(10.0)


def test_sell_adds_value_minus_cost_to_cash():
    engine = _engine(commission_fixed=10.0)
    positions, cash, cost, trade = engine._apply_trade(
        positions={"AAA": 100.0},
        cash=0.0,
        ticker="AAA",
        target_value=0.0,
        current_value=10_000.0,
        price=100.0,
    )
    assert cost == pytest.approx(10.0)
    assert positions["AAA"] == pytest.approx(0.0)
    assert cash == pytest.approx(10_000.0 - 10.0)
    assert trade is not None and trade.action == "SELL"


def test_sub_dust_returns_no_trade():
    engine = _engine(commission_fixed=10.0)
    positions_in = {"AAA": 50.0}
    positions, cash, cost, trade = engine._apply_trade(
        positions=positions_in,
        cash=5_000.0,
        ticker="AAA",
        target_value=5_050.0,    # delta = 50, well below default min_trade_value=100
        current_value=5_000.0,
        price=100.0,
    )
    assert trade is None
    assert cost == 0.0
    assert cash == 5_000.0
    assert positions["AAA"] == 50.0


def test_does_not_mutate_caller_positions():
    engine = _engine()
    positions_in = {"AAA": 0.0}
    positions_out, _cash, _cost, _trade = engine._apply_trade(
        positions=positions_in,
        cash=100_000.0,
        ticker="AAA",
        target_value=10_000.0,
        current_value=0.0,
        price=100.0,
    )
    assert positions_in == {"AAA": 0.0}, "input positions dict was mutated"
    assert positions_out is not positions_in, "output should be a fresh dict"


def test_zero_cost_path_no_op_on_cash_arithmetic():
    """With zero costs, buying X dollars then selling X back returns to original cash."""
    engine = _engine()  # all costs 0
    positions, cash, _cost1, _trade1 = engine._apply_trade(
        positions={"AAA": 0.0},
        cash=100_000.0,
        ticker="AAA",
        target_value=10_000.0,
        current_value=0.0,
        price=100.0,
    )
    positions, cash, _cost2, _trade2 = engine._apply_trade(
        positions=positions,
        cash=cash,
        ticker="AAA",
        target_value=0.0,
        current_value=10_000.0,
        price=100.0,
    )
    assert cash == pytest.approx(100_000.0)
    assert positions["AAA"] == pytest.approx(0.0)


def test_sell_clamps_at_zero_does_not_go_negative():
    """Carry-forward parity with legacy line 867: over-sell silently clamps to 0.

    NOTE: this is intentionally permissive. Task 5 may tighten it (assert /
    warn instead of clamp). Until then, lock in current behavior.
    """
    engine = _engine()
    positions, _cash, _cost, _trade = engine._apply_trade(
        positions={"AAA": 5.0},   # only 5 shares
        cash=0.0,
        ticker="AAA",
        target_value=0.0,
        current_value=10_000.0,   # claims 100 shares' worth
        price=100.0,
    )
    assert positions["AAA"] == 0.0
