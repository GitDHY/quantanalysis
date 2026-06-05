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


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    """Write JSON to <path>.tmp then os.replace into place."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                              default=str), encoding="utf-8")
    os.replace(tmp, path)


def _parse_iso_date(s: str) -> date:
    """Parse a date out of an ISO string permissively.

    Accepts both "YYYY-MM-DD" and full datetime strings like
    "2023-06-07T00:00:00.000001". The engine produces the latter when
    Trade.date is a pd.Timestamp (Timestamp is a subclass of
    datetime.date so isinstance() lets it through Trade.to_dict()'s
    isoformat() branch). We collapse everything to a pure date here.
    """
    return pd.Timestamp(s).date()


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
    try:
        inferred = pd.infer_freq(idx)
        if inferred:
            idx.freq = inferred
    except Exception:
        pass
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
    try:
        inferred = pd.infer_freq(idx)
        if inferred:
            idx.freq = inferred
    except Exception:
        pass
    cols = [k for k in records[0].keys() if k != "date"]
    data = {c: [float(r[c]) for r in records] for c in cols}
    return pd.DataFrame(data, index=idx)


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

    # ---------- mutators ----------

    def save(
        self,
        result: "BacktestResult",
        *,
        mode: str,
        name: str,
        strategy_code: str = "",
    ) -> Optional[str]:
        """Write summary + detail atomically. Returns run_id, or None if
        result.success is False (no files written)."""
        if not result.success:
            return None

        self._prune()  # make room BEFORE adding the new run
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

    def load_detail(self, run_id: str) -> "RunDetail":
        """Read <run_id>.detail.json. Raises FileNotFoundError if missing."""
        path = self.runs_dir / f"{run_id}.detail.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunDetail(
            id=raw["id"],
            portfolio_values=_dict_to_series(raw["portfolio_values"]),
            drawdown_series=_dict_to_series(raw["drawdown_series"]),
            weights_history=_records_to_df(raw["weights_history"]),
            trades=[Trade(
                date=_parse_iso_date(t["date"]),
                ticker=t["ticker"], action=t["action"],
                shares=float(t["shares"]), price=float(t["price"]),
                value=float(t["value"]), cost=float(t["cost"]),
            ) for t in raw.get("trades", [])],
            effective_start_date=(_parse_iso_date(raw["effective_start_date"])
                                  if raw.get("effective_start_date") else None),
            effective_end_date=(_parse_iso_date(raw["effective_end_date"])
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

    def _prune(self) -> None:
        """Keep all pinned + max_unpinned most-recent unpinned. Reclaim
        any orphan detail files (detail.json with no matching summary).

        Called from save() BEFORE adding the new run, so the on-disk
        steady state is bounded by max_unpinned + 1 between the prune
        check and the post-save state. Verified by the test suite.
        """
        all_summaries = self.list_summaries()
        unpinned = [s for s in all_summaries if not s.pinned]
        # list_summaries returns descending by created_at, so unpinned[max_unpinned:]
        # is the oldest unpinned beyond the budget.
        to_drop = unpinned[self.max_unpinned :]
        for s in to_drop:
            self.delete(s.id)

        # Reclaim orphan detail files (no matching summary on disk).
        live_summary_ids = {p.name.removesuffix(".summary.json")
                            for p in self.runs_dir.glob("*.summary.json")}
        for detail_path in self.runs_dir.glob("*.detail.json"):
            rid = detail_path.name.removesuffix(".detail.json")
            if rid not in live_summary_ids:
                detail_path.unlink()
