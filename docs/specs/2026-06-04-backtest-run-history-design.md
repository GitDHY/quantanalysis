# Backtest Run History — Design Spec

- **Date:** 2026-06-04
- **Roadmap item:** Phase 5 / "#3 Backtest history + side-by-side compare"
- **Status:** Approved (this document) → next step `superpowers:writing-plans`

---

## 1. Problem

When iterating on a strategy, the only way today to know "did my last edit help or hurt?" is to remember the previous run's numbers. The existing in-session `render_multi_strategy_comparison` is transient — close the browser tab, lose everything. Without a persisted history of runs and a way to put two of them side-by-side, A/B comparison is impossible and research-loop feedback is broken.

## 2. Goals

1. **Auto-capture** every successful backtest run so the user never forgets to save.
2. **Cheap list view** that loads in milliseconds even with dozens of runs (tiered storage).
3. **Compare 2–4 runs** with overlay equity curves, side-by-side metrics, and a "what inputs differ" diff.
4. **Survive code changes**: a run captured today must remain readable next month even after the strategy in `strategies.json` is rewritten or deleted.
5. **Bounded disk footprint**: ring buffer of N (default 50) unpinned runs + unbounded pinned set.

## 3. Non-goals (YAGNI)

- Cross-device sync / cloud backup (OneDrive already syncs the whole directory).
- Full-text search, tag system, hierarchical grouping. 50 rows + sort + Ctrl-F is enough.
- Automatic "this run is a regression" detection — user picks what to compare.
- Git integration of run records.
- Performance optimization beyond the tiered-storage split (no parallel I/O, no caching layer).
- Trade-level diff between runs (the design notes it's interesting but defers to a later iteration).

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ ui/pages/backtest_page.py                                        │
│   tabs: [静态] [动态] [多策略对比] [📜 History (NEW)]           │
│         ↓ on every successful run, both static & dynamic call:  │
│              store.save(result, mode, name, strategy_code)      │
│         History tab uses store.list_summaries() / load_detail() │
│         "选 2-4 → 对比" mounts ui/components/run_compare.py     │
├─────────────────────────────────────────────────────────────────┤
│ ui/components/run_compare.py (NEW)                               │
│   render_compare(run_ids: List[str], store) — equity overlay,   │
│   metrics table, inputs diff. Pure renderer, no I/O of its own. │
├─────────────────────────────────────────────────────────────────┤
│ backtest/history.py (NEW)                                        │
│   RunHistoryStore — file-based, atomic writes, ring-buffer prune│
│   RunSummary, RunDetail dataclasses                              │
│   _hash_strategy_code(), _hash_config(), _make_run_id()         │
├─────────────────────────────────────────────────────────────────┤
│ data/runs/ (NEW)                                                 │
│   <id>.summary.json   <id>.detail.json   _meta.json             │
└─────────────────────────────────────────────────────────────────┘
```

`BacktestEngine` is **untouched** — engine stays pure, history is a UI-side concern. (Keeps engine tests independent of filesystem; preserves the option of running the engine programmatically without polluting history.)

## 5. Data contract

### 5.1 File layout

```
data/runs/
  <run_id>.summary.json      ~3 KB,  list view reads only this
  <run_id>.detail.json       ~50–200 KB, detail / compare reads this
  _meta.json                 schema_version + max_unpinned config
```

### 5.2 `run_id`

`{YYYYMMDD}T{HHMMSS}_{strategy_hash[:4]}` — e.g. `20260604T142318_a3f9`.

- Sortable as a string → ascending by time.
- Strategy-prefix collision is extremely rare; if two saves land in the same second AND the file already exists, append `_2`, `_3`, … until unique.

### 5.3 `<run_id>.summary.json`

```json
{
  "id": "20260604T142318_a3f9",
  "schema_version": 1,
  "created_at": "2026-06-04T14:23:18+00:00",
  "mode": "dynamic",
  "name": "momentum_v2",
  "note": "",
  "pinned": false,
  "metrics": { "total_return": 1.52, "sharpe": 1.42, "max_drawdown": -0.183, ... },
  "fingerprint": {
    "prices_hash": "ab12cd...",
    "code_hash": "9c3f...",
    "code_first_line": "...",
    "config_hash": "5e8a...",
    "bars_count": 2543,
    "pandas_version": "2.0.3",
    "numpy_version": "1.24.3",
    "python_version": "3.11.5"
  },
  "config": { "start_date": "2018-01-01", "end_date": "2026-05-31",
              "initial_capital": 100000.0, "rebalance_freq": "monthly",
              "commission_fixed": 0.0, "commission_pct": 0.001,
              "slippage_pct": 0.001, "fill_timing": "t_open",
              "normalize_weights": true, "random_seed": null },
  "strategy_code": "def strategy():\n    ...",
  "tickers": ["SPY", "QQQ"],
  "warnings": []
}
```

`name` defaults:

| mode      | name default                                              |
|-----------|----------------------------------------------------------|
| dynamic   | strategy's display name from `strategies.json`           |
| static    | `"static (60/40)"` etc., derived from `tickers` + weights |
| multi     | `"<strategy_name> (multi)"` per sub-run                  |

`note` is user-editable from the History tab (double-click to edit). All other fields are immutable after save.

### 5.4 `<run_id>.detail.json`

```json
{
  "id": "20260604T142318_a3f9",
  "schema_version": 1,
  "portfolio_values": { "2018-01-02": 100000.0, "2018-01-03": 100120.5, ... },
  "drawdown_series": { "2018-01-02": 0.0, ... },
  "weights_history": [ { "date": "2018-01-02", "SPY": 60.0, "QQQ": 40.0 }, ... ],
  "trades": [ { "date": "2018-01-02", "ticker": "SPY", "action": "BUY",
                "shares": 600.0, "price": 100.0, "value": 60000.0,
                "cost": 60.0 }, ... ],
  "effective_start_date": "2018-01-02",
  "effective_end_date": "2026-05-31"
}
```

`equity_breakdown` is **not** persisted — it's a debugging-only field, doesn't aid the compare view, and doubles disk usage.

### 5.5 `_meta.json`

```json
{
  "schema_version": 1,
  "max_unpinned": 50
}
```

User can edit this to change ring-buffer size. Future migration logic reads `schema_version`.

## 6. Backend API (`backtest/history.py`)

```python
@dataclass
class RunSummary:
    id: str; created_at: datetime; mode: str; name: str; note: str
    pinned: bool; metrics: Dict[str, float]
    fingerprint: Dict[str, Any]
    config: Dict[str, Any]
    tickers: List[str]
    # strategy_code, warnings excluded from RunSummary even though they're
    # in the JSON — list-page rendering doesn't need them.

@dataclass
class RunDetail:
    id: str
    portfolio_values: pd.Series
    drawdown_series: pd.Series
    weights_history: pd.DataFrame
    trades: List[Trade]
    effective_start_date: date
    effective_end_date: date

class RunHistoryStore:
    def __init__(self, runs_dir: Path | None = None,
                 max_unpinned: int | None = None): ...

    # mutators
    def save(self, result: BacktestResult, *, mode: str, name: str,
             strategy_code: str = "") -> Optional[str]:
        """Write summary + detail atomically. Auto-prune. Return run_id.
           Returns None and is a no-op when result.success is False."""
    def update_note(self, run_id: str, note: str) -> None: ...
    def pin(self, run_id: str) -> None: ...
    def unpin(self, run_id: str) -> None: ...
    def delete(self, run_id: str) -> None: ...

    # readers
    def list_summaries(self) -> List[RunSummary]:
        """All *.summary.json sorted by created_at desc.
           Skips files that fail to parse (logs a warning)."""
    def load_detail(self, run_id: str) -> RunDetail:
        """Raises FileNotFoundError if detail file is missing."""

    # internal
    def _prune(self) -> None:
        """Keep all pinned + max_unpinned most-recent unpinned. Delete the rest."""
```

Atomic writes: write to `<path>.tmp` then `os.replace(...)`. Detail is written **before** summary, so an interrupted write leaves an orphan detail (harmless, can be cleaned up by `delete()`) — never an orphan summary that can't load.

## 7. UI flow

### 7.1 History tab (4th tab on backtest page)

```
☑ ⭐ 2026-06-04 14:23  momentum_v2     Sharpe 1.42  Return +152%  📝 "baseline"
☐  ⭐ 2026-06-03 18:01  momentum_v1     Sharpe 1.30  Return +138%
☐     2026-06-02 09:14  ma_crossover    Sharpe 0.95  Return +89%
☐     2026-06-01 21:50  static          Sharpe 1.20  Return +120%
   ...

[对比选中 (2-4)]   [查看详情]   [删除选中]

共 50 个 run (3 pinned + 47 recent), 容量 8.2 MB
```

- Columns: select / pin / created_at / name / sharpe / total_return / note.
- Pin star: click toggles `pinned`.
- Note: inline-editable.
- Sort default: `created_at` desc.
- Sortable: any column header click. Sticky-headered. No filter / search bar in v1.

### 7.2 Detail view (single run)

Click a row's [查看详情] → modal-style expander on the same tab.

- Top: equity curve (single line).
- Tabs inside: `Metrics` (default) / `Trades` (lazy-loaded from detail.json) / `Weights History` (lazy) / `Config & Code` (read-only display of summary.config + strategy_code).

Layout matches the existing single-run result page so the user feels at home.

### 7.3 Compare view (2–4 runs)

```
[← 返回列表]   对比 3 个 run

┌─ Equity Curves (plotly overlay) ───────────────────────────┐
│ Run A (momentum_v2): ────                                   │
│ Run B (momentum_v1): ====                                   │
│ Run C (ma_crossover): ....                                  │
└─────────────────────────────────────────────────────────────┘

┌─ Metrics ──────────────────────────────────────────────────┐
│              Run A     Run B     Run C                     │
│ Total Ret    +152%    +138%     +89%                       │
│ CAGR         13.2%    12.4%      8.1%                      │
│ Sharpe       1.42     1.30       0.95                      │
│ Max DD      -18.3%   -19.1%    -22.5%                      │
│ Trades       87       82        134                        │
└─────────────────────────────────────────────────────────────┘

┌─ Inputs Diff (only fields that differ) ────────────────────┐
│              Run A         Run B         Run C             │
│ code_hash   ab12cd        ab12cd        xy99zz   ⚠         │
│ start_date  2018-01-01    2018-01-01    2020-01-01 ⚠       │
│ commission  0.001         0.001         0.002    ⚠         │
└─────────────────────────────────────────────────────────────┘
```

**Inputs Diff rules**:
- Compare all fields under `fingerprint` and `config`.
- Show only fields where ≥1 run differs from any other.
- A cell is highlighted iff its value doesn't match **all** other selected runs (so a 2-vs-1 split highlights all three cells, not just the minority).
- If all selected runs share `prices_hash`, hide that row (everyone agrees).
- If all share `code_hash`, hide.

### 7.4 Save trigger

Both `render_static_backtest` and `render_dynamic_backtest`, after a successful `engine.run_*` call, call:

```python
run_id = history_store.save(
    result,
    mode="static" | "dynamic",
    name=display_name,
    strategy_code=strategy_source,  # "" for static
)
```

`render_multi_strategy_comparison` calls `save` once per sub-run with `mode="multi"`.

Failure path: `result.success is False` → `store.save` returns `None`, no file written.

## 8. Edge cases

| Case | Handling |
|---|---|
| `result.success == False` | `save()` returns `None`, no files written. |
| Atomic write interrupted (process killed mid-save) | Detail written first, then summary. Worst case: orphan detail. `_prune()` and `delete()` always remove orphan detail when summary is gone. |
| Manually-deleted summary, detail still on disk | `list_summaries()` doesn't see it; orphan detail is reclaimed at next `_prune()`. |
| Manually-deleted detail, summary still on disk | List view shows the run; clicking [查看详情] surfaces a clear `FileNotFoundError` and offers a [Clean up] button that calls `delete()`. |
| Schema version mismatch | `list_summaries()` skips runs with newer `schema_version` and logs a warning; detail load raises a clear error. (No automatic migration in v1.) |
| Same-second run_id collision | After hash-prefix matching, append `_2`, `_3`, … |
| Strategy in `strategies.json` rewritten or deleted after the run | `strategy_code` is captured in the summary; history is independent. |
| User edits `_meta.json` to bad value | `RunHistoryStore.__init__` validates; falls back to defaults with a logged warning. |
| Two backtests fired in parallel from different browser tabs | Streamlit is single-thread per session; cross-session is unlikely on a personal tool. Atomic-write semantics handle the rare case (last-writer-wins on the index, no corruption per file). |

## 9. Testing

| Test | What it verifies |
|---|---|
| `test_history_save_and_load` | save → list_summaries → load_detail; all fields round-trip |
| `test_history_skips_failed_runs` | `success=False` returns `None`, no files |
| `test_history_prune_keeps_pinned` | save 100 runs, pin 5, max_unpinned=20 → list size 25 |
| `test_history_atomic_write_no_partial_summary` | monkeypatch summary write to raise → no `<id>.summary.json` exists; orphan detail OK |
| `test_history_orphan_summary_handled` | delete detail manually → load_detail raises clearly |
| `test_history_orphan_detail_pruned` | delete summary manually → next `_prune` removes detail |
| `test_compare_inputs_diff_only_shows_differing_fields` | given 3 RunSummaries, return only fields where ≥1 differs |
| `test_compare_inputs_diff_hides_unanimous_fields` | all 3 share `prices_hash` → not in diff |
| `test_run_id_collision` | same-second saves → run_ids are unique |
| `test_save_dataframe_roundtrip` | `pd.Series.to_dict()` ↔ `pd.Series(d)` preserves dtype + index |

UI integration: manual smoke test only. Streamlit's testing story is weak; ROI low for a personal tool.

## 10. Open questions / future work

- **Trade-level diff**: useful for debugging "why did this strategy fire one fewer trade?" but complex (need to align dates, classify "same trade" vs "different"). Defer.
- **Run grouping by strategy_id**: as the run count grows past 50, a "show only momentum_v2 runs" filter would help. Defer; revisit when a real user complains.
- **Walk-forward integration (#2)**: the WFA framework will produce many child runs per parent. Likely needs a `parent_run_id` field in the schema → bump `schema_version` to 2 then. Designed for that future, not implementing now.
- **Equity_breakdown re-introduction**: if compare-view ever shows per-bar position breakdowns, we'd persist it. Currently no demand.
