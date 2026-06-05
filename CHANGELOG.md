# Changelog

## Unreleased — Backtest run history (#3)

Persistent history of every backtest run + a 2–4-run side-by-side compare view.

### Added

- `backtest/history.py` — new module:
  - `RunHistoryStore` class: file-based store with atomic writes, ring-buffer pruning (default 50 unpinned + unbounded pinned), pin/note/delete mutators.
  - `RunSummary`, `RunDetail` dataclasses for the tiered storage layout.
  - Hash helpers (`_hash_strategy_code`, `_hash_config`) and `_make_run_id` with collision avoidance.
- `ui/components/run_compare.py`:
  - `compute_inputs_diff` — pure function isolating the Inputs Diff logic for unit testing.
  - `render_history_list`, `render_detail`, `render_compare` — Streamlit UIs.
- `ui/pages/backtest_page.py` — new "📜 History" 4th tab; static/dynamic/multi-strategy backtests now auto-save their `BacktestResult` to history on success (`result.success=False` runs are skipped).
- `data/runs/` — runtime directory (gitignored under existing `data/` rules) with one `<id>.summary.json` (~3KB) and one `<id>.detail.json` (~50–200KB) per run, plus `_meta.json` for global config.

### Tests

- `tests/backtest/test_history.py` (18 tests): save/list/load round-trip, skip-failed-runs, pin/unpin/note/delete, ring-buffer prune, atomic-write invariant, orphan-file handling, run_id collision.
- `tests/ui/test_run_compare.py` (5 tests): pure-function `compute_inputs_diff` cases.

### Migration

- Old runs from before this commit are not retroactively imported.
- Designed for forward compatibility with #2 (Walk-forward): a `parent_run_id` field will be added to summary's schema_version=2 when WFA produces child runs.

## Unreleased — Phase 2: backtest correctness

Two fixes to `BacktestEngine.run_dynamic` that change reported numbers (in the conservative direction). Backtest results from this version onward will differ from previous runs.

### Added (CI + reproducibility, post-Phase-2 cleanup)

- **GitHub Actions** workflow (`.github/workflows/test.yml`) runs `pytest tests/ --cov=backtest` on every push and on PRs to `main`. Replaces the vacuous "CI green" claim that existed when no CI ran at all.
- **`requirements.txt` upper-bound pins** for the dep majors that have known or likely breaking changes: `streamlit<2.0`, `pandas<2.2` (we still use the legacy `Grouper(freq='M')` codes), `numpy<2.0`, `plotly<6.0`. Header comment documents the convention.
- **`BacktestConfig.random_seed: int | None`** (default `None`). When set, `run_dynamic` calls `np.random.seed(...)` once before the rebalance loop, so any strategy that uses `np.random.*` produces byte-identical results across runs with the same seed. Doesn't affect strategies that don't use the RNG.
- **`BacktestResult` reproducibility metadata** — five new fields populated on the success path:
  - `prices_hash: str` — MD5 over the price DataFrame's columns + index + values. Use it to verify "two runs were on the same data" before comparing their numbers.
  - `bars_count: int` — `len(backtest_prices)`.
  - `pandas_version`, `numpy_version`, `python_version: str` — runtime stack snapshot.
- **Tests:**
  - `tests/backtest/test_reproducibility.py` — same seed → identical equity curve; different seeds → different equity curves.
  - `tests/backtest/test_data_snapshot.py` — fields exist and are populated; same data → same hash; single-cell change → different hash.

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
