"""
Item 5: t+1 fill semantics + lookahead red-team test.

A perfect-foresight strategy that peeks at the next bar's prices to pick the
winner SHOULD outperform when fills happen at the same bar (legacy `t_close`
behavior — lookahead succeeds). Under proper `t_open` semantics — fills happen
at the bar AFTER the decision — that lookahead is blunted: the strategy can't
trade at the prices it peeked at, so the foresight value disappears.

This test compares the same strategy under both fill modes and asserts that
`t_close` produces a measurably higher return than `t_open`. While Task 9 is
pending the engine ignores `fill_timing`, both branches produce the same
number, and the assertion fails (RED). Task 9 wires fill_timing and the
assertion becomes true.
"""

import pytest
from backtest.engine import BacktestEngine, BacktestConfig
from tests._helpers import run_backtest


def _zero_cost_config(start, end, *, fill_timing: str):
    return BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        rebalance_freq="daily",
        commission_fixed=0.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
        fill_timing=fill_timing,
    )


def _make_perfect_foresight(prices_df):
    """Return a strategy func that picks tomorrow's best performer.

    The strategy CHEATS by peeking at i+1's prices when deciding at bar i.
    Under t_close fill, this cheat is realized (engine fills at bar i's close
    of the asset that's about to win). Under t_open fill, the cheat is wasted
    (engine fills at i+1's price, by which time the peek is stale info).
    """
    def perfect_foresight(ctx, d):
        try:
            today_idx = prices_df.index.get_loc(d)
        except KeyError:
            today_idx = prices_df.index.searchsorted(d)
        if today_idx + 1 >= len(prices_df):
            return None
        today = prices_df.iloc[today_idx]
        tomorrow = prices_df.iloc[today_idx + 1]
        winner = max(prices_df.columns, key=lambda t: tomorrow[t] / today[t])
        return {t: (100.0 if t == winner else 0.0) for t in prices_df.columns}
    return perfect_foresight


def test_t_open_blunts_lookahead_compared_to_t_close(synthetic_prices):
    """Same perfect-foresight strategy under t_close vs t_open: t_close MUST
    out-return t_open by a measurable margin once t+1 fills land."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()
    strategy = _make_perfect_foresight(synthetic_prices)

    cfg_close = _zero_cost_config(start, end, fill_timing="t_close")
    cfg_open = _zero_cost_config(start, end, fill_timing="t_open")

    r_close = run_backtest(BacktestEngine(cfg_close), synthetic_prices, strategy)
    r_open = run_backtest(BacktestEngine(cfg_open), synthetic_prices, strategy)

    final_close = r_close.portfolio_values.iloc[-1]
    final_open = r_open.portfolio_values.iloc[-1]

    # 0.1% margin: enough to detect "lookahead value removed", small enough
    # to avoid false positives if t+1 itself has a tiny constant edge from
    # one-bar timing on the very first or last decision.
    assert final_close > final_open * 1.001, (
        f"Lookahead value not removed by t_open: "
        f"t_close final=${final_close:.2f}, t_open final=${final_open:.2f}"
    )


def test_t_open_fill_strictly_after_decision(synthetic_prices):
    """Under fill_timing='t_open', a rebalance trade's fill date must be
    STRICTLY AFTER the decision date that produced it."""
    start = synthetic_prices.index[0].date()
    end = synthetic_prices.index[-1].date()
    cfg = _zero_cost_config(start, end, fill_timing="t_open")
    engine = BacktestEngine(cfg)

    seen_dates = []
    def force_50_50(ctx, d):
        seen_dates.append(d)
        return {t: 50.0 for t in ctx.tickers}

    result = run_backtest(engine, synthetic_prices, force_50_50)

    rebalance_trades = [t for t in result.trades if t.date != synthetic_prices.index[0].date()]
    assert len(rebalance_trades) > 0, "no rebalance trades produced"

    first_trade = rebalance_trades[0]
    decision_dates = [d for d in seen_dates if d <= first_trade.date]
    assert decision_dates, "no decision recorded before first trade"
    decision_date = decision_dates[-1]

    assert first_trade.date > decision_date, (
        f"fill at {first_trade.date} but decision was at {decision_date} — "
        f"same-bar fill detected (fill_timing='t_open' not honored)"
    )
