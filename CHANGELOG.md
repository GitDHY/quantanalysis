# Changelog

## Unreleased — Phase 2: backtest correctness

Two fixes to `BacktestEngine.run_dynamic` that change reported numbers (in the conservative direction). Backtest results from this version onward will differ from previous runs.

### Fixed (Item 4 — cash ledger)

Transaction costs (commissions + slippage) now reduce the equity curve. Previously they were summed in `Total Trading Costs ($)` for reporting but never subtracted from `portfolio_values`, so reported Sharpe / total return ignored realistic costs.

- `BacktestResult` gains a per-bar `equity_breakdown: List[Dict[str, Any]]` ledger with `{date, total_value, cash, positions, prices}` for every bar — used by tests; useful for UI debugging.
- The rebalance loop estimates total commissions for each rebalance and shrinks `target_basis = total_value − expected_total_commission`, so cash never goes negative due to commission overhead.
- Initial purchase deducts cost from share count: `shares = (value_to_invest − cost) / price`.

Existing strategies and saved portfolios continue to work unchanged. Backtests with `commission_pct=0` and `slippage_pct=0` produce **identical** numbers to before (the cost-deduction logic is a no-op when costs are zero).

### Fixed (Item 5 — t+1 fill semantics)

Trades now fill at **the next bar's price** by default (`fill_timing="t_open"`), preventing strategies from implicitly using the close price they just decided against. Previously, a strategy that peeked at today's close (e.g. via `ctx.get_price()` returning the latest bar) could effectively trade at that same close — a subtle look-ahead that produced supernormal "free" returns in backtests.

- `BacktestConfig` gains `fill_timing: str = "t_open"` (validated values: `"t_open"`, `"t_close"`).
- Default `"t_open"` shifts the fill to the **next** bar after the rebalance decision. (For Phase 2 the fill price is the next bar's Close as a stand-in for Open — `fetch_prices` only returns adjusted Close. True next-bar Open requires routing OHLCV through the parquet cache, scheduled for Phase 4 Item 6.)
- Legacy behavior available via `BacktestConfig(fill_timing="t_close")` — produces numbers identical to pre-Phase-2 runs.
- `BacktestResult.trades[i].date` is now the **fill** date (one bar after the decision), not the decision date.

### Added (testing)

- `tests/` directory with pytest scaffolding (`pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`).
- `tests/backtest/test_baseline.py` — smoke test for `run_dynamic` with pinned values.
- `tests/backtest/test_apply_trade.py` — direct unit tests for the new `BacktestEngine._apply_trade` helper.
- `tests/backtest/test_cash_ledger.py` — correctness tests for cost-deduction and the `cash + Σ shares × price = total_value` invariant.
- `tests/backtest/test_lookahead.py` — red-team perfect-foresight test (`test_t_open_blunts_lookahead_compared_to_t_close`) ensuring a "cheating" strategy can no longer extract risk-free returns under `t_open`, plus `test_t_open_fill_strictly_after_decision` enforcing the fill-after-decision invariant.
- `tests/_helpers.py` — shared `dummy_coverage` and `run_backtest` helpers.
