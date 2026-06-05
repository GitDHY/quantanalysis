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
