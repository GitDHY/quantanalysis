# Backtest Run History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent history of backtest runs (auto-saved + ring-buffered) and a 2–4-run side-by-side comparison view inside `backtest_page`'s 4th tab.

**Architecture:** New backend module `backtest/history.py` (`RunHistoryStore`, dataclasses, helpers) writes tiered JSON files under `data/runs/`. Engine stays untouched — UI calls `store.save(result, ...)` after every successful backtest. New `ui/components/run_compare.py` renders compare and detail views. `backtest_page` gains a 4th tab with list + detail + compare flows.

**Tech Stack:** Python 3.11, pandas 2.0, Streamlit, plotly. No new third-party deps.

**Spec:** `docs/specs/2026-06-04-backtest-run-history-design.md`. Read it before starting; the data contract in §5 is normative.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `backtest/history.py` | NEW | `RunSummary`, `RunDetail` dataclasses; `RunHistoryStore` class; hash + run_id helpers |
| `tests/backtest/test_history.py` | NEW | All RunHistoryStore unit tests (Tasks 2–7) |
| `ui/components/run_compare.py` | NEW | `compute_inputs_diff()` pure function + Streamlit render functions for detail and compare views |
| `tests/ui/test_run_compare.py` | NEW | Unit tests for `compute_inputs_diff` (only pure-function tests; rendering not tested) |
| `tests/ui/__init__.py` | NEW | Empty, marks `tests/ui` as a package |
| `ui/pages/backtest_page.py` | MODIFY | Add 4th tab "📜 History"; add `store.save(...)` calls in render_static / render_dynamic / render_multi_strategy_comparison |
| `CHANGELOG.md` | MODIFY | Document the feature |
| `data/runs/` | RUNTIME | Created on first save; gitignored (already covered by `data/` rules) |

---

## Task 0: Branch setup

**Files:** none (git only).

The current branch is `phase2-backtest-correctness` with 24+ commits in PR #1. This feature is unrelated to Phase 2 backtest correctness; it should land on its own branch.

- [ ] **Step 0.1: Decide whether Phase 2 has merged**

```bash
gh pr view 1 --json state,merged --jq '{state, merged}'
```

If `merged: true` → branch from `main`:

```bash
git checkout main && git pull && git checkout -b feature/backtest-run-history
```

If `merged: false` → ask the user whether to:
- (a) wait for PR #1 to merge, then branch from `main`,
- (b) branch from `phase2-backtest-correctness` and base the new PR on PR #1.

Default to (a) unless the user chooses otherwise.

- [ ] **Step 0.2: Confirm worktree state**

```bash
git status
```

Working tree should be clean. If `data/notification_config.json` shows modified, leave it alone (intentional, see roadmap reproducibility item).

---

## Task 1: Scaffold `backtest/history.py` with dataclasses

**Files:**
- Create: `backtest/history.py`
- Create: `tests/backtest/test_history.py`

- [ ] **Step 1.1: Write a smoke import test**

`tests/backtest/test_history.py`:

```python
"""Tests for backtest/history.py — RunHistoryStore + helpers."""

from backtest.history import (
    RunSummary,
    RunDetail,
    RunHistoryStore,
)


def test_module_imports_ok():
    """Smoke test: the symbols documented in the spec are importable."""
    assert RunSummary is not None
    assert RunDetail is not None
    assert RunHistoryStore is not None
```

- [ ] **Step 1.2: Run the failing test**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: `ModuleNotFoundError: No module named 'backtest.history'`.

- [ ] **Step 1.3: Create the module skeleton**

`backtest/history.py`:

```python
"""Persisted history of backtest runs.

See docs/specs/2026-06-04-backtest-run-history-design.md for the contract.

Layout under runs_dir (default data/runs/):
  <run_id>.summary.json   — small (~3KB), list view reads only this
  <run_id>.detail.json    — large (~50–200KB), detail/compare reads this
  _meta.json              — schema_version + max_unpinned config

run_id format: YYYYMMDDTHHMMSS_<strategy_hash[:4]>, e.g. 20260604T142318_a3f9.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.engine import BacktestResult, Trade

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_MAX_UNPINNED = 50


@dataclass
class RunSummary:
    """Lightweight metadata for the list view. Mirrors <id>.summary.json
    minus the heavyweight strategy_code field."""
    id: str
    created_at: datetime
    mode: str                          # "static" | "dynamic" | "multi"
    name: str
    note: str
    pinned: bool
    metrics: Dict[str, float]
    fingerprint: Dict[str, Any]
    config: Dict[str, Any]
    tickers: List[str]


@dataclass
class RunDetail:
    """Heavy result data, loaded only on demand (compare or detail view)."""
    id: str
    portfolio_values: pd.Series        # date-indexed
    drawdown_series: pd.Series
    weights_history: pd.DataFrame
    trades: List[Trade]
    effective_start_date: Optional[date]
    effective_end_date: Optional[date]


class RunHistoryStore:
    """File-based store of backtest runs. See module docstring for layout."""

    def __init__(
        self,
        runs_dir: Optional[Path] = None,
        max_unpinned: Optional[int] = None,
    ) -> None:
        if runs_dir is None:
            from config.settings import get_settings
            runs_dir = Path(get_settings().base_dir) / "data" / "runs"
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.max_unpinned = (
            max_unpinned
            if max_unpinned is not None
            else self._read_meta().get("max_unpinned", DEFAULT_MAX_UNPINNED)
        )

    def _read_meta(self) -> Dict[str, Any]:
        path = self.runs_dir / "_meta.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("history: failed to read _meta.json: %s", e)
            return {}
```

- [ ] **Step 1.4: Run the test to verify it passes**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: PASS (1 test).

- [ ] **Step 1.5: Commit**

```bash
git add backtest/history.py tests/backtest/test_history.py
git commit -m "feat(history): scaffold backtest/history.py with dataclasses (T1)"
```

---

## Task 2: `_make_run_id` and hash helpers (TDD)

**Files:**
- Modify: `backtest/history.py` — add `_hash_strategy_code`, `_hash_config`, `_make_run_id` module functions
- Modify: `tests/backtest/test_history.py`

- [ ] **Step 2.1: Write failing tests**

Append to `tests/backtest/test_history.py`:

```python
import re
from datetime import datetime
from pathlib import Path

from backtest.history import (
    _hash_strategy_code,
    _hash_config,
    _make_run_id,
)


def test_hash_strategy_code_is_deterministic():
    code = "def strategy():\n    return None\n"
    assert _hash_strategy_code(code) == _hash_strategy_code(code)


def test_hash_strategy_code_differs_on_change():
    a = "def strategy():\n    return None\n"
    b = "def strategy():\n    return {}\n"
    assert _hash_strategy_code(a) != _hash_strategy_code(b)


def test_hash_strategy_code_empty_string_is_handled():
    h = _hash_strategy_code("")
    assert isinstance(h, str) and len(h) == 64  # sha256 hex


def test_hash_config_is_order_independent():
    # Same logical config in different dict orderings produces the same hash.
    a = {"start_date": "2020-01-01", "end_date": "2024-12-31", "commission_pct": 0.001}
    b = {"commission_pct": 0.001, "end_date": "2024-12-31", "start_date": "2020-01-01"}
    assert _hash_config(a) == _hash_config(b)


def test_make_run_id_format(tmp_path):
    rid = _make_run_id(strategy_code="def strategy(): pass", runs_dir=tmp_path,
                       at=datetime(2026, 6, 4, 14, 23, 18))
    # YYYYMMDDTHHMMSS_<4 hex>
    assert re.fullmatch(r"20260604T142318_[0-9a-f]{4}", rid), rid


def test_make_run_id_collision_appends_suffix(tmp_path):
    """Two saves that hash-prefix-collide AND happen the same second
    produce different ids by appending _2, _3, ..."""
    code = "def s(): pass"
    at = datetime(2026, 6, 4, 14, 23, 18)
    rid1 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    # Simulate the first run already on disk
    (tmp_path / f"{rid1}.summary.json").write_text("{}", encoding="utf-8")
    rid2 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid2 == f"{rid1}_2"
    (tmp_path / f"{rid2}.summary.json").write_text("{}", encoding="utf-8")
    rid3 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid3 == f"{rid1}_3"
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: 6 failures, all `ImportError: cannot import name '_hash_strategy_code'`.

- [ ] **Step 2.3: Add the helpers**

Append to `backtest/history.py` (above the `RunHistoryStore` class):

```python
def _hash_strategy_code(code: str) -> str:
    """SHA256 hex of the strategy source. '' is hashed as empty string."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _hash_config(config: Dict[str, Any]) -> str:
    """SHA256 hex of a JSON-canonicalized dict (sort_keys, default=str)."""
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _make_run_id(
    strategy_code: str,
    runs_dir: Path,
    at: Optional[datetime] = None,
) -> str:
    """Generate a unique run_id of the form YYYYMMDDTHHMMSS_<hash[:4]>.

    On collision (file with this id already on disk), append _2, _3, ...
    """
    if at is None:
        at = datetime.now()
    timestamp = at.strftime("%Y%m%dT%H%M%S")
    code_prefix = _hash_strategy_code(strategy_code)[:4]
    base = f"{timestamp}_{code_prefix}"
    candidate = base
    suffix = 2
    while (runs_dir / f"{candidate}.summary.json").exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: PASS (7 tests total).

- [ ] **Step 2.5: Commit**

```bash
git add backtest/history.py tests/backtest/test_history.py
git commit -m "feat(history): _make_run_id + hash helpers with collision handling (T2)"
```

---

## Task 3: `save` + `list_summaries` + `load_detail` round-trip (TDD)

**Files:**
- Modify: `backtest/history.py`
- Modify: `tests/backtest/test_history.py`

- [ ] **Step 3.1: Add a fixture for a fake BacktestResult**

Append to `tests/backtest/test_history.py`:

```python
import pytest
import pandas as pd
from datetime import date as date_t

from backtest.engine import BacktestResult, BacktestConfig, Trade


def _make_fake_result(success: bool = True, n_bars: int = 10) -> BacktestResult:
    idx = pd.bdate_range("2024-01-02", periods=n_bars)
    pv = pd.Series([100000.0 + i * 100 for i in range(n_bars)],
                   index=idx, name="value")
    dd = pd.Series([0.0] * n_bars, index=idx)
    weights = pd.DataFrame(
        {"AAA": [50.0] * n_bars, "BBB": [50.0] * n_bars}, index=idx
    )
    trades = [
        Trade(date=date_t(2024, 1, 2), ticker="AAA", action="BUY",
              shares=500.0, price=100.0, value=50000.0, cost=50.0),
    ]
    cfg = BacktestConfig(
        start_date=date_t(2024, 1, 2),
        end_date=date_t(2024, 1, 15),
        initial_capital=100_000.0,
        rebalance_freq="monthly",
        commission_fixed=0.0, commission_pct=0.001, slippage_pct=0.001,
    )
    return BacktestResult(
        portfolio_values=pv,
        trades=trades,
        metrics={"total_return": 0.009, "sharpe": 1.5},
        drawdown_series=dd,
        weights_history=weights,
        config=cfg,
        success=success,
        effective_start_date=date_t(2024, 1, 2),
        effective_end_date=date_t(2024, 1, 15),
        prices_hash="ab12cd",
        bars_count=n_bars,
        pandas_version="2.0.3",
        numpy_version="1.24.3",
        python_version="3.11.5",
    )


@pytest.fixture
def store(tmp_path):
    return RunHistoryStore(runs_dir=tmp_path, max_unpinned=50)
```

- [ ] **Step 3.2: Write failing round-trip test**

Append to `tests/backtest/test_history.py`:

```python
def test_save_and_list_and_load_roundtrip(store):
    result = _make_fake_result()
    run_id = store.save(
        result, mode="dynamic", name="momentum_v2",
        strategy_code="def strategy(): return {'AAA': 50, 'BBB': 50}",
    )

    # save returns an id
    assert isinstance(run_id, str) and len(run_id) > 0

    # list_summaries returns one entry, with the correct shape
    summaries = store.list_summaries()
    assert len(summaries) == 1
    s = summaries[0]
    assert s.id == run_id
    assert s.name == "momentum_v2"
    assert s.mode == "dynamic"
    assert s.note == ""
    assert s.pinned is False
    assert s.metrics == {"total_return": 0.009, "sharpe": 1.5}
    assert s.fingerprint["prices_hash"] == "ab12cd"
    assert s.fingerprint["bars_count"] == 10
    assert s.fingerprint["pandas_version"] == "2.0.3"
    assert "code_hash" in s.fingerprint
    assert "config_hash" in s.fingerprint

    # load_detail round-trips the heavy data
    detail = store.load_detail(run_id)
    pd.testing.assert_series_equal(detail.portfolio_values, result.portfolio_values)
    pd.testing.assert_series_equal(detail.drawdown_series, result.drawdown_series)
    pd.testing.assert_frame_equal(detail.weights_history, result.weights_history)
    assert len(detail.trades) == 1
    assert detail.trades[0].ticker == "AAA"
    assert detail.effective_start_date == date_t(2024, 1, 2)
```

- [ ] **Step 3.3: Run to verify it fails**

```bash
python -m pytest tests/backtest/test_history.py::test_save_and_list_and_load_roundtrip -v
```

Expected: FAIL — `RunHistoryStore` has no `save` method.

- [ ] **Step 3.4: Implement save / list_summaries / load_detail**

Add to `backtest/history.py` inside `RunHistoryStore` (replace the placeholder `_read_meta` if you put it last):

```python
    # ---------- mutators ----------

    def save(
        self,
        result: BacktestResult,
        *,
        mode: str,
        name: str,
        strategy_code: str = "",
    ) -> Optional[str]:
        """Write summary + detail atomically. Returns run_id, or None if
        result.success is False (no files written)."""
        if not result.success:
            return None

        run_id = _make_run_id(strategy_code, self.runs_dir)
        config_dict = self._config_to_dict(result.config)

        summary = {
            "id": run_id,
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now().isoformat(),
            "mode": mode,
            "name": name,
            "note": "",
            "pinned": False,
            "metrics": dict(result.metrics or {}),
            "fingerprint": {
                "prices_hash": result.prices_hash,
                "code_hash": _hash_strategy_code(strategy_code),
                "code_first_line": (strategy_code.splitlines()[0][:80]
                                     if strategy_code else ""),
                "config_hash": _hash_config(config_dict),
                "bars_count": result.bars_count,
                "pandas_version": result.pandas_version,
                "numpy_version": result.numpy_version,
                "python_version": result.python_version,
            },
            "config": config_dict,
            "strategy_code": strategy_code,
            "tickers": list(result.weights_history.columns)
                       if not result.weights_history.empty else [],
            "warnings": list(result.warnings or []),
        }

        detail = {
            "id": run_id,
            "schema_version": SCHEMA_VERSION,
            "portfolio_values": _series_to_dict(result.portfolio_values),
            "drawdown_series": _series_to_dict(result.drawdown_series),
            "weights_history": _df_to_records(result.weights_history),
            "trades": [t.to_dict() for t in (result.trades or [])],
            "effective_start_date": (result.effective_start_date.isoformat()
                                     if result.effective_start_date else None),
            "effective_end_date": (result.effective_end_date.isoformat()
                                   if result.effective_end_date else None),
        }

        # Write detail BEFORE summary so an interrupted save never leaves
        # an orphan summary that points to nothing.
        _atomic_write_json(self.runs_dir / f"{run_id}.detail.json", detail)
        _atomic_write_json(self.runs_dir / f"{run_id}.summary.json", summary)

        self._prune()
        return run_id

    # ---------- readers ----------

    def list_summaries(self) -> List[RunSummary]:
        """All *.summary.json sorted by created_at descending. Skip+log
        any file we can't parse."""
        out: List[RunSummary] = []
        for path in self.runs_dir.glob("*.summary.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("history: skipping unreadable %s: %s", path, e)
                continue
            if raw.get("schema_version", 0) > SCHEMA_VERSION:
                logger.warning("history: skipping %s — newer schema version %s",
                               path, raw.get("schema_version"))
                continue
            try:
                out.append(RunSummary(
                    id=raw["id"],
                    created_at=datetime.fromisoformat(raw["created_at"]),
                    mode=raw.get("mode", "dynamic"),
                    name=raw.get("name", ""),
                    note=raw.get("note", ""),
                    pinned=bool(raw.get("pinned", False)),
                    metrics=dict(raw.get("metrics", {})),
                    fingerprint=dict(raw.get("fingerprint", {})),
                    config=dict(raw.get("config", {})),
                    tickers=list(raw.get("tickers", [])),
                ))
            except (KeyError, ValueError) as e:
                logger.warning("history: malformed %s: %s", path, e)
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    def load_detail(self, run_id: str) -> RunDetail:
        """Read <run_id>.detail.json. Raises FileNotFoundError if missing."""
        path = self.runs_dir / f"{run_id}.detail.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunDetail(
            id=raw["id"],
            portfolio_values=_dict_to_series(raw["portfolio_values"]),
            drawdown_series=_dict_to_series(raw["drawdown_series"]),
            weights_history=_records_to_df(raw["weights_history"]),
            trades=[Trade(
                date=date_t.fromisoformat(t["date"]),
                ticker=t["ticker"], action=t["action"],
                shares=float(t["shares"]), price=float(t["price"]),
                value=float(t["value"]), cost=float(t["cost"]),
            ) for t in raw.get("trades", [])],
            effective_start_date=(date_t.fromisoformat(raw["effective_start_date"])
                                  if raw.get("effective_start_date") else None),
            effective_end_date=(date_t.fromisoformat(raw["effective_end_date"])
                                if raw.get("effective_end_date") else None),
        )

    # ---------- helpers ----------

    def _config_to_dict(self, cfg) -> Dict[str, Any]:
        """BacktestConfig → JSON-safe dict."""
        d = asdict(cfg)
        # date → ISO string
        for key in ("start_date", "end_date"):
            v = d.get(key)
            if isinstance(v, date):
                d[key] = v.isoformat()
        return d

    def _prune(self) -> None:
        """Stub — implemented in Task 6. Called from save() so it's
        wired up early; will be a no-op until Task 6 fills it in."""
        pass
```

Add the import for `date as date_t` at the top of the file:

```python
from datetime import datetime, date
date_t = date  # alias used for clarity inside JSON-decoding code
```

…and add the four module-level serialization helpers above `RunHistoryStore`:

```python
def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    """Write JSON to <path>.tmp then os.replace into place."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                              default=str), encoding="utf-8")
    os.replace(tmp, path)


def _series_to_dict(s: pd.Series) -> Dict[str, float]:
    return {
        (idx.isoformat() if hasattr(idx, "isoformat") else str(idx)): float(v)
        for idx, v in s.items()
    }


def _dict_to_series(d: Dict[str, float]) -> pd.Series:
    if not d:
        return pd.Series(dtype=float)
    keys = list(d.keys())
    idx = pd.DatetimeIndex([pd.Timestamp(k) for k in keys])
    return pd.Series([float(d[k]) for k in keys], index=idx)


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    out = []
    for ts, row in df.iterrows():
        rec = {"date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts)}
        for col in df.columns:
            rec[col] = float(row[col])
        out.append(rec)
    return out


def _records_to_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    idx = pd.DatetimeIndex([pd.Timestamp(r["date"]) for r in records])
    cols = [k for k in records[0].keys() if k != "date"]
    data = {c: [float(r[c]) for r in records] for c in cols}
    return pd.DataFrame(data, index=idx)
```

- [ ] **Step 3.5: Run the test**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: PASS (8 tests).

- [ ] **Step 3.6: Commit**

```bash
git add backtest/history.py tests/backtest/test_history.py
git commit -m "feat(history): save/list/load round-trip with tiered JSON layout (T3)"
```

---

## Task 4: Skip failed runs (TDD)

**Files:**
- Modify: `tests/backtest/test_history.py`

`save()` already returns `None` when `success=False` (Task 3). This task adds the proving test.

- [ ] **Step 4.1: Add test**

Append to `tests/backtest/test_history.py`:

```python
def test_save_returns_none_on_failed_result(store, tmp_path):
    failed = _make_fake_result(success=False)
    rid = store.save(failed, mode="dynamic", name="x", strategy_code="")
    assert rid is None
    # No JSON files written.
    assert list(tmp_path.glob("*.json")) == []
```

- [ ] **Step 4.2: Run**

```bash
python -m pytest tests/backtest/test_history.py::test_save_returns_none_on_failed_result -v
```

Expected: PASS.

- [ ] **Step 4.3: Commit**

```bash
git add tests/backtest/test_history.py
git commit -m "test(history): assert save no-ops on failed BacktestResult (T4)"
```

---

## Task 5: pin / unpin / update_note / delete (TDD)

**Files:**
- Modify: `backtest/history.py`
- Modify: `tests/backtest/test_history.py`

- [ ] **Step 5.1: Write failing tests**

Append to `tests/backtest/test_history.py`:

```python
def test_pin_unpin_round_trip(store):
    rid = store.save(_make_fake_result(), mode="dynamic", name="a",
                     strategy_code="def s(): pass")
    assert store.list_summaries()[0].pinned is False
    store.pin(rid)
    assert store.list_summaries()[0].pinned is True
    store.unpin(rid)
    assert store.list_summaries()[0].pinned is False


def test_update_note_persists(store):
    rid = store.save(_make_fake_result(), mode="dynamic", name="a",
                     strategy_code="def s(): pass")
    store.update_note(rid, "baseline run before adding RSI filter")
    assert store.list_summaries()[0].note == \
        "baseline run before adding RSI filter"


def test_delete_removes_both_files(store, tmp_path):
    rid = store.save(_make_fake_result(), mode="dynamic", name="a",
                     strategy_code="def s(): pass")
    assert (tmp_path / f"{rid}.summary.json").exists()
    assert (tmp_path / f"{rid}.detail.json").exists()
    store.delete(rid)
    assert not (tmp_path / f"{rid}.summary.json").exists()
    assert not (tmp_path / f"{rid}.detail.json").exists()
    assert store.list_summaries() == []


def test_delete_handles_missing_files(store):
    """delete is idempotent — calling it on a non-existent id is OK."""
    store.delete("nonexistent_id_xyz")  # must not raise
```

- [ ] **Step 5.2: Run to confirm RED**

```bash
python -m pytest tests/backtest/test_history.py -v -k "pin or note or delete"
```

Expected: 4 failures, AttributeError on missing methods.

- [ ] **Step 5.3: Implement**

Add inside `RunHistoryStore`:

```python
    def pin(self, run_id: str) -> None:
        self._set_summary_field(run_id, "pinned", True)

    def unpin(self, run_id: str) -> None:
        self._set_summary_field(run_id, "pinned", False)

    def update_note(self, run_id: str, note: str) -> None:
        self._set_summary_field(run_id, "note", note)

    def delete(self, run_id: str) -> None:
        for suffix in (".summary.json", ".detail.json"):
            path = self.runs_dir / f"{run_id}{suffix}"
            if path.exists():
                path.unlink()

    def _set_summary_field(self, run_id: str, field_name: str, value: Any) -> None:
        path = self.runs_dir / f"{run_id}.summary.json"
        if not path.exists():
            raise FileNotFoundError(f"no summary for run_id={run_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw[field_name] = value
        _atomic_write_json(path, raw)
```

- [ ] **Step 5.4: Run to verify GREEN**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: PASS (12+ tests).

- [ ] **Step 5.5: Commit**

```bash
git add backtest/history.py tests/backtest/test_history.py
git commit -m "feat(history): pin/unpin/update_note/delete (T5)"
```

---

## Task 6: `_prune` ring buffer (TDD)

**Files:**
- Modify: `backtest/history.py`
- Modify: `tests/backtest/test_history.py`

- [ ] **Step 6.1: Write failing test**

Append to `tests/backtest/test_history.py`:

```python
import time


def test_prune_keeps_pinned_plus_n_recent(tmp_path):
    """save N=5 with max_unpinned=3, pin one in the middle. After pruning
    we should have {pinned[1]} ∪ {3 most recent unpinned} = 4 runs.
    Oldest unpinned is dropped."""
    store = RunHistoryStore(runs_dir=tmp_path, max_unpinned=3)

    ids = []
    for i in range(5):
        rid = store.save(_make_fake_result(), mode="dynamic",
                          name=f"r{i}", strategy_code=f"# {i}\ndef s(): pass")
        ids.append(rid)
        # Force created_at to advance enough for ordering, since save()
        # uses datetime.now() at write time.
        time.sleep(0.01)

    # Pin the 2nd-oldest run.
    store.pin(ids[1])

    # _prune() is invoked from save() but we re-call it explicitly here
    # for clarity. Should be idempotent.
    store._prune()

    summaries = store.list_summaries()
    surviving_ids = {s.id for s in summaries}

    # ids[1] (pinned) survives unconditionally.
    assert ids[1] in surviving_ids
    # max_unpinned=3 → most recent 3 unpinned survive: ids[4], ids[3], ids[2]
    assert ids[4] in surviving_ids
    assert ids[3] in surviving_ids
    assert ids[2] in surviving_ids
    # ids[0] (oldest unpinned) is dropped.
    assert ids[0] not in surviving_ids

    # Files for dropped run are gone.
    assert not (tmp_path / f"{ids[0]}.summary.json").exists()
    assert not (tmp_path / f"{ids[0]}.detail.json").exists()


def test_prune_keeps_all_when_under_limit(tmp_path):
    store = RunHistoryStore(runs_dir=tmp_path, max_unpinned=10)
    for i in range(3):
        store.save(_make_fake_result(), mode="dynamic",
                   name=f"r{i}", strategy_code=f"# {i}")
        time.sleep(0.01)
    assert len(store.list_summaries()) == 3
```

- [ ] **Step 6.2: Run to confirm RED**

```bash
python -m pytest tests/backtest/test_history.py::test_prune_keeps_pinned_plus_n_recent -v
```

Expected: FAIL — currently `_prune` is a no-op so all 5 runs remain.

- [ ] **Step 6.3: Implement `_prune`**

Replace the `_prune` stub in `RunHistoryStore`:

```python
    def _prune(self) -> None:
        """Keep all pinned + max_unpinned most-recent unpinned. Delete
        the rest (both summary and detail files)."""
        all_summaries = self.list_summaries()
        unpinned = [s for s in all_summaries if not s.pinned]
        # list_summaries returns descending by created_at, so unpinned[max_unpinned:]
        # is the oldest unpinned beyond the budget.
        to_drop = unpinned[self.max_unpinned :]
        for s in to_drop:
            self.delete(s.id)
```

- [ ] **Step 6.4: Run to verify GREEN**

```bash
python -m pytest tests/backtest/test_history.py -v
```

Expected: PASS (14+ tests).

- [ ] **Step 6.5: Commit**

```bash
git add backtest/history.py tests/backtest/test_history.py
git commit -m "feat(history): _prune ring buffer keeps pinned + N most-recent (T6)"
```

---

## Task 7: Atomic write — orphan handling (TDD)

**Files:**
- Modify: `tests/backtest/test_history.py`

The atomic write is already implemented in Task 3 (`_atomic_write_json` + detail-before-summary order). This task proves the invariant.

- [ ] **Step 7.1: Write the failure-mode tests**

Append to `tests/backtest/test_history.py`:

```python
def test_save_writes_detail_before_summary(store, tmp_path, monkeypatch):
    """If summary write fails, no orphan summary on disk; detail may
    exist (orphan). The next save's _prune cleans up via list_summaries
    not seeing the orphan."""
    import backtest.history as hist

    original_atomic = hist._atomic_write_json
    seen_paths = []

    def flaky_atomic(path, obj):
        seen_paths.append(path)
        if str(path).endswith(".summary.json"):
            raise IOError("simulated disk failure")
        return original_atomic(path, obj)

    monkeypatch.setattr(hist, "_atomic_write_json", flaky_atomic)

    with pytest.raises(IOError):
        store.save(_make_fake_result(), mode="dynamic", name="x",
                   strategy_code="def s(): pass")

    # Order: detail.json was written first, then summary.json (which raised).
    suffixes = [str(p).split(".")[-2] for p in seen_paths]
    assert suffixes[0] == "detail" and suffixes[1] == "summary", suffixes

    # No summary file exists → list_summaries doesn't see the failed run.
    assert store.list_summaries() == []
    # Orphan detail might exist (acceptable).


def test_orphan_summary_load_detail_raises_clearly(store, tmp_path):
    """If the user manually deletes the detail file but not the summary,
    list_summaries still returns it (so they can clean up), and
    load_detail raises FileNotFoundError."""
    rid = store.save(_make_fake_result(), mode="dynamic", name="x",
                     strategy_code="def s(): pass")
    (tmp_path / f"{rid}.detail.json").unlink()

    assert any(s.id == rid for s in store.list_summaries())
    with pytest.raises(FileNotFoundError):
        store.load_detail(rid)


def test_orphan_detail_pruned_when_summary_deleted(store, tmp_path):
    """If the user deletes only the summary, the orphan detail is no
    longer linked from any summary. delete() reclaims it; _prune() is a
    no-op for orphans (it only sees what list_summaries returns)."""
    rid = store.save(_make_fake_result(), mode="dynamic", name="x",
                     strategy_code="def s(): pass")
    (tmp_path / f"{rid}.summary.json").unlink()

    # delete is the official cleanup path — it removes detail too.
    store.delete(rid)
    assert not (tmp_path / f"{rid}.detail.json").exists()
```

- [ ] **Step 7.2: Run**

```bash
python -m pytest tests/backtest/test_history.py -v -k "atomic or orphan"
```

Expected: PASS (3 tests). The save-order test exercises Task 3's implementation; if it fails, the bug is in Task 3 not here.

- [ ] **Step 7.3: Commit**

```bash
git add tests/backtest/test_history.py
git commit -m "test(history): atomic-write + orphan-file invariants (T7)"
```

---

## Task 8: `compute_inputs_diff` pure function (TDD)

**Files:**
- Create: `ui/components/run_compare.py`
- Create: `tests/ui/__init__.py` (empty)
- Create: `tests/ui/test_run_compare.py`

- [ ] **Step 8.1: Create empty `tests/ui/__init__.py`**

```bash
mkdir -p tests/ui && touch tests/ui/__init__.py
```

- [ ] **Step 8.2: Write failing test**

`tests/ui/test_run_compare.py`:

```python
"""Unit tests for ui/components/run_compare.py — pure logic only."""

from datetime import datetime
from backtest.history import RunSummary
from ui.components.run_compare import compute_inputs_diff


def _summary(id_: str, *, prices_hash: str, code_hash: str,
             commission_pct: float, start_date: str = "2020-01-01"):
    return RunSummary(
        id=id_,
        created_at=datetime(2026, 6, 4, 14, 23, 18),
        mode="dynamic", name=id_, note="", pinned=False,
        metrics={"sharpe": 1.0},
        fingerprint={"prices_hash": prices_hash, "code_hash": code_hash,
                     "bars_count": 100, "pandas_version": "2.0.3"},
        config={"start_date": start_date, "end_date": "2024-12-31",
                "commission_pct": commission_pct, "rebalance_freq": "monthly"},
        tickers=["SPY"],
    )


def test_inputs_diff_only_shows_differing_fields():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.002)
    diff = compute_inputs_diff([a, b])
    # commission_pct differs; everything else uniform → only commission_pct
    # appears in the diff.
    assert "commission_pct" in diff
    assert diff["commission_pct"] == [0.001, 0.002]
    assert "prices_hash" not in diff
    assert "code_hash" not in diff
    assert "rebalance_freq" not in diff


def test_inputs_diff_hides_unanimous_fields():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    c = _summary("c", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    assert compute_inputs_diff([a, b, c]) == {}


def test_inputs_diff_three_runs_two_vs_one_split():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    c = _summary("c", prices_hash="P1", code_hash="C1", commission_pct=0.002)
    diff = compute_inputs_diff([a, b, c])
    assert diff["commission_pct"] == [0.001, 0.001, 0.002]


def test_inputs_diff_handles_empty_input():
    assert compute_inputs_diff([]) == {}


def test_inputs_diff_single_run_returns_empty():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    assert compute_inputs_diff([a]) == {}
```

- [ ] **Step 8.3: Run to confirm RED**

```bash
python -m pytest tests/ui/test_run_compare.py -v
```

Expected: `ModuleNotFoundError: No module named 'ui.components.run_compare'`.

- [ ] **Step 8.4: Implement**

`ui/components/run_compare.py`:

```python
"""Render the History tab's compare view + the detail expander.

`compute_inputs_diff` is pure and unit-tested. The Streamlit render
functions are not unit-tested; verify them manually."""

from __future__ import annotations

from typing import Any, Dict, List

from backtest.history import RunSummary, RunDetail, RunHistoryStore


def compute_inputs_diff(summaries: List[RunSummary]) -> Dict[str, List[Any]]:
    """Return {field_name: [val_run0, val_run1, ...]} only for fields
    where ≥1 run differs from any other.

    Compared fields = fingerprint ∪ config. Field name preserved, value
    list ordered by `summaries` order.
    """
    if len(summaries) < 2:
        return {}

    # Collect all candidate field names from fingerprint + config.
    field_names = set()
    for s in summaries:
        field_names.update(s.fingerprint.keys())
        field_names.update(s.config.keys())

    diff: Dict[str, List[Any]] = {}
    for fname in field_names:
        values = []
        for s in summaries:
            if fname in s.fingerprint:
                values.append(s.fingerprint[fname])
            elif fname in s.config:
                values.append(s.config[fname])
            else:
                values.append(None)
        if not all(v == values[0] for v in values):
            diff[fname] = values
    return diff
```

- [ ] **Step 8.5: Run**

```bash
python -m pytest tests/ui/test_run_compare.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 8.6: Commit**

```bash
git add ui/components/run_compare.py tests/ui/__init__.py tests/ui/test_run_compare.py
git commit -m "feat(run_compare): compute_inputs_diff pure helper + tests (T8)"
```

---

## Task 9: History tab list view in `backtest_page`

**Files:**
- Modify: `ui/pages/backtest_page.py` — add 4th tab and `render_history_tab` function
- Modify: `ui/components/run_compare.py` — append `render_history_list` (Streamlit code)

- [ ] **Step 9.1: Add `render_history_list` to `run_compare.py`**

Append to `ui/components/run_compare.py`:

```python
import streamlit as st


def render_history_list(store: RunHistoryStore) -> List[str]:
    """Render the list view. Returns the list of run_ids the user
    selected via checkbox (0–N items).

    Side effects: pin/unpin/note edits/delete go through `store` directly.
    """
    summaries = store.list_summaries()
    if not summaries:
        st.info("还没有保存的回测。跑一次动态/静态回测即可自动入库。")
        return []

    n_pinned = sum(1 for s in summaries if s.pinned)
    n_recent = len(summaries) - n_pinned
    st.caption(f"共 {len(summaries)} 个 run "
               f"({n_pinned} pinned + {n_recent} recent)")

    selected_ids: List[str] = []
    for s in summaries:
        cols = st.columns([0.5, 0.4, 1.5, 1.7, 1.0, 1.0, 2.0, 0.8])
        with cols[0]:
            picked = st.checkbox("", key=f"pick_{s.id}", label_visibility="collapsed")
            if picked:
                selected_ids.append(s.id)
        with cols[1]:
            star_label = "⭐" if s.pinned else "☆"
            if st.button(star_label, key=f"pin_{s.id}", help="切换 pin"):
                if s.pinned:
                    store.unpin(s.id)
                else:
                    store.pin(s.id)
                st.rerun()
        with cols[2]:
            st.text(s.created_at.strftime("%Y-%m-%d %H:%M"))
        with cols[3]:
            st.text(s.name)
        with cols[4]:
            sharpe = s.metrics.get("sharpe_ratio") or s.metrics.get("sharpe")
            st.text(f"Sharpe {sharpe:.2f}" if sharpe is not None else "")
        with cols[5]:
            tr = s.metrics.get("total_return")
            st.text(f"{tr:+.1%}" if tr is not None else "")
        with cols[6]:
            new_note = st.text_input(
                "", value=s.note, key=f"note_{s.id}",
                label_visibility="collapsed", placeholder="备注...",
            )
            if new_note != s.note:
                store.update_note(s.id, new_note)
        with cols[7]:
            if st.button("🗑", key=f"del_{s.id}", help="删除"):
                store.delete(s.id)
                st.rerun()

    return selected_ids
```

- [ ] **Step 9.2: Wire up the 4th tab in `backtest_page.py`**

In `ui/pages/backtest_page.py`, locate `def render_backtest_page():`. Find the line that creates the existing tabs (e.g. `tab1, tab2, tab3 = st.tabs([...])`). Replace the 3-tab call with 4 tabs and add the new render call:

```python
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 静态回测", "🚀 动态策略", "🆚 多策略对比", "📜 History"
    ])
    # ... existing tab1, tab2, tab3 bodies unchanged ...
    with tab4:
        render_history_tab()
```

Add the new function near the bottom of `backtest_page.py` (above the `render_backtest_page` definition or after the existing renderers — pick whichever matches the file's existing style):

```python
def render_history_tab():
    """4th tab: persisted history of past backtest runs + compare flow."""
    from backtest.history import RunHistoryStore
    from ui.components.run_compare import render_history_list

    if "history_store" not in st.session_state:
        st.session_state.history_store = RunHistoryStore()
    store = st.session_state.history_store

    selected = render_history_list(store)
    st.divider()

    if 2 <= len(selected) <= 4:
        if st.button(f"📊 对比选中的 {len(selected)} 个", type="primary"):
            st.session_state.compare_run_ids = selected
            st.rerun()
    elif len(selected) > 4:
        st.warning(f"最多对比 4 个 (你选了 {len(selected)})")
    elif len(selected) == 1:
        st.caption("再选 1 个就能对比了")

    if st.session_state.get("compare_run_ids"):
        st.divider()
        # render_compare is added in Task 11 — placeholder for now.
        from ui.components.run_compare import render_compare
        render_compare(st.session_state.compare_run_ids, store)
        if st.button("← 返回列表"):
            del st.session_state["compare_run_ids"]
            st.rerun()
```

- [ ] **Step 9.3: Smoke import check**

```bash
python -c "import ui.pages.backtest_page; print('import OK')"
```

Expected: `import OK` (no errors). Note: importing the module doesn't render Streamlit, just confirms there are no syntax errors or top-level import problems.

If you get `ImportError: cannot import name 'render_compare'`, that's expected — Task 11 adds it. Comment out the `if st.session_state.get("compare_run_ids"):` block for now and re-add it in Task 11.

- [ ] **Step 9.4: Commit**

```bash
git add ui/pages/backtest_page.py ui/components/run_compare.py
git commit -m "feat(ui): History tab list view with pin/note/delete (T9)"
```

---

## Task 10: Detail expander

**Files:**
- Modify: `ui/components/run_compare.py` — append `render_detail`
- Modify: `ui/pages/backtest_page.py` — call from `render_history_tab` when a row is "selected for detail"

- [ ] **Step 10.1: Add `render_detail` to `run_compare.py`**

```python
def render_detail(run_id: str, store: RunHistoryStore) -> None:
    """Render a single run's detail view. Lazy-loads the detail.json."""
    summaries_by_id = {s.id: s for s in store.list_summaries()}
    summary = summaries_by_id.get(run_id)
    if summary is None:
        st.error(f"找不到 run_id={run_id}")
        return

    st.subheader(f"📊 {summary.name} — {summary.created_at:%Y-%m-%d %H:%M}")
    if summary.note:
        st.caption(f"📝 {summary.note}")

    try:
        detail = store.load_detail(run_id)
    except FileNotFoundError:
        st.error("详情文件丢失。")
        if st.button("清理这个孤立 summary"):
            store.delete(run_id)
            st.rerun()
        return

    # Equity curve
    import plotly.express as px
    fig = px.line(detail.portfolio_values, title="Equity Curve")
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Value")
    st.plotly_chart(fig, use_container_width=True)

    # Inner tabs for the heavy data
    t_metrics, t_trades, t_weights, t_config = st.tabs([
        "Metrics", "Trades", "Weights", "Config & Code"
    ])
    with t_metrics:
        st.json(summary.metrics)
    with t_trades:
        if detail.trades:
            import pandas as pd
            st.dataframe(pd.DataFrame([t.to_dict() for t in detail.trades]))
        else:
            st.caption("No trades.")
    with t_weights:
        st.dataframe(detail.weights_history)
    with t_config:
        st.write("**Config**")
        st.json(summary.config)
        st.write("**Strategy code**")
        # strategy_code lives in summary.json but RunSummary excludes it;
        # re-read raw to fetch it.
        import json
        path = store.runs_dir / f"{run_id}.summary.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        st.code(raw.get("strategy_code", ""), language="python")
```

- [ ] **Step 10.2: Wire detail into the History tab**

In `render_history_tab` in `backtest_page.py`, after `selected = render_history_list(store)` and before the compare logic, add:

```python
    # Single-row "view detail" — surfaced as a select box if one or
    # more rows are selected via checkbox.
    if len(selected) == 1:
        st.divider()
        from ui.components.run_compare import render_detail
        render_detail(selected[0], store)
```

(If both detail and compare conditions could fire, the compare path takes precedence — selected ≥ 2 → compare; selected == 1 → detail.)

- [ ] **Step 10.3: Smoke import**

```bash
python -c "import ui.pages.backtest_page; from ui.components.run_compare import render_detail; print('import OK')"
```

Expected: `import OK`.

- [ ] **Step 10.4: Commit**

```bash
git add ui/components/run_compare.py ui/pages/backtest_page.py
git commit -m "feat(ui): single-run detail expander in History tab (T10)"
```

---

## Task 11: Compare view

**Files:**
- Modify: `ui/components/run_compare.py` — append `render_compare`

- [ ] **Step 11.1: Add `render_compare`**

Append to `ui/components/run_compare.py`:

```python
def render_compare(run_ids: List[str], store: RunHistoryStore) -> None:
    """Compare 2–4 runs: equity overlay, metrics table, inputs diff."""
    summaries_by_id = {s.id: s for s in store.list_summaries()}
    summaries = [summaries_by_id[rid] for rid in run_ids
                 if rid in summaries_by_id]

    if len(summaries) < 2:
        st.warning("compare 需要至少 2 个有效 run")
        return

    st.header(f"对比 {len(summaries)} 个 run")

    # 1. Equity overlay
    st.subheader("Equity Curves")
    import plotly.graph_objects as go
    fig = go.Figure()
    for s in summaries:
        try:
            d = store.load_detail(s.id)
        except FileNotFoundError:
            st.warning(f"{s.name}: detail 文件缺失,跳过")
            continue
        fig.add_trace(go.Scatter(
            x=d.portfolio_values.index,
            y=d.portfolio_values.values,
            mode="lines",
            name=f"{s.name} ({s.id[-9:]})",
        ))
    fig.update_layout(xaxis_title=None, yaxis_title="Value", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 2. Metrics table — pivot summaries × metric names
    st.subheader("Metrics")
    import pandas as pd
    metric_keys = sorted({k for s in summaries for k in s.metrics.keys()})
    rows = {}
    for k in metric_keys:
        rows[k] = [s.metrics.get(k) for s in summaries]
    df_m = pd.DataFrame(rows, index=[f"{s.name}\n{s.id[-9:]}" for s in summaries]).T
    st.dataframe(df_m, use_container_width=True)

    # 3. Inputs Diff — only fields that differ
    st.subheader("Inputs Diff (only fields that differ)")
    diff = compute_inputs_diff(summaries)
    if not diff:
        st.success("✅ 所有输入字段一致 (prices_hash / code_hash / config 全相同)")
    else:
        diff_rows = {field_name: values for field_name, values in diff.items()}
        df_d = pd.DataFrame(
            diff_rows,
            index=[f"{s.name}\n{s.id[-9:]}" for s in summaries],
        ).T
        # Highlight differing cells: a cell highlights iff its value
        # ≠ all others in the row.
        def _highlight(row):
            return [
                "background-color: #ffe4b3" if v != row.iloc[0] or
                any(other != row.iloc[0] for other in row) else ""
                for v in row
            ]
        st.dataframe(df_d.style.apply(_highlight, axis=1),
                     use_container_width=True)
```

- [ ] **Step 11.2: Smoke import**

```bash
python -c "from ui.components.run_compare import render_compare; print('OK')"
```

Expected: `OK`.

- [ ] **Step 11.3: Commit**

```bash
git add ui/components/run_compare.py
git commit -m "feat(ui): compare view with equity overlay + metrics + Inputs Diff (T11)"
```

---

## Task 12: Save hooks in static / dynamic / multi-strategy paths

**Files:**
- Modify: `ui/pages/backtest_page.py` — `render_static_backtest`, `render_dynamic_backtest`, `render_multi_strategy_comparison` each call `store.save(...)` after a successful run

- [ ] **Step 12.1: Identify the call sites**

```bash
grep -n "engine.run_static\|engine.run_dynamic\|engine.run_with_code" ui/pages/backtest_page.py
```

There should be one call inside each of the three render functions. Each is followed by `display_backtest_results(...)` or similar.

- [ ] **Step 12.2: Add save hook in `render_static_backtest`**

Locate the line that gets a successful `result` from `engine.run_static(...)` — typically right before the existing `display_backtest_results(result, ...)` call. Add:

```python
        if result.success:
            from backtest.history import RunHistoryStore
            if "history_store" not in st.session_state:
                st.session_state.history_store = RunHistoryStore()
            # Build a human-readable name from the static config.
            tickers_str = "+".join(result.weights_history.columns[:3])
            static_name = f"static ({tickers_str})"
            st.session_state.history_store.save(
                result, mode="static", name=static_name, strategy_code="",
            )
```

- [ ] **Step 12.3: Add save hook in `render_dynamic_backtest`**

Locate the call that produces `result = engine.run_with_code(...)` (or `engine.run_dynamic(...)` — whichever the dynamic page uses). Determine the strategy display name and source code from session_state / the strategy selector. Add right before `display_backtest_results`:

```python
        if result.success:
            from backtest.history import RunHistoryStore
            if "history_store" not in st.session_state:
                st.session_state.history_store = RunHistoryStore()
            # `selected_strategy` is the StrategyEngine entry the page
            # already loaded. Adapt the variable name to whatever this
            # render function uses locally — search for "strategy_code"
            # or "strategy.code" above.
            st.session_state.history_store.save(
                result, mode="dynamic",
                name=selected_strategy.name,           # <-- adapt
                strategy_code=selected_strategy.code,  # <-- adapt
            )
```

If the variable names differ in the actual file, replace `selected_strategy.name` and `selected_strategy.code` with whatever the surrounding code uses to reference the running strategy. The point is: pass the user-visible strategy name and the full source string.

- [ ] **Step 12.4: Add save hook in `render_multi_strategy_comparison`**

This function loops over multiple strategies. Inside the loop, after each `engine.run_with_code(...)`-equivalent call:

```python
            if result.success:
                from backtest.history import RunHistoryStore
                if "history_store" not in st.session_state:
                    st.session_state.history_store = RunHistoryStore()
                st.session_state.history_store.save(
                    result, mode="multi",
                    name=f"{strategy.name} (multi)",  # adapt
                    strategy_code=strategy.code,      # adapt
                )
```

- [ ] **Step 12.5: Smoke check imports + render**

```bash
python -c "import ui.pages.backtest_page; print('OK')"
python -m pytest tests/ -q
```

Expected: import OK; all tests pass.

- [ ] **Step 12.6: Commit**

```bash
git add ui/pages/backtest_page.py
git commit -m "feat(ui): auto-save BacktestResult to history after every run (T12)"
```

---

## Task 13: CHANGELOG + final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 13.1: Append CHANGELOG entry**

In `CHANGELOG.md`, find the existing `## Unreleased — Phase 2: backtest correctness` section. Add a new section ABOVE it:

```markdown
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

- `tests/backtest/test_history.py` (~14 tests): save/list/load round-trip, skip-failed-runs, pin/unpin/note/delete, ring-buffer prune, atomic-write invariant, orphan-file handling, run_id collision.
- `tests/ui/test_run_compare.py` (5 tests): pure-function `compute_inputs_diff` cases.

### Migration

- Old runs from before this commit are not retroactively imported.
- Designed for forward compatibility with #2 (Walk-forward): a `parent_run_id` field will be added to summary's schema_version=2 when WFA produces child runs.
```

- [ ] **Step 13.2: Run the full test suite**

```bash
python -m pytest tests/ --cov=backtest --cov-report=term-missing
```

Expected: 18 (existing) + ~14 (history) + 5 (run_compare) = ~37 passing. Coverage on `backtest/history.py` should be ≥80%.

- [ ] **Step 13.3: Manual UI smoke test**

```bash
streamlit run app.py
```

Verify in the browser:
1. Backtest tab loads with 4 sub-tabs including "📜 History".
2. Run a static backtest → switch to History tab → run is listed.
3. Run a dynamic strategy → re-check History → 2 runs.
4. Edit a note inline → reload page → note persists.
5. Click ⭐ to pin a run.
6. Select 2 runs via checkbox → click "对比选中的 2 个" → compare view shows equity overlay + metrics + (probably empty) Inputs Diff.
7. Run a third backtest with a tweaked config (e.g. different `commission_pct`) → compare with prior → Inputs Diff shows `commission_pct` row highlighted.
8. Click "删除" on an old run → both files in `data/runs/` are gone.

- [ ] **Step 13.4: Final commit + push**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for backtest run history feature (T13)"
git push -u origin feature/backtest-run-history
```

- [ ] **Step 13.5: Open PR**

```bash
gh pr create --title "Backtest run history + side-by-side compare (#3)" \
  --body "$(cat <<'EOF'
Implements the spec at docs/specs/2026-06-04-backtest-run-history-design.md.

## Summary

- New backend module `backtest/history.py` with file-based `RunHistoryStore`.
- New 4th tab "📜 History" in the backtest page with list, detail, and 2–4-run compare flows.
- Auto-save every successful backtest (static / dynamic / multi-strategy each have a save hook).
- Ring-buffered to N=50 unpinned + unbounded pinned; user can pin/edit-note/delete from the UI.

## Behavior changes

None to existing flows. New tab is purely additive; engine is untouched.

## Test plan

- [ ] CI green
- [ ] Manual UI smoke (steps 1–8 from plan task 13.3)
EOF
)"
```

---

## Self-Review

**Spec coverage** — every requirement maps to a task:

| Spec section | Task |
|---|---|
| §4 Architecture (history.py + run_compare.py + backtest_page) | T1, T8, T9–T12 |
| §5.1 File layout | T3 |
| §5.2 run_id format + collision | T2 |
| §5.3 summary.json schema | T3 |
| §5.4 detail.json schema | T3 |
| §5.5 _meta.json | T1 (`_read_meta`) — `max_unpinned` reading; writing _meta.json itself isn't required for v1 (defaults are fine) |
| §6 RunHistoryStore API | T1, T3, T5, T6 |
| §7.1 List view | T9 |
| §7.2 Detail view | T10 |
| §7.3 Compare view + Inputs Diff | T8 (logic), T11 (render) |
| §7.4 Save trigger | T12 |
| §8 Edge cases | T4 (failed runs), T7 (atomic + orphans), T2 (collision); schema_version mismatch handled in T3's `list_summaries` |
| §9 Tests | T2–T8 |

**Placeholder scan:**
- T12 leaves `selected_strategy.name` / `.code` adaptable to the actual variable name in the file. This is unavoidable because I didn't read the full `render_dynamic_backtest` body — the implementer needs to name the local variable. Marked clearly in the task.
- No "TBD" / "TODO" / "fill in later" anywhere else.

**Type / signature consistency:**
- `save(...)` signature in T1 (skeleton mention) and T3 (implementation): match.
- `_atomic_write_json(path, obj)` used in T3 and referenced in T7: match.
- `compute_inputs_diff(summaries: List[RunSummary]) -> Dict[str, List[Any]]` defined in T8, used in T11: match.
- `render_compare(run_ids: List[str], store: RunHistoryStore)` defined in T11, called from T9: match.
- `RunSummary` field names used identically across T1 (definition), T3 (population), T8 (test fixture), T11 (rendering).

**Ambiguity check:**
- T12 hook variable names — flagged inline.
- T9's note-input pattern: `if new_note != s.note: store.update_note(...)` runs on every Streamlit rerun. With a fast user typing, this writes once per keystroke. Acceptable for v1 (atomic JSON writes are fast); a debounce can be added later.

No issues that would block execution.
