"""Tests for backtest/history.py — RunHistoryStore + helpers."""

import re
from datetime import datetime
from pathlib import Path

from backtest.history import (
    RunSummary,
    RunDetail,
    RunHistoryStore,
    _hash_strategy_code,
    _hash_config,
    _make_run_id,
)


def test_module_imports_ok():
    """Smoke test: the symbols documented in the spec are importable."""
    assert RunSummary is not None
    assert RunDetail is not None
    assert RunHistoryStore is not None


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
    a = {"start_date": "2020-01-01", "end_date": "2024-12-31", "commission_pct": 0.001}
    b = {"commission_pct": 0.001, "end_date": "2024-12-31", "start_date": "2020-01-01"}
    assert _hash_config(a) == _hash_config(b)


def test_make_run_id_format(tmp_path):
    rid = _make_run_id(strategy_code="def strategy(): pass", runs_dir=tmp_path,
                       at=datetime(2026, 6, 4, 14, 23, 18))
    assert re.fullmatch(r"20260604T142318_[0-9a-f]{4}", rid), rid


def test_make_run_id_collision_appends_suffix(tmp_path):
    code = "def s(): pass"
    at = datetime(2026, 6, 4, 14, 23, 18)
    rid1 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    (tmp_path / f"{rid1}.summary.json").write_text("{}", encoding="utf-8")
    rid2 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid2 == f"{rid1}_2"
    (tmp_path / f"{rid2}.summary.json").write_text("{}", encoding="utf-8")
    rid3 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid3 == f"{rid1}_3"


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


def test_save_and_list_and_load_roundtrip(store):
    result = _make_fake_result()
    run_id = store.save(
        result, mode="dynamic", name="momentum_v2",
        strategy_code="def strategy(): return {'AAA': 50, 'BBB': 50}",
    )

    assert isinstance(run_id, str) and len(run_id) > 0

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

    detail = store.load_detail(run_id)
    pd.testing.assert_series_equal(detail.portfolio_values, result.portfolio_values,
                                   check_names=False)
    pd.testing.assert_series_equal(detail.drawdown_series, result.drawdown_series,
                                   check_names=False)
    pd.testing.assert_frame_equal(detail.weights_history, result.weights_history)
    assert len(detail.trades) == 1
    assert detail.trades[0].ticker == "AAA"
    assert detail.effective_start_date == date_t(2024, 1, 2)


def test_save_returns_none_on_failed_result(store, tmp_path):
    failed = _make_fake_result(success=False)
    rid = store.save(failed, mode="dynamic", name="x", strategy_code="")
    assert rid is None
    assert list(tmp_path.glob("*.json")) == []


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
        time.sleep(0.01)

    store.pin(ids[1])
    store._prune()

    summaries = store.list_summaries()
    surviving_ids = {s.id for s in summaries}

    assert ids[1] in surviving_ids
    assert ids[4] in surviving_ids
    assert ids[3] in surviving_ids
    assert ids[2] in surviving_ids
    assert ids[0] not in surviving_ids

    assert not (tmp_path / f"{ids[0]}.summary.json").exists()
    assert not (tmp_path / f"{ids[0]}.detail.json").exists()


def test_prune_keeps_all_when_under_limit(tmp_path):
    store = RunHistoryStore(runs_dir=tmp_path, max_unpinned=10)
    for i in range(3):
        store.save(_make_fake_result(), mode="dynamic",
                   name=f"r{i}", strategy_code=f"# {i}")
        time.sleep(0.01)
    assert len(store.list_summaries()) == 3


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

    suffixes = [str(p).split(".")[-2] for p in seen_paths]
    assert suffixes[0] == "detail" and suffixes[1] == "summary", suffixes

    assert store.list_summaries() == []


def test_orphan_summary_load_detail_raises_clearly(store, tmp_path):
    rid = store.save(_make_fake_result(), mode="dynamic", name="x",
                     strategy_code="def s(): pass")
    (tmp_path / f"{rid}.detail.json").unlink()

    assert any(s.id == rid for s in store.list_summaries())
    with pytest.raises(FileNotFoundError):
        store.load_detail(rid)


def test_orphan_detail_pruned_when_summary_deleted(store, tmp_path):
    """If the user manually deletes the summary file, the detail file
    becomes an orphan. _prune() should reclaim it on next call (e.g.
    on the next save()), per spec §8."""
    rid = store.save(_make_fake_result(), mode="dynamic", name="x",
                     strategy_code="def s(): pass")
    (tmp_path / f"{rid}.summary.json").unlink()
    assert (tmp_path / f"{rid}.detail.json").exists()  # still orphaned

    store._prune()
    assert not (tmp_path / f"{rid}.detail.json").exists()


def test_load_detail_handles_timestamp_trade_dates(store):
    """Real engine produces Trade.date as pd.Timestamp (with microsecond
    precision from t+1 fill semantics). isinstance(ts, datetime.date) is
    True for Timestamp, so Trade.to_dict() emits a full ISO datetime
    string like '2023-06-07T00:00:00.000001'. load_detail must accept
    that, not just bare 'YYYY-MM-DD'.

    Regression for the runtime ValueError seen on a real saved run:
        ValueError: Invalid isoformat string: '2023-06-07T00:00:00.000001'
    """
    result = _make_fake_result()
    # Replace the test fixture's pure-date trade with one whose date is a
    # pd.Timestamp + 1 microsecond — the exact shape produced by the
    # engine's t_open fill code (engine.py: idx + pd.Timedelta(microseconds=1)).
    ts = pd.Timestamp("2023-06-07") + pd.Timedelta(microseconds=1)
    result.trades = [Trade(date=ts, ticker="AAA", action="BUY",
                            shares=10.0, price=100.0, value=1000.0, cost=1.0)]
    rid = store.save(result, mode="dynamic", name="x",
                     strategy_code="def s(): pass")

    # Must not raise.
    detail = store.load_detail(rid)
    assert len(detail.trades) == 1
    # Engine's microsecond is fine to lose — what we want is "the day was
    # preserved" so the trade aligns with the equity curve.
    assert detail.trades[0].date.year == 2023
    assert detail.trades[0].date.month == 6
    assert detail.trades[0].date.day == 7

