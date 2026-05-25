"""
Item 5: t+1 fill semantics + lookahead red-team test.

A "perfect foresight" strategy — one that picks tomorrow's best performer —
must NOT achieve super-normal returns under correct fill semantics. If it does,
the strategy is filling at the same bar it sees, which is lookahead.
"""

import pytest
from datetime import date
from unittest.mock import patch
from backtest.engine import BacktestEngine, BacktestConfig
from tests._helpers import dummy_coverage


def _run(engine, prices, strategy_func):
    with patch.object(engine.data_fetcher, "fetch_prices", return_value=prices), \
         patch.object(engine, "validate_data_coverage", return_value=dummy_coverage(prices)):
        return engine.run_dynamic(
            tickers=list(prices.columns),
            initial_weights={prices.columns[0]: 100},
            strategy_func=strategy_func,
        )


def _zero_cost_t_open(start, end):
    return BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        rebalance_freq="daily",
        commission_fixed=0.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        normalize_weights=True,
        fill_timing="t_open",
    )


def test_perfect_foresight_no_supernormal_under_t_open(synthetic_prices):
    """
    A strategy that always picks the next bar's best performer should produce
    a return roughly equal to the average of (best-of-2 next-bar return),
    NOT a return that uses today's already-known close.

    Today (t_close fill, the default the legacy engine uses) the strategy
    earns this bar's already-realized return — much higher.
    With t+1 fill (Task 9), the perfect-foresight gain is bounded by the
    next-bar realized return.

    This test is RED until Task 9 lands.
    """
    cfg = _zero_cost_t_open(
        synthetic_prices.index[0].date(),
        synthetic_prices.index[-1].date(),
    )
    engine = BacktestEngine(cfg)

    def perfect_foresight(ctx, d):
        all_prices = synthetic_prices  # closure capture for test
        try:
            today_idx = all_prices.index.get_loc(d)
        except KeyError:
            today_idx = all_prices.index.searchsorted(d)
        if today_idx + 1 >= len(all_prices):
            return None
        today = all_prices.iloc[today_idx]
        tomorrow = all_prices.iloc[today_idx + 1]
        winner = max(all_prices.columns, key=lambda t: tomorrow[t] / today[t])
        return {t: (100.0 if t == winner else 0.0) for t in all_prices.columns}

    result = _run(engine, synthetic_prices, perfect_foresight)
    final_return = (result.portfolio_values.iloc[-1] / cfg.initial_capital) - 1

    # Honest perfect-foresight ceiling: each bar earn the WINNER's NEXT-bar return
    n = len(synthetic_prices)
    rets = []
    for i in range(n - 1):
        today = synthetic_prices.iloc[i]
        tomorrow = synthetic_prices.iloc[i + 1]
        best = max(synthetic_prices.columns, key=lambda t: tomorrow[t] / today[t])
        rets.append(tomorrow[best] / today[best] - 1)
    ceiling = 1.0
    for r in rets:
        ceiling *= (1 + r)
    ceiling -= 1

    rel_err = abs(final_return - ceiling) / max(abs(ceiling), 1e-6)
    assert rel_err < 0.02, (
        f"Lookahead detected: realized {final_return*100:.2f}% vs honest "
        f"perfect-foresight ceiling {ceiling*100:.2f}% (rel err {rel_err*100:.1f}%)"
    )


def test_t_open_fill_uses_next_bar(synthetic_prices):
    """The first non-initial trade's fill must occur on a bar STRICTLY AFTER the
    decision bar, when fill_timing='t_open'."""
    cfg = _zero_cost_t_open(
        synthetic_prices.index[0].date(),
        synthetic_prices.index[-1].date(),
    )
    engine = BacktestEngine(cfg)

    seen_dates = []
    def force_50_50(ctx, d):
        seen_dates.append(d)
        return {t: 50.0 for t in ctx.tickers}

    result = _run(engine, synthetic_prices, force_50_50)

    rebalance_trades = [t for t in result.trades if t.date != synthetic_prices.index[0].date()]
    assert len(rebalance_trades) > 0, "no rebalance trades produced"

    first_trade = rebalance_trades[0]
    decision_dates = [d for d in seen_dates if d <= first_trade.date]
    assert decision_dates, "no decision recorded before first trade"
    decision_date = decision_dates[-1]

    assert first_trade.date > decision_date, (
        f"fill at {first_trade.date} but decision was at {decision_date} — "
        f"same-bar fill detected"
    )
