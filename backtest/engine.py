"""
Backtesting engine for strategy simulation.
"""

import pandas as pd
import numpy as np
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
    
    def __post_init__(self):
        if self.start_date is None:
            self.start_date = date.today() - timedelta(days=365*3)
        if self.end_date is None:
            self.end_date = date.today()


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
        
        # Calculate initial position values
        cash = cfg.initial_capital
        positions = {t: 0.0 for t in available}  # Number of shares
        
        # Initial purchase
        first_date = backtest_prices.index[0]
        first_prices = backtest_prices.iloc[0]
        
        for ticker in available:
            weight = current_weights.get(ticker, 0) / 100
            if weight > 0:
                value_to_invest = cash * weight
                price = first_prices[ticker]
                shares = value_to_invest / price
                cost = self.cost_model.calculate_total_cost(value_to_invest, price)
                
                positions[ticker] = shares
                
                trades.append(Trade(
                    date=first_date.date() if hasattr(first_date, 'date') else first_date,
                    ticker=ticker,
                    action='BUY',
                    shares=shares,
                    price=price,
                    value=value_to_invest,
                    cost=cost,
                ))
        
        cash = 0  # All invested
        
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
            
            # Calculate current weights
            if total_value > 0:
                current_weights = {t: (position_values.get(t, 0) / total_value) * 100 
                                   for t in available}
            
            weights_history.append({
                'date': idx,
                **{t: current_weights.get(t, 0) for t in available}
            })
            
            # Check if rebalancing date
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
                    )
                    
                    # Execute strategy
                    target_weights = strategy_func(ctx, current_date)
                    
                    if target_weights is None:
                        continue
                    
                    # Normalize target weights
                    target_total = sum(target_weights.values())
                    if target_total > 0:
                        target_weights = {t: (w / target_total) * 100 
                                         for t, w in target_weights.items()}
                    
                    # Execute rebalancing trades
                    for ticker in available:
                        current_w = current_weights.get(ticker, 0)
                        target_w = target_weights.get(ticker, 0)
                        
                        diff = target_w - current_w
                        
                        # Skip small changes
                        if abs(diff) < 1.0:  # Less than 1% change
                            continue
                        
                        price = row[ticker]
                        current_value = position_values.get(ticker, 0)
                        target_value = total_value * (target_w / 100)
                        trade_value = target_value - current_value
                        
                        if abs(trade_value) < 100:  # Skip tiny trades
                            continue
                        
                        # Calculate trade
                        shares_change = trade_value / price
                        cost = self.cost_model.calculate_total_cost(abs(trade_value), price)
                        
                        if trade_value > 0:  # Buy
                            positions[ticker] = positions.get(ticker, 0) + shares_change
                            action = 'BUY'
                        else:  # Sell
                            positions[ticker] = max(0, positions.get(ticker, 0) + shares_change)
                            action = 'SELL'
                        
                        trades.append(Trade(
                            date=current_date,
                            ticker=ticker,
                            action=action,
                            shares=abs(shares_change),
                            price=price,
                            value=abs(trade_value),
                            cost=cost,
                        ))
                        
                        # Deduct cost from portfolio
                        # (simplified - in reality would affect cash)
                    
                    current_weights = target_weights
                    
                except Exception as e:
                    # Strategy error - continue with current weights
                    pass
        
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
        
        def strategy_func(ctx, current_date):
            result = engine.execute(
                code=strategy_code,
                tickers=ctx.tickers,
                current_weights=ctx.get_current_weights(),
                current_date=current_date,
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
