# Changelog

## Unreleased — Phase 2: backtest correctness

Two fixes to `BacktestEngine.run_dynamic` that change reported numbers (in the conservative direction). Backtest results from this version onward will differ from previous runs.

### Fixed (Item 4 — cash ledger)

Transaction costs (commissions + slippage) now reduce the equity curve. Previously they were summed in `Total Trading Costs ($)` for reporting but never subtracted from `portfolio_values`, so reported Sharpe / total return ignored realistic costs.

- `BacktestResult` gains a per-bar `equity_breakdown: List[Dict[str, Any]]` ledger with `{date, total_value, cash, positions, prices}` for every bar — used by tests; useful for UI debugging.
- The rebalance loop estimates total commissions for each rebalance and shrinks `target_basis = total_value − expected_total_commission`, so cash never goes negative due to commission overhead.
- Initial purchase deducts cost from share count: `shares = (value_to_invest − cost) / price`.

Existing strategies and saved portfolios continue to work unchanged. Backtests with `commission_pct=0` and `slippage_pct=0` produce **identical** numbers to before (the cost-deduction logic is a no-op when costs are zero).

### Added (testing)

- `tests/` directory with pytest scaffolding (`pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`).
- `tests/backtest/test_baseline.py` — smoke test for `run_dynamic` with pinned values.
- `tests/backtest/test_apply_trade.py` — direct unit tests for the new `BacktestEngine._apply_trade` helper.
- `tests/backtest/test_cash_ledger.py` — correctness tests for cost-deduction and the `cash + Σ shares × price = total_value` invariant.
- `tests/_helpers.py` — shared `dummy_coverage` for tests that mock `validate_data_coverage`.
