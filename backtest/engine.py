"""
Backtesting engine for strategy simulation.
"""

import pandas as pd
import numpy as np
import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from config.settings import get_settings
from data.fetcher import DataFetcher, get_data_fetcher
from data.indicators import TechnicalIndicators
from backtest.cost_model import CostModel, CostConfig
from backtest.metrics import PerformanceMetrics, MetricsConfig


class RebalanceFrequency(Enum):
    """Rebalancing frequency options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class DataCoverageStatus(Enum):
    """Data coverage status for a ticker."""
    FULL = "full"           # 完全覆盖
    PARTIAL = "partial"     # 部分覆盖（数据开始时间晚于回测开始时间）
    NO_DATA = "no_data"     # 无数据


@dataclass
class TickerCoverageInfo:
    """Data coverage information for a single ticker."""
    ticker: str
    status: DataCoverageStatus
    requested_start: date
    requested_end: date
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    coverage_pct: float = 0.0
    missing_start_days: int = 0  # 开始日期前缺失的天数
    missing_end_days: int = 0    # 结束日期后缺失的天数
    trading_days_available: int = 0
    trading_days_requested: int = 0
    
    @property
    def has_full_coverage(self) -> bool:
        return self.status == DataCoverageStatus.FULL
    
    @property
    def is_usable(self) -> bool:
        return self.status != DataCoverageStatus.NO_DATA
    
    def get_status_emoji(self) -> str:
        if self.status == DataCoverageStatus.FULL:
            return "✅"
        elif self.status == DataCoverageStatus.PARTIAL:
            return "⚠️"
        else:
            return "❌"
    
    def get_status_label(self) -> str:
        if self.status == DataCoverageStatus.FULL:
            return "完整"
        elif self.status == DataCoverageStatus.PARTIAL:
            return "部分"
        else:
            return "无数据"
    
    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'status': self.status.value,
            'requested_start': self.requested_start.isoformat() if self.requested_start else None,
            'requested_end': self.requested_end.isoformat() if self.requested_end else None,
            'actual_start': self.actual_start.isoformat() if self.actual_start else None,
            'actual_end': self.actual_end.isoformat() if self.actual_end else None,
            'coverage_pct': self.coverage_pct,
            'missing_start_days': self.missing_start_days,
            'trading_days_available': self.trading_days_available,
        }


@dataclass 
class DataValidationResult:
    """Result of data coverage validation."""
    is_valid: bool                              # 是否可以进行回测
    has_warnings: bool                          # 是否有警告
    all_tickers_have_full_coverage: bool        # 所有标的是否都有完整数据
    coverage_info: Dict[str, TickerCoverageInfo]  # 每个标的的覆盖信息
    effective_start_date: Optional[date]        # 所有可用标的的共同开始日期
    effective_end_date: Optional[date]          # 所有可用标的的共同结束日期
    excluded_tickers: List[str]                 # 完全被排除的标的（无数据）
    partial_tickers: List[str]                  # 部分覆盖的标的
    full_coverage_tickers: List[str]            # 完全覆盖的标的
    warnings: List[str]                         # 警告消息列表
    
    @property
    def usable_tickers_count(self) -> int:
        return len(self.partial_tickers) + len(self.full_coverage_tickers)
    
    @property
    def total_tickers_count(self) -> int:
        return len(self.coverage_info)
    
    @property
    def has_excluded_tickers(self) -> bool:
        return len(self.excluded_tickers) > 0
    
    @property
    def has_partial_tickers(self) -> bool:
        return len(self.partial_tickers) > 0
    
    def get_severity_level(self) -> str:
        """
        获取警告严重程度：
        - 'success': 所有数据完整
        - 'warning': 有部分覆盖但可用
        - 'error': 有标的完全无数据
        - 'critical': 没有可用标的
        """
        if not self.is_valid:
            return 'critical'
        elif self.has_excluded_tickers:
            return 'error'
        elif self.has_partial_tickers:
            return 'warning'
        else:
            return 'success'
    
    def to_dict(self) -> dict:
        return {
            'is_valid': self.is_valid,
            'has_warnings': self.has_warnings,
            'effective_start_date': self.effective_start_date.isoformat() if self.effective_start_date else None,
            'effective_end_date': self.effective_end_date.isoformat() if self.effective_end_date else None,
            'excluded_tickers': self.excluded_tickers,
            'partial_tickers': self.partial_tickers,
            'full_coverage_tickers': self.full_coverage_tickers,
            'warnings': self.warnings,
            'coverage_info': {k: v.to_dict() for k, v in self.coverage_info.items()},
        }


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    start_date: date = None
    end_date: date = None
    initial_capital: float = 100000.0
    rebalance_freq: str = "monthly"
    commission_fixed: float = 0.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.001
    risk_free_rate: float = 0.03
    # 是否自动将策略返回的目标权重归一化到总和为 100%。
    # True（默认）：与历史行为一致。
    # False：按字面值使用权重，<100% 视为持现金，>100% 视为杠杆并产生警告。
    normalize_weights: bool = True
    # When does a rebalance trade fill?
    #   "t_close" (legacy): fill at the same bar's close — fast, but allows lookahead
    #   "t_open"  (default): fill at next bar's open — robust, the strategy can't see the fill price
    fill_timing: str = "t_open"
    # Pin numpy's global RNG before strategy execution so any strategy that
    # uses np.random.* gives reproducible results across runs. None (default)
    # leaves the RNG untouched (legacy behavior).
    random_seed: Optional[int] = None

    def __post_init__(self):
        if self.start_date is None:
            self.start_date = date.today() - timedelta(days=365*3)
        if self.end_date is None:
            self.end_date = date.today()
        if self.fill_timing not in ("t_open", "t_close"):
            raise ValueError(
                f"fill_timing must be 't_open' or 't_close', got {self.fill_timing!r}"
            )


@dataclass
class Trade:
    """Represents a single trade."""
    date: date
    ticker: str
    action: str  # 'BUY' or 'SELL'
    shares: float
    price: float
    value: float
    cost: float
    
    def to_dict(self) -> dict:
        return {
            'date': self.date.isoformat() if isinstance(self.date, date) else str(self.date),
            'ticker': self.ticker,
            'action': self.action,
            'shares': self.shares,
            'price': self.price,
            'value': self.value,
            'cost': self.cost,
        }


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    portfolio_values: pd.Series
    trades: List[Trade]
    metrics: Dict[str, float]
    drawdown_series: pd.Series
    weights_history: pd.DataFrame
    config: BacktestConfig
    success: bool = True
    message: str = ""
    # 数据覆盖相关字段
    data_validation: Optional[DataValidationResult] = None
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None
    # 回测期间累积的非致命警告（例如关闭归一化时目标权重 >100% 的杠杆提醒）
    warnings: List[str] = field(default_factory=list)
    # Per-step ledger snapshots: list of {date, total_value, cash, positions, prices}
    equity_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    # Reproducibility metadata: enough to verify two BacktestResults were
    # produced from the same data + library stack. Populated on success;
    # left at defaults on early-exit failure paths.
    prices_hash: str = ""
    bars_count: int = 0
    pandas_version: str = ""
    numpy_version: str = ""
    python_version: str = ""

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self.trades])
    
    @property
    def has_data_warnings(self) -> bool:
        """Check if there are any data coverage warnings."""
        return self.data_validation is not None and self.data_validation.has_warnings
    
    @property
    def data_warnings(self) -> List[str]:
        """Get data coverage warnings."""
        if self.data_validation is None:
            return []
        return self.data_validation.warnings




def _hash_prices_df(prices: pd.DataFrame) -> str:
    """MD5 hash that fingerprints a price DataFrame for reproducibility checks.

    Covers column names + order, the index timestamps, and the float values.
    Two DataFrames with the same logical content (same tickers, same bars,
    same prices) produce the same hash; any cell change produces a different
    hash. Used to populate ``BacktestResult.prices_hash``.
    """
    h = hashlib.md5()
    h.update(repr(list(prices.columns)).encode())
    h.update(np.asarray(prices.index.values).tobytes())
    h.update(prices.values.tobytes())
    return h.hexdigest()


class BacktestEngine:
    """
    Main backtesting engine.
    Supports static weight and dynamic strategy backtests.
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Initialize backtest engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        self.data_fetcher = get_data_fetcher()
        
        # Initialize cost model
        cost_config = CostConfig(
            commission_fixed=self.config.commission_fixed,
            commission_pct=self.config.commission_pct,
            slippage_pct=self.config.slippage_pct,
        )
        self.cost_model = CostModel(cost_config)
        
        # Initialize metrics calculator
        metrics_config = MetricsConfig(risk_free_rate=self.config.risk_free_rate)
        self.metrics = PerformanceMetrics(metrics_config)

    def _apply_trade(
        self,
        *,
        positions: Dict[str, float],
        cash: float,
        ticker: str,
        target_value: float,
        current_value: float,
        price: float,
    ) -> "tuple[Dict[str, float], float, float, Optional[Trade]]":
        """
        Execute one rebalancing trade and return updated (positions, cash, cost, trade).

        Cash semantics:
            Buy:  cash -= (trade_value + cost)   shares += trade_value / price
            Sell: cash += (trade_value - cost)   shares -= trade_value / price
            (trade_value here is the absolute notional moved.)

        The returned ``trade`` has ``date=None`` — the caller must overwrite it
        before appending to a ``trades`` list. ``Trade.to_dict()`` already
        tolerates non-``date`` values via ``str(self.date)``, so a missed
        overwrite degrades gracefully rather than crashing, but callers should
        still set the date for correctness.

        Returns ``(positions, cash, cost, trade_or_None)``. ``trade_or_None`` is
        ``None`` when the trade was filtered out (notional below the dust
        threshold).
        """
        trade_value_signed = target_value - current_value
        trade_value = abs(trade_value_signed)

        if trade_value < self.cost_model.config.min_trade_value:
            return positions, cash, 0.0, None

        cost = self.cost_model.calculate_total_cost(trade_value, price)
        shares = trade_value / price

        positions = dict(positions)  # don't mutate caller's dict in place
        if trade_value_signed > 0:
            positions[ticker] = positions.get(ticker, 0) + shares
            cash -= (trade_value + cost)
            action = "BUY"
        else:
            positions[ticker] = max(0, positions.get(ticker, 0) - shares)
            cash += (trade_value - cost)
            action = "SELL"

        trade = Trade(
            date=None,  # caller fills this in
            ticker=ticker,
            action=action,
            shares=shares,
            price=price,
            value=trade_value,
            cost=cost,
        )
        return positions, cash, cost, trade

    def _execute_rebalance_trades(
        self,
        *,
        positions: Dict[str, float],
        cash: float,
        total_value: float,
        position_values: Dict[str, float],
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        available: List[str],
        prices_row,  # pd.Series indexed by ticker
        trades_list: List["Trade"],
        fill_date: date,
    ) -> "tuple[Dict[str, float], float]":
        """Execute one rebalance using commission-aware target sizing.

        Phase A: estimate total commission across all tickers crossing the 1% /
            dust thresholds.
        Phase B: shrink target_basis = total_value - expected_total_commission
            (clamped at zero) so cash doesn't go negative due to commission
            overhead.
        Phase C: execute each per-ticker trade via ``_apply_trade`` and append
            to ``trades_list`` with ``fill_date``.

        Returns updated ``(positions, cash)``.
        """
        # Phase A: estimate commissions on the initial target sizing
        expected_total_commission = 0.0
        for ticker in available:
            current_w = current_weights.get(ticker, 0)
            target_w = target_weights.get(ticker, 0)
            if abs(target_w - current_w) < 1.0:
                continue
            initial_target = total_value * (target_w / 100)
            initial_current = position_values.get(ticker, 0)
            initial_trade_value = abs(initial_target - initial_current)
            if initial_trade_value < self.cost_model.config.min_trade_value:
                continue
            expected_total_commission += self.cost_model.calculate_total_cost(
                initial_trade_value, prices_row[ticker]
            )

        # Phase B: shrink target basis (no-op when commissions are 0).
        # Clamp at zero to guard against pathological commission overhead
        # exceeding equity (small bonus correctness fix).
        target_basis = max(0.0, total_value - expected_total_commission)

        # Phase C: execute trades
        for ticker in available:
            current_w = current_weights.get(ticker, 0)
            target_w = target_weights.get(ticker, 0)
            if abs(target_w - current_w) < 1.0:
                continue
            price = prices_row[ticker]
            target_value = target_basis * (target_w / 100)
            current_value = position_values.get(ticker, 0)
            positions, cash, _cost, trade = self._apply_trade(
                positions=positions,
                cash=cash,
                ticker=ticker,
                target_value=target_value,
                current_value=current_value,
                price=price,
            )
            if trade is not None:
                trade.date = fill_date
                trades_list.append(trade)

        return positions, cash

    def validate_data_coverage(
        self,
        tickers: List[str],
        start_date: date,
        end_date: date
    ) -> DataValidationResult:
        """
        验证标的在指定时间范围内的数据覆盖情况。
        
        这个方法会预先检查数据可用性，用于在回测执行前向用户显示警告。
        **重要**: 使用标的的真实成立日期（通过获取完整历史数据确定），而非仅依赖回测期间的数据。
        
        Args:
            tickers: 标的列表
            start_date: 回测开始日期
            end_date: 回测结束日期
            
        Returns:
            DataValidationResult: 包含每个标的的详细覆盖信息
        """
        warnings = []
        coverage_info = {}
        excluded_tickers = []
        partial_tickers = []
        full_coverage_tickers = []
        
        effective_start = None
        effective_end = None
        
        requested_days = (end_date - start_date).days
        
        # 获取所有标的的真实成立日期
        inception_dates = self.data_fetcher.get_tickers_inception_dates(tickers)
        
        # 获取回测期间的价格数据（用于计算覆盖率）
        prices = self.data_fetcher.fetch_prices(
            tickers,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
        )
        
        for ticker in tickers:
            inception_date = inception_dates.get(ticker)
            
            # 如果无法获取成立日期，标记为无数据
            if inception_date is None:
                info = TickerCoverageInfo(
                    ticker=ticker,
                    status=DataCoverageStatus.NO_DATA,
                    requested_start=start_date,
                    requested_end=end_date,
                    coverage_pct=0.0,
                    missing_start_days=requested_days,
                )
                coverage_info[ticker] = info
                excluded_tickers.append(ticker)
                warnings.append(f"❌ {ticker}: 无法获取成立日期，该标的将被排除")
                continue
            
            # 转换为 date 类型
            actual_start = inception_date.date() if hasattr(inception_date, 'date') else inception_date
            
            # 检查回测期间是否有数据
            has_price_data = not prices.empty and ticker in prices.columns
            if has_price_data:
                ticker_data = prices[ticker].dropna()
                has_price_data = not ticker_data.empty
            
            if not has_price_data:
                # 成立日期在回测结束日期之后
                if actual_start > end_date:
                    info = TickerCoverageInfo(
                        ticker=ticker,
                        status=DataCoverageStatus.NO_DATA,
                        requested_start=start_date,
                        requested_end=end_date,
                        actual_start=actual_start,
                        coverage_pct=0.0,
                        missing_start_days=(actual_start - start_date).days,
                    )
                    coverage_info[ticker] = info
                    excluded_tickers.append(ticker)
                    warnings.append(f"❌ {ticker}: 成立于 {actual_start.strftime('%Y-%m-%d')}，晚于回测结束日期")
                    continue
                else:
                    info = TickerCoverageInfo(
                        ticker=ticker,
                        status=DataCoverageStatus.NO_DATA,
                        requested_start=start_date,
                        requested_end=end_date,
                        actual_start=actual_start,
                        coverage_pct=0.0,
                        missing_start_days=requested_days,
                    )
                    coverage_info[ticker] = info
                    excluded_tickers.append(ticker)
                    warnings.append(f"❌ {ticker}: 在回测期间无法获取数据")
                    continue
            
            # 计算回测期间的数据范围
            ticker_data = prices[ticker].dropna()
            data_start_in_period = ticker_data.index[0].date() if hasattr(ticker_data.index[0], 'date') else ticker_data.index[0]
            actual_end = ticker_data.index[-1].date() if hasattr(ticker_data.index[-1], 'date') else ticker_data.index[-1]
            
            # 计算覆盖率
            trading_days_available = len(ticker_data)
            trading_days_total = len(prices)
            coverage_pct = (trading_days_available / max(trading_days_total, 1)) * 100
            
            # 计算缺失天数（基于真实成立日期）
            missing_start_days = max(0, (actual_start - start_date).days)
            missing_end_days = max(0, (end_date - actual_end).days)
            
            # 判断覆盖状态
            # 主要判断：成立日期是否早于或等于回测开始日期
            # 结束日期的判断要考虑数据更新延迟（如果 actual_end 接近 end_date 或在合理范围内就算完整）
            start_ok = actual_start <= start_date
            # 允许结束日期有几天的误差（数据更新延迟）或者回测结束日期在未来
            end_ok = actual_end >= end_date or (end_date - actual_end).days <= 5
            
            if start_ok and end_ok:
                status = DataCoverageStatus.FULL
            else:
                status = DataCoverageStatus.PARTIAL
            
            info = TickerCoverageInfo(
                ticker=ticker,
                status=status,
                requested_start=start_date,
                requested_end=end_date,
                actual_start=actual_start,  # 真实成立日期
                actual_end=actual_end,
                coverage_pct=min(coverage_pct, 100),
                missing_start_days=missing_start_days,
                missing_end_days=missing_end_days,
                trading_days_available=trading_days_available,
                trading_days_requested=trading_days_total,
            )
            coverage_info[ticker] = info
            
            # 分类标的
            if status == DataCoverageStatus.FULL:
                full_coverage_tickers.append(ticker)
            else:
                partial_tickers.append(ticker)
                # 生成警告消息
                if missing_start_days > 0:
                    warnings.append(
                        f"⚠️ {ticker}: 成立于 {actual_start.strftime('%Y-%m-%d')}，"
                        f"比回测开始日期晚 {missing_start_days} 天"
                    )
            
            # 更新有效日期范围
            # effective_start 应该是所有标的中最晚的成立日期（确保所有标的都有数据）
            if effective_start is None or actual_start > effective_start:
                effective_start = actual_start
            if effective_end is None or actual_end < effective_end:
                effective_end = actual_end
        
        # 判断是否可以进行回测
        usable_count = len(partial_tickers) + len(full_coverage_tickers)
        is_valid = usable_count > 0
        
        has_warnings = len(warnings) > 0
        all_full_coverage = len(excluded_tickers) == 0 and len(partial_tickers) == 0
        
        return DataValidationResult(
            is_valid=is_valid,
            has_warnings=has_warnings,
            all_tickers_have_full_coverage=all_full_coverage,
            coverage_info=coverage_info,
            effective_start_date=effective_start,
            effective_end_date=effective_end,
            excluded_tickers=excluded_tickers,
            partial_tickers=partial_tickers,
            full_coverage_tickers=full_coverage_tickers,
            warnings=warnings,
        )
    
    def _get_rebalance_dates(self, dates: pd.DatetimeIndex) -> List[pd.Timestamp]:
        """
        Get rebalancing dates based on frequency.
        
        Args:
            dates: All trading dates
            
        Returns:
            List of rebalancing dates
        """
        freq = self.config.rebalance_freq.lower()
        
        if freq == "daily":
            return list(dates)
        
        elif freq == "weekly":
            # Rebalance on Mondays (or first trading day of week)
            weekly = dates.to_series().groupby(pd.Grouper(freq='W')).first()
            return [d for d in weekly.dropna().values]
        
        elif freq == "monthly":
            # Rebalance on first trading day of month
            monthly = dates.to_series().groupby(pd.Grouper(freq='M')).first()
            return [d for d in monthly.dropna().values]
        
        elif freq == "quarterly":
            # Rebalance on first trading day of quarter
            quarterly = dates.to_series().groupby(pd.Grouper(freq='Q')).first()
            return [d for d in quarterly.dropna().values]
        
        else:
            # Default to monthly
            monthly = dates.to_series().groupby(pd.Grouper(freq='M')).first()
            return [d for d in monthly.dropna().values]
    
    def run_static(
        self,
        tickers: List[str],
        weights: Dict[str, float],
        config: Optional[BacktestConfig] = None
    ) -> BacktestResult:
        """
        Run backtest with static (buy-and-hold) weights.
        
        Args:
            tickers: List of tickers
            weights: Dictionary of ticker -> weight (percentage)
            config: Optional custom config
            
        Returns:
            BacktestResult
        """
        cfg = config or self.config
        
        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight == 0:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="Weights sum to zero",
            )
        
        norm_weights = {t: w / total_weight for t, w in weights.items()}
        
        # 先进行数据验证
        data_validation = self.validate_data_coverage(tickers, cfg.start_date, cfg.end_date)
        
        # Fetch price data
        prices = self.data_fetcher.fetch_prices(
            tickers,
            start_date=cfg.start_date.strftime('%Y-%m-%d'),
            end_date=cfg.end_date.strftime('%Y-%m-%d'),
        )
        
        if prices.empty:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="No price data available",
                data_validation=data_validation,
            )
        
        # Filter to available tickers
        available = [t for t in tickers if t in prices.columns]
        if not available:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="No valid tickers found",
                data_validation=data_validation,
            )
        
        # Recalculate weights for available tickers
        avail_weights = {t: norm_weights.get(t, 0) for t in available}
        avail_total = sum(avail_weights.values())
        if avail_total > 0:
            avail_weights = {t: w / avail_total for t, w in avail_weights.items()}
        
        # Calculate normalized prices
        norm_prices = prices[available] / prices[available].iloc[0]
        
        # Calculate portfolio value
        portfolio_value = pd.Series(0.0, index=norm_prices.index)
        for ticker in available:
            weight = avail_weights.get(ticker, 0)
            portfolio_value += norm_prices[ticker] * (cfg.initial_capital * weight)
        
        # Calculate metrics
        metrics_dict = self.metrics.calculate_all(portfolio_value)
        
        # Calculate drawdown
        drawdown = self.metrics.drawdown_series(portfolio_value)
        
        # Create weights history (static)
        weights_history = pd.DataFrame(
            {t: [avail_weights.get(t, 0) * 100] * len(norm_prices) for t in available},
            index=norm_prices.index
        )
        
        # No trades in static backtest (buy and hold)
        trades = []
        
        # 计算实际有效的开始和结束日期
        effective_start = data_validation.effective_start_date
        effective_end = data_validation.effective_end_date
        
        return BacktestResult(
            portfolio_values=portfolio_value,
            trades=trades,
            metrics=metrics_dict,
            drawdown_series=drawdown,
            weights_history=weights_history,
            config=cfg,
            success=True,
            data_validation=data_validation,
            effective_start_date=effective_start,
            effective_end_date=effective_end,
        )
    
    def run_dynamic(
        self,
        tickers: List[str],
        initial_weights: Dict[str, float],
        strategy_func: Callable,
        config: Optional[BacktestConfig] = None
    ) -> BacktestResult:
        """
        Run backtest with dynamic strategy.
        
        Args:
            tickers: List of tickers
            initial_weights: Starting weights
            strategy_func: Function that takes (context, date) and returns target weights
            config: Optional custom config
            
        Returns:
            BacktestResult
        """
        cfg = config or self.config

        # Pin numpy's global RNG so strategies that call np.random.* are
        # reproducible across runs with the same seed. None = leave alone.
        if cfg.random_seed is not None:
            np.random.seed(cfg.random_seed)

        # Normalize initial weights
        total_weight = sum(initial_weights.values())
        if total_weight == 0:
            norm_weights = {t: 100 / len(tickers) for t in tickers}
        else:
            norm_weights = {t: (w / total_weight) * 100 for t, w in initial_weights.items()}
        
        # 先进行数据验证
        data_validation = self.validate_data_coverage(tickers, cfg.start_date, cfg.end_date)
        
        # Fetch price data (with extra lookback for indicators)
        lookback_start = cfg.start_date - timedelta(days=300)
        
        prices = self.data_fetcher.fetch_prices(
            tickers,
            start_date=lookback_start.strftime('%Y-%m-%d'),
            end_date=cfg.end_date.strftime('%Y-%m-%d'),
        )
        
        if prices.empty:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="No price data available",
                data_validation=data_validation,
            )
        
        # Filter to backtest period
        backtest_prices = prices[prices.index >= pd.Timestamp(cfg.start_date)]
        
        if backtest_prices.empty:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="No data in backtest period",
                data_validation=data_validation,
            )
        
        # Filter to available tickers
        available = [t for t in tickers if t in prices.columns]
        if not available:
            return BacktestResult(
                portfolio_values=pd.Series(dtype=float),
                trades=[],
                metrics={},
                drawdown_series=pd.Series(dtype=float),
                weights_history=pd.DataFrame(),
                config=cfg,
                success=False,
                message="No valid tickers found",
                data_validation=data_validation,
            )
        
        # Get rebalancing dates
        rebalance_dates = self._get_rebalance_dates(backtest_prices.index)
        
        # Initialize tracking variables
        current_weights = {t: norm_weights.get(t, 0) for t in available}
        portfolio_values = []
        weights_history = []
        trades = []
        _backtest_warnings: list = []  # 收集非致命警告（如关闭归一化时的杠杆提醒）
        
        # Calculate initial position values
        cash = cfg.initial_capital
        positions = {t: 0.0 for t in available}  # Number of shares
        
        # Initial purchase
        first_date = backtest_prices.index[0]
        first_prices = backtest_prices.iloc[0]
        
        # Track total spent for cash residual calc below
        total_spent = 0.0

        for ticker in available:
            weight = current_weights.get(ticker, 0) / 100
            if weight > 0:
                value_to_invest = cash * weight
                price = first_prices[ticker]
                cost = self.cost_model.calculate_total_cost(value_to_invest, price)
                shares = (value_to_invest - cost) / price  # cost reduces what we can buy

                positions[ticker] = shares
                total_spent += value_to_invest  # cash outflow = allocated value (cost is implicit in fewer shares)

                trades.append(Trade(
                    date=first_date.date() if hasattr(first_date, 'date') else first_date,
                    ticker=ticker,
                    action='BUY',
                    shares=shares,
                    price=price,
                    value=value_to_invest - cost,
                    cost=cost,
                ))

        # Real cash residual: anything not allocated to a ticker stays as cash
        # (e.g., normalize_weights=False with weights summing to <100)
        cash = cash - total_spent

        equity_breakdown: List[Dict[str, Any]] = []

        # Deferred-fill state for fill_timing="t_open": a decision made at bar i
        # produces target weights that are stashed here, then executed at bar i+1.
        pending_target_weights: Optional[Dict[str, float]] = None
        pending_decision_date: Optional[date] = None

        # Simulate through time
        for idx, row in backtest_prices.iterrows():
            current_date = idx.date() if hasattr(idx, 'date') else idx
            
            # Calculate current portfolio value
            position_values = {}
            total_value = cash
            
            for ticker in available:
                if ticker in row and positions.get(ticker, 0) > 0:
                    price = row[ticker]
                    value = positions[ticker] * price
                    position_values[ticker] = value
                    total_value += value
            
            portfolio_values.append({'date': idx, 'value': total_value})

            equity_breakdown.append({
                'date': idx,
                'total_value': total_value,
                'cash': cash,
                'positions': dict(positions),
                'prices': {t: row[t] for t in available if t in row},
            })
            
            # Calculate current weights
            if total_value > 0:
                current_weights = {t: (position_values.get(t, 0) / total_value) * 100 
                                   for t in available}
            
            weights_history.append({
                'date': idx,
                **{t: current_weights.get(t, 0) for t in available}
            })

            # STAGE 1: execute deferred fill from a prior decision (t_open only).
            # The decision was made at the PREVIOUS rebalance bar using prices up to
            # that bar; the fill happens NOW at this bar's prices, using the same
            # commission-aware sizing as the legacy t_close path.
            #
            # NOTE: fill_date is set to ``idx + 1us`` so it is strictly after the
            # bar's nominal timestamp. This represents "fill at the open of this
            # bar, slightly after the prior bar's close where the decision was
            # made". It also makes Trade.date strictly greater than seen decision
            # timestamps for the same bar (where Stage 2 still records a new
            # decision after Stage 1's fill), preserving the t+1 invariant.
            if pending_target_weights is not None and cfg.fill_timing == "t_open":
                fill_ts = idx + pd.Timedelta(microseconds=1) if hasattr(idx, "__add__") else idx
                positions, cash = self._execute_rebalance_trades(
                    positions=positions,
                    cash=cash,
                    total_value=total_value,
                    position_values=position_values,
                    current_weights=current_weights,
                    target_weights=pending_target_weights,
                    available=available,
                    prices_row=row,
                    trades_list=trades,
                    fill_date=fill_ts,
                )
                # Treat current_weights as the engine's INTENT (the same way the
                # legacy t_close path does). The dust/1% filter may skip some
                # tickers so realized weights can drift slightly — that subtlety
                # is consistent with the pre-Task-9 behavior.
                current_weights = pending_target_weights
                pending_target_weights = None
                pending_decision_date = None

            # STAGE 2: decision (rebalance bar)
            if idx in rebalance_dates:
                try:
                    # Create strategy context
                    from strategy.engine import StrategyContext

                    ctx = StrategyContext(
                        tickers=available,
                        current_weights=current_weights,
                        current_date=current_date,
                        data_fetcher=self.data_fetcher,
                        lookback_days=252,
                        normalize_weights=cfg.normalize_weights,
                    )

                    # Execute strategy
                    target_weights = strategy_func(ctx, idx)

                    if target_weights is None:
                        continue

                    # Normalize target weights (conditioned on config)
                    target_total = sum(target_weights.values())
                    if cfg.normalize_weights:
                        # 历史默认行为：归一化到 100%
                        if target_total > 0:
                            target_weights = {t: (w / target_total) * 100
                                             for t, w in target_weights.items()}
                    else:
                        # 用户关闭归一化：按字面值使用
                        if target_total > 100 + 0.1:
                            warn_msg = (
                                f"⚠️ [{current_date}] 目标权重总和 "
                                f"{target_total:.1f}% > 100%，可能产生杠杆敞口"
                            )
                            _backtest_warnings.append(warn_msg)
                        elif target_total <= 0:
                            continue  # 全 0 跳过本次调仓

                    if cfg.fill_timing == "t_close":
                        # Legacy path: fill at THIS bar's prices, same bar as the decision.
                        positions, cash = self._execute_rebalance_trades(
                            positions=positions,
                            cash=cash,
                            total_value=total_value,
                            position_values=position_values,
                            current_weights=current_weights,
                            target_weights=target_weights,
                            available=available,
                            prices_row=row,
                            trades_list=trades,
                            fill_date=idx,
                        )
                        current_weights = target_weights
                    else:
                        # t_open: defer the fill to the next bar so the strategy
                        # cannot trade at prices it just looked at.
                        pending_target_weights = target_weights
                        pending_decision_date = current_date

                except Exception as e:
                    # Strategy error - continue with current weights
                    # 同时把异常记录到 warnings，便于在 UI/日志里定位"静默失败"的情况
                    try:
                        warn_msg = (
                            f"⚠️ [{current_date}] 策略执行异常，已跳过本次调仓："
                            f"{type(e).__name__}: {e}"
                        )
                        _backtest_warnings.append(warn_msg)
                    except Exception:
                        # 记录异常本身不能再抛异常影响主流程
                        pass

        # If t_open had a pending decision on the LAST bar, there is no next bar
        # to fill on. Log a warning and discard the pending weights.
        if pending_target_weights is not None:
            _backtest_warnings.append(
                f"⚠️ [{pending_decision_date}] 决策落在回测最后一根 bar，"
                f"无下一根可成交，已跳过。"
            )

        # Convert to Series/DataFrame
        values_df = pd.DataFrame(portfolio_values)
        portfolio_series = pd.Series(
            values_df['value'].values,
            index=pd.DatetimeIndex(values_df['date'])
        )
        
        weights_df = pd.DataFrame(weights_history)
        if 'date' in weights_df.columns:
            weights_df.set_index('date', inplace=True)
        
        # Calculate metrics
        metrics_dict = self.metrics.calculate_all(
            portfolio_series,
            trades=[t.to_dict() for t in trades]
        )
        
        # Calculate total costs
        total_costs = sum(t.cost for t in trades)
        metrics_dict['Total Trading Costs ($)'] = total_costs
        metrics_dict['Trade Count'] = len(trades)
        
        # Calculate drawdown
        drawdown = self.metrics.drawdown_series(portfolio_series)
        
        # 计算实际有效的开始和结束日期
        effective_start = data_validation.effective_start_date
        effective_end = data_validation.effective_end_date
        
        return BacktestResult(
            portfolio_values=portfolio_series,
            trades=trades,
            metrics=metrics_dict,
            drawdown_series=drawdown,
            weights_history=weights_df,
            config=cfg,
            success=True,
            data_validation=data_validation,
            effective_start_date=effective_start,
            effective_end_date=effective_end,
            # 杠杆/归一化相关的累积警告（仅保留前 20 条，避免过长）
            warnings=_backtest_warnings[:20],
            equity_breakdown=equity_breakdown,
            prices_hash=_hash_prices_df(backtest_prices),
            bars_count=len(backtest_prices),
            pandas_version=pd.__version__,
            numpy_version=np.__version__,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    
    def run_with_code(
        self,
        tickers: List[str],
        initial_weights: Dict[str, float],
        strategy_code: str,
        config: Optional[BacktestConfig] = None
    ) -> BacktestResult:
        """
        Run backtest with strategy code string.
        
        Args:
            tickers: List of tickers
            initial_weights: Starting weights
            strategy_code: Python strategy code
            config: Optional custom config
            
        Returns:
            BacktestResult
        """
        from strategy.engine import StrategyEngine
        
        engine = StrategyEngine()
        # 解析本地 config，便于把归一化开关透传给 StrategyEngine.execute
        # （修复：之前没传，导致策略层总是默认归一化到 100%，
        #  使得 run_dynamic 里 cfg.normalize_weights 的 if/else 两条分支输出一致）
        cfg = config or self.config
        
        def strategy_func(ctx, current_date):
            result = engine.execute(
                code=strategy_code,
                tickers=ctx.tickers,
                current_weights=ctx.get_current_weights(),
                current_date=current_date,
                normalize_weights=cfg.normalize_weights,
            )
            
            if result.success:
                return result.target_weights
            return None
        
        return self.run_dynamic(
            tickers=tickers,
            initial_weights=initial_weights,
            strategy_func=strategy_func,
            config=config,
        )
