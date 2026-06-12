# Walk-forward / Out-of-Sample 框架 设计文档

**Status:** Draft
**Date:** 2026-06-05
**Tracking:** Roadmap item #2
**Depends on:** #3 (backtest run history) — already shipped on `feature/backtest-run-history` branch (PR #2)

---

## 1. 目标与非目标

### 1.1 目标

让用户对策略做**真正的样本外测试**:

- 用一段历史数据(IS,in-sample)优化策略参数
- 用紧邻其后的另一段数据(OOS,out-of-sample)验证最优参数的实际表现
- 多个 IS/OOS 窗口前后滚动,把每段 OOS 拼成一条完整曲线
- 头条诊断指标 — **OOS Sharpe / IS Sharpe 退化比例** — 量化策略是否过拟合

### 1.2 非目标(v1 显式不做)

- **连续参数空间**(`IntRange(20, 200, 20)` 等):v1 只支持离散 list 候选
- **Bayesian / Optuna 智能搜索**:v1 用 full grid + 200 cap 就够
- **跨窗口持仓延续**:每个 OOS 窗口独立从 `initial_capital` 起跑,通过 stitching 数学保持曲线连续
- **WFA 父子关系建模**(parent_run_id):v1 把整个 WFA 当一条 history 记录
- **异步 / 多进程**:v1 同步顺序跑,进度条实时反馈
- **OOS 重叠窗口** (`step < oos_years`):v1 强制 `step >= oos`,避免双计 bar

---

## 2. 关键设计决策

| # | 决策 | 选择 | 备选(已 reject) |
|---|---|---|---|
| 1 | WFA 范围 | Train-on-IS / Test-on-OOS(参数优化) | 仅 rolling 鲁棒性测试(无参数优化) |
| 2 | 窗口方案 | 同时支持 rolling 固定 + anchored 扩张,运行时可选 | 二选一 |
| 3 | 参数 API | 策略代码顶层 `PARAMS = {...}` 字典 + literal 限制 + UI 可窄化 | UI-only / decorator / 用户自写 schema |
| 4 | IS 优化目标 | 运行时下拉选 Sharpe / Calmar / CAGR / Sortino | 固定 Sharpe / 用户可插自定义 |
| 5 | 搜索算法 | 完全网格 + 每窗口 200 组合上限 | 随机搜索 / Bayesian |
| 6 | History 集成 | 单条记录(不引入 schema_version 升级) | 父子记录(parent_run_id, schema v2) |

---

## 3. 架构与文件布局

WFA 引擎是 `BacktestEngine.run_dynamic` 的**协调层包装**,而不是引擎扩展。这样:

- 现有动态回测路径**永不会**因为 WFA 改动而回归
- WFA 的窗口/优化循环可独立单测,不需要 mock 整个引擎
- 性能优化通过两个手术性改动达成(`run_dynamic` 加可选 `prices` 参数 + 策略 compile 缓存),不破坏调用方约定

### 3.1 新增 / 修改文件

```
backtest/
├── engine.py            (修改) — run_dynamic 加可选 prices 参数
├── walk_forward.py      (新)   — WfaConfig / WfaResult / WalkForwardEngine
├── param_grid.py        (新)   — extract_params_dict / expand_grid / WfaError
├── metrics.py           (修改) — 新增 objective_score()
└── history.py           (修改) — save_wfa() / load_wfa_detail() / WfaDetail

strategy/
└── engine.py            (修改) — StrategyContext.params 字段, execute(params=...)

ui/
├── pages/
│   └── backtest_page.py (修改) — 加第 5 个 "🚶 Walk-forward" tab
└── components/
    ├── wfa_form.py      (新)   — 启动表单
    ├── wfa_render.py    (新)   — 详情页渲染(stitched curve, 窗口表, IS-vs-OOS 退化, 参数轨迹, grid 热力图)
    └── run_compare.py   (修改) — render_history_detail 按 mode 分流到 render_wfa_detail

tests/
├── backtest/
│   ├── test_param_grid.py            (新)
│   ├── test_walk_forward_windows.py  (新)
│   ├── test_walk_forward_stitch.py   (新)
│   ├── test_walk_forward_config.py   (新)
│   ├── test_walk_forward_integration.py (新)
│   ├── test_objective.py             (新)
│   ├── test_history_wfa.py           (新)
│   └── test_engine.py                (修改) — 新增 run_dynamic prices 注入测试
└── strategy/
    └── test_engine_params.py         (新)
```

---

## 4. 数据模型

```python
@dataclass
class WfaConfig:
    """Walk-forward 配置, 与 BacktestConfig 平行。"""
    window_scheme: str = "rolling"           # "rolling" | "anchored"
    is_years: float = 3.0                    # IS 窗口长度(rolling: 固定; anchored: 起始)
    oos_years: float = 1.0                   # OOS 窗口长度
    step_years: float = 1.0                  # 每次推进; 必须 >= oos_years
    objective: str = "sharpe"                # "sharpe" | "calmar" | "cagr" | "sortino"
    search_algo: str = "grid"                # v1 仅支持 "grid"; 字段保留以备 v2 扩展
    max_combos_per_window: int = 200         # 硬上限; 超过则 WfaError
    param_overrides: Dict[str, List[Any]] = field(default_factory=dict)
                                             # 运行时缩小 PARAMS 候选; key 必须在 PARAMS 中存在

    def __post_init__(self):
        if self.window_scheme not in ("rolling", "anchored"):
            raise ValueError(f"window_scheme must be 'rolling' or 'anchored', got {self.window_scheme!r}")
        if self.objective not in ("sharpe", "calmar", "cagr", "sortino"):
            raise ValueError(f"unknown objective {self.objective!r}")
        if self.search_algo not in ("grid",):
            raise ValueError(f"v1 only supports search_algo='grid', got {self.search_algo!r}")
        if self.is_years <= 0 or self.oos_years <= 0:
            raise ValueError("is_years and oos_years must be > 0")
        if self.step_years < self.oos_years:
            raise ValueError("step_years must be >= oos_years (no overlapping OOS in v1)")
        if self.max_combos_per_window <= 0:
            raise ValueError("max_combos_per_window must be > 0")


@dataclass
class WfaWindowResult:
    """WFA 中一个 IS+OOS 窗口的结果。"""
    window_idx: int                          # 0, 1, 2, ...
    is_start: date
    is_end: date                             # IS 优化使用的最后一根 bar
    oos_start: date                          # OOS 测试的第一根 bar(在 is_end 之后)
    oos_end: date
    optimal_params: Dict[str, Any]           # IS 阶段胜出的参数组合
    is_objective_score: float                # 胜出组合在 IS 上的 objective 得分
    is_metrics: Dict[str, float]             # 胜出组合的完整 IS 指标
    oos_metrics: Dict[str, float]            # 胜出组合的完整 OOS 指标
    oos_portfolio_values: pd.Series          # OOS 曲线(rescale 前的原始值)
    oos_trades: List[Trade]                  # OOS 期间产生的交易
    oos_weights_history: pd.DataFrame
    grid_evaluations: List[Dict[str, Any]]
        # [{"params": {...}, "is_objective": float, "failed": bool, "error": str|None}, ...]
        # 每个 combo 一条; 用于热力图、近邻分析、debug


@dataclass
class WfaResult:
    """WFA 顶层结果。RunHistoryStore 用单条记录存储。"""
    config: BacktestConfig                   # 基础回测配置(commission, freq 等)
    wfa_config: WfaConfig
    windows: List[WfaWindowResult]
    stitched_oos_curve: pd.Series            # 头条结果; 跨窗口 rescale 拼接
    stitched_drawdown: pd.Series
    aggregate_metrics: Dict[str, float]      # 在 stitched_oos_curve 上计算
    success: bool = True
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    # 可复现性元数据(对齐 BacktestResult)
    prices_hash: str = ""
    bars_count: int = 0
    pandas_version: str = ""
    numpy_version: str = ""
    python_version: str = ""
```

### 4.1 字段设计要点

1. **`stitched_oos_curve` 是头条**:每窗口的 `oos_portfolio_values` 都从 `cfg.initial_capital` 起跑;stitcher 把窗口 N 的曲线 rescale 到窗口 N-1 的终点。这是"在窗口边界 refit 参数,但权益连续向前"的标准 WFA 拼接方式。
2. **`grid_evaluations` 全保留**:200 组合 × 10 窗口 × 每条小 dict ≈ 50 KB,代价低、诊断价值高。
3. **`aggregate_metrics` 复用 `PerformanceMetrics.calculate_all`**,这样 WFA 的 Sharpe / Calmar 跟普通 run 是同一个定义,可直接对比。
4. **`fingerprint.wfa_config_hash` 作为 history 的额外区分因子**:让两个相同代码 / 不同窗口方案的 WFA run 在 inputs diff 中能被识别。

---

## 5. 策略作者 API

### 5.1 策略侧契约

```python
PARAMS = {
    "lookback": [20, 60, 120],
    "threshold": [0.0, 0.05, 0.10],
}

def strategy(ctx):
    lb = ctx.params["lookback"]
    th = ctx.params["threshold"]
    sma = ctx.ma("SPY", lb)
    if ctx.get_price("SPY") > sma * (1 + th):
        ctx.set_target_weights({"SPY": 100})
    else:
        ctx.set_target_weights({"SPY": 0})
```

**规则:**

- WFA 模式下 `PARAMS` 必须存在,缺失 → `WfaError`(启动前拒绝)
- `PARAMS` 必须是**纯 literal**(数字、字符串、bool、None、list、dict、tuple);不能 `range()`、变量、函数调用 — 这是为了能用 `ast.literal_eval` 在沙箱外安全提取
- 每个值必须是非空 list
- 普通(非 WFA)回测下完全不读 `PARAMS`,声明也不影响
- 策略读未声明的 `ctx.params["x"]` → KeyError 进 `_backtest_warnings`,该 bar 跳过(走现有 strategy exception 路径)

### 5.2 PARAMS 提取(沙箱外)

`backtest/param_grid.py`:

```python
class WfaError(ValueError):
    """WFA 配置或解析错误,与运行时 sandbox 错误区分。"""

def extract_params_dict(strategy_code: str) -> Dict[str, List[Any]]:
    """从策略代码顶层提取 PARAMS dict literal。
    
    安全保证:仅用 ast.parse + ast.literal_eval, 不执行用户代码。
    """
    tree = ast.parse(strategy_code)  # SyntaxError -> WfaError
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "PARAMS"):
            val = ast.literal_eval(node.value)  # ValueError -> WfaError
            _validate_params_dict(val)
            return val
    raise WfaError("策略未声明 PARAMS")


def _validate_params_dict(d: Any) -> None:
    if not isinstance(d, dict):
        raise WfaError(...)
    for key, vals in d.items():
        if not isinstance(key, str):
            raise WfaError(...)
        if not isinstance(vals, list) or len(vals) == 0:
            raise WfaError(...)


def expand_grid(
    params: Dict[str, List[Any]],
    overrides: Dict[str, List[Any]],
    max_combos: int,
) -> List[Dict[str, Any]]:
    """生成参数组合的 Cartesian 积, 应用 overrides, 检查 cap。"""
    # 1. overrides: 只允许窄化已存在的 key
    # 2. itertools.product(*vals) 展开
    # 3. len(combos) > max_combos -> WfaError
```

### 5.3 `ctx.params` 注入(沙箱内)

修改 `strategy/engine.py`:

```python
@dataclass
class StrategyContext:
    # ... 现有字段
    params: Dict[str, Any] = field(default_factory=dict)


class StrategyEngine:
    def execute(
        self,
        code: str,
        tickers, current_weights, current_date,
        normalize_weights: bool = True,
        params: Optional[Dict[str, Any]] = None,    # 新参数
    ) -> StrategyResult:
        ctx = StrategyContext(
            ...,
            params=params or {},
        )
        # 其余不变
```

`run_with_code` 也透传 `params`,WFA 的 `_run_with_combo` 通过闭包绑定。

---

## 6. WFA 引擎主算法

### 6.1 顶层流程

```python
class WalkForwardEngine:
    def __init__(self, base_engine: BacktestEngine, wfa_config: WfaConfig):
        self.base = base_engine
        self.wfa = wfa_config

    def run(
        self,
        tickers: List[str],
        initial_weights: Dict[str, float],
        strategy_code: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> WfaResult:
        cfg = self.base.config

        # 1. 解析 PARAMS, 展开 grid (会抛 WfaError, UI 层接住)
        params_dict = extract_params_dict(strategy_code)
        combos = expand_grid(params_dict, self.wfa.param_overrides,
                             self.wfa.max_combos_per_window)

        # 2. 构造窗口列表
        windows = build_windows(cfg.start_date, cfg.end_date, self.wfa)
        if not windows:
            return WfaResult(success=False, message="数据 span 不够一个完整窗口", ...)

        # 3. 一次性拉取整段价格 (含 lookback)
        full_prices = self.base.data_fetcher.fetch_prices(
            tickers,
            start_date=(windows[0].is_start - timedelta(days=300)).strftime('%Y-%m-%d'),
            end_date=windows[-1].oos_end.strftime('%Y-%m-%d'),
        )

        # 4. 逐窗口跑 IS 优化 + OOS 运行
        window_results = []
        prev_winner = None
        warnings = []
        for w in windows:
            if progress_callback:
                progress_callback(w.idx, len(windows), f"IS 优化 ({len(combos)} combo)")
            wr, win_warns = self._run_one_window(
                w, tickers, initial_weights, strategy_code,
                combos, full_prices, prev_winner,
            )
            window_results.append(wr)
            warnings.extend(win_warns)
            prev_winner = wr.optimal_params

        # 5. Stitch + aggregate metrics
        stitched, stitched_dd = self._stitch(window_results, cfg.initial_capital)
        agg_metrics = self.base.metrics.calculate_all(stitched)

        return WfaResult(
            config=cfg, wfa_config=self.wfa, windows=window_results,
            stitched_oos_curve=stitched, stitched_drawdown=stitched_dd,
            aggregate_metrics=agg_metrics, success=True, warnings=warnings,
            prices_hash=_hash_prices_df(full_prices),
            bars_count=len(full_prices),
            pandas_version=pd.__version__, numpy_version=np.__version__,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
```

### 6.2 窗口构造

`backtest/walk_forward.py: build_windows()`:

按 calendar-day 切(对齐 `BacktestConfig.start_date` 的语义)。`is_days = int(is_years * 365)` 等。

- **Rolling 模式**:每窗口 `is_start = cursor`,`is_end = cursor + is_days - 1`,`oos_start = cursor + is_days`,`oos_end = oos_start + oos_days - 1`,`cursor += step_days`
- **Anchored 模式**:`is_start = global_start`(固定);其他与 rolling 同
- **不完整 OOS 直接丢**:`oos_end > global_end` 即终止循环
- **0 窗口情况**:返回 `[]`,WFA 直接返回 `success=False`

### 6.3 单窗口算法 (`_run_one_window`)

**IS 阶段:**

```python
for combo in combos:
    is_cfg = replace(self.base.config, start_date=window.is_start, end_date=window.is_end)
    try:
        is_result = self._run_with_combo(tickers, initial_weights, code, combo,
                                          cfg=is_cfg, prices=full_prices)
        if not is_result.success:
            grid_evals.append({"params": combo, "is_objective": -inf,
                               "failed": True, "error": is_result.message})
            continue
        score = objective_score(is_result.metrics, self.wfa.objective)
        grid_evals.append({"params": combo, "is_objective": score,
                           "failed": False, "error": None})
        is_results.append((combo, is_result, score))
    except Exception as e:
        grid_evals.append({"params": combo, "is_objective": -inf,
                           "failed": True, "error": f"{type(e).__name__}: {e}"})
```

**胜者选择:**

- 有任何成功的 IS run → 取 max objective 得分对应的 combo
- 全失败 + 有 `prev_winner` → 沿用 prev_winner,加 warning
- 全失败 + 第 0 窗口 → 抛 `WfaError`("WFA 无法启动")

**OOS 阶段:**

用胜者 combo 在 OOS 区间跑一次。如果 OOS 失败,`oos_pv = pd.Series(dtype=float)`,记 warning,stitcher 跳过该窗口。

### 6.4 Stitching 数学

```python
def _stitch(self, window_results, initial_capital) -> Tuple[pd.Series, pd.Series]:
    pieces = []
    running_end = initial_capital
    for wr in window_results:
        pv = wr.oos_portfolio_values
        if pv.empty:
            continue
        scale = running_end / pv.iloc[0]    # 让本段起点 == 上段终点
        rescaled = pv * scale
        pieces.append(rescaled)
        running_end = rescaled.iloc[-1]

    if not pieces:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    stitched = pd.concat(pieces).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep="last")]
    drawdown = self.base.metrics.drawdown_series(stitched)
    return stitched, drawdown
```

**语义:** `scale = prev_end / curr_start` 等价于"把第 N 段当作'从 prev_end 美元起步,按这段 OOS 收益率序列演化'"。简单、可解释、不需要跨窗口搬实际仓位。

### 6.5 `_run_with_combo` 胶水

```python
def _run_with_combo(self, tickers, initial_weights, code, combo, cfg, prices):
    se = StrategyEngine()

    def strategy_func(ctx, current_date):
        result = se.execute(
            code=code,
            tickers=ctx.tickers,
            current_weights=ctx.get_current_weights(),
            current_date=current_date,
            normalize_weights=cfg.normalize_weights,
            params=combo,                   # 注入当前组合
        )
        return result.target_weights if result.success else None

    return self.base.run_dynamic(
        tickers=tickers,
        initial_weights=initial_weights,
        strategy_func=strategy_func,
        config=cfg,
        prices=prices,                      # 跳过 fetch_prices
    )
```

### 6.6 引擎层手术性改动

`backtest/engine.py: BacktestEngine.run_dynamic` 加一个可选参数 `prices: Optional[pd.DataFrame] = None`:

```python
def run_dynamic(self, tickers, initial_weights, strategy_func,
                config=None, prices: Optional[pd.DataFrame] = None) -> BacktestResult:
    cfg = config or self.config
    ...
    # 数据获取
    if prices is None:
        prices = self.data_fetcher.fetch_prices(
            tickers,
            start_date=lookback_start.strftime('%Y-%m-%d'),
            end_date=cfg.end_date.strftime('%Y-%m-%d'),
        )
    # 其余完全不变
```

向后兼容:`prices is None` 时走原有路径。WFA 引擎调用时传入预 fetch 好的全段 prices。

### 6.7 Objective 评分

`backtest/metrics.py: objective_score()`:

```python
def objective_score(metrics: Dict[str, float], objective: str) -> float:
    """返回 -inf 表示失败 / 缺 metric。"""
    KEY = {
        "sharpe": "Sharpe Ratio",
        "calmar": "Calmar Ratio",
        "cagr":   "CAGR (%)",
        "sortino": "Sortino Ratio",
    }
    if objective not in KEY:
        raise WfaError(f"unknown objective {objective!r}")
    return float(metrics.get(KEY[objective], float("-inf")))
```

### 6.8 性能预估

| 项 | 量级 |
|---|---|
| 默认 grid: 3 参数 × 5 值 = 125 组合 | |
| 默认窗口数(span=10y, IS=3y, OOS=1y, step=1y) | 7-8 个 |
| 每窗口 IS+OOS 调用 | 125+1 = 126 |
| 单次 `run_dynamic` 平均(月调仓, 252×3 bar) | ~50ms |
| 全 WFA 估计时长 | ~50s |

接受。`compile cache` 是后续优化项,不进 v1。

---

## 7. Run history 集成

不升级 `schema_version`,通过加字段的方式扩展 — 与 `portfolio_name` 走的是同一套向后兼容套路。

### 7.1 `RunHistoryStore.save_wfa()`

新增方法,与 `save()` 平行(类型清晰、不做 polymorphism):

```python
def save_wfa(
    self,
    result: WfaResult,
    *,
    name: str,
    strategy_code: str = "",
    portfolio_name: str = "",
) -> Optional[str]:
    if not result.success:
        return None

    self._prune()
    run_id = _make_run_id(strategy_code, self.runs_dir)
    base_cfg_dict = self._config_to_dict(result.config)
    wfa_cfg_dict = asdict(result.wfa_config)

    summary = {
        "id": run_id,
        "schema_version": SCHEMA_VERSION,            # 仍是 1
        "created_at": datetime.now().isoformat(),
        "mode": "wfa",                                # 新 mode 值
        "name": name,
        "note": "",
        "pinned": False,
        "portfolio_name": portfolio_name,
        "metrics": dict(result.aggregate_metrics or {}),
        "fingerprint": {
            "prices_hash": result.prices_hash,
            "code_hash": _hash_strategy_code(strategy_code),
            "code_first_line": (strategy_code.splitlines()[0][:80]
                                 if strategy_code else ""),
            "config_hash": _hash_config(base_cfg_dict),
            "wfa_config_hash": _hash_config(wfa_cfg_dict),    # 新字段
            "bars_count": result.bars_count,
            "pandas_version": result.pandas_version,
            "numpy_version": result.numpy_version,
            "python_version": result.python_version,
        },
        "config": base_cfg_dict,
        "wfa_config": wfa_cfg_dict,
        "strategy_code": strategy_code,
        "tickers": _extract_tickers_from_windows(result.windows),
        "warnings": list(result.warnings or []),
        "wfa_summary": {                              # 给 list 视图用
            "n_windows": len(result.windows),
            "is_years": result.wfa_config.is_years,
            "oos_years": result.wfa_config.oos_years,
            "window_scheme": result.wfa_config.window_scheme,
            "objective": result.wfa_config.objective,
            "n_combos_per_window": (
                len(result.windows[0].grid_evaluations) if result.windows else 0
            ),
        },
    }

    detail = {
        "id": run_id,
        "schema_version": SCHEMA_VERSION,
        "portfolio_values": _series_to_dict(result.stitched_oos_curve),
        "drawdown_series": _series_to_dict(result.stitched_drawdown),
        "weights_history": [],         # WFA 没有"全局"weights, 实际数据在 wfa.windows[*]
        "trades": [],                  # 同上
        "effective_start_date": result.windows[0].oos_start.isoformat() if result.windows else None,
        "effective_end_date": result.windows[-1].oos_end.isoformat() if result.windows else None,
        "wfa": {                        # 新加 WFA 专属 block
            "wfa_config": wfa_cfg_dict,
            "windows": [_window_to_dict(w) for w in result.windows],
        },
    }

    _atomic_write_json(self.runs_dir / f"{run_id}.detail.json", detail)
    _atomic_write_json(self.runs_dir / f"{run_id}.summary.json", summary)
    return run_id
```

### 7.2 `RunSummary` dataclass 改动

新增可选字段(对老 summary.json 向后兼容):

```python
@dataclass
class RunSummary:
    # ... 现有字段
    portfolio_name: str = ""
    wfa_summary: Optional[Dict[str, Any]] = None     # 新加; 非 WFA run 为 None
```

`list_summaries()` 解析时容错读 `raw.get("wfa_summary")`,缺失即 None。

### 7.3 `WfaDetail` + `load_wfa_detail()`

新增并行 dataclass + loader,而不是塞进现有 `RunDetail`(后者的 trades/weights 在 WFA 里是空的,会让消费者代码混乱):

```python
@dataclass
class WfaDetail:
    id: str
    stitched_curve: pd.Series
    stitched_drawdown: pd.Series
    wfa_config: WfaConfig
    windows: List[WfaWindowResult]
```

UI 层根据 `summary.mode` 分流到 `load_detail` 或 `load_wfa_detail`。

### 7.4 `_prune` 行为

不区分 mode,WFA run 也走 `pinned + max_unpinned 最近` 的同一套淘汰规则。**有意保持** — 用户的心智模型保持一致(在意就 pin)。

### 7.5 自动入库钩子

WFA 跑成功 → `store.save_wfa(result, name, strategy_code, portfolio_name)`,与现有 static / dynamic / multi 三处钩子风格一致。失败时 `st.warning("已完成,但保存到历史失败: {e}")`。

---

## 8. UI 渲染

### 8.1 启动表单 (`ui/components/wfa_form.py`)

新 tab "🚶 Walk-forward",和现有 4 个 tab 平行。

布局自上而下:**组合选择 → 策略选择 → 回测期间 → WFA 配置 → 参数搜索空间 → 开始按钮**

关键 UX 行为:

- **PARAMS 实时反射**:选完策略后,立即用 `extract_params_dict` 读取 PARAMS,渲染候选列表,用户可勾选窄化(等价 `param_overrides`)。策略未声明 PARAMS → 显示红字 + 禁用启动按钮。
- **总组合数 + 估计时长预览**:`n_windows × n_combos × ~50ms`。`combos > max_combos` 时直接禁按钮 + 报错。
- **窗口数 live 重算**:用户改 IS/OOS/step 时,前端立即用 `build_windows()` 给出窗口数,避免"配完了才发现 0 窗口"。
- **Step 默认 = OOS**:用户没主动改 step 时跟着 OOS 走;改了 OOS 也同步;用户改了 step 后不再自动。

### 8.2 运行进度

`WalkForwardEngine.run` 接受 `progress_callback: Callable[[int, int, str], None]`。UI 层用 `st.progress` + `st.empty()` 同步反馈,不开后台线程(与现有同步执行风格一致)。

### 8.3 结果详情页 (`render_wfa_detail`)

自上而下五区块:

1. **Stitched OOS Equity Curve**(头条 + 虚线分割窗口边界)
2. **Aggregate (OOS) Metrics**:Sharpe / CAGR / Max DD / Calmar
3. **退化诊断指标**:`OOS Sharpe / IS Sharpe = 0.42` 这种核心数字
4. **窗口详情(内嵌 4 tab)**:
   - **窗口表**:N 行 × `[idx, IS 区间, OOS 区间, 最优参数, IS 分数, OOS Sharpe]`
   - **IS vs OOS 退化**:每窗口双柱 bar chart
   - **参数轨迹**:每参数一条 line(x=窗口 idx,y=最优值)
   - **Grid 热力图**:选窗口 → 渲染该窗口 grid_evaluations 热力图(2 参数)或 parallel coordinates(3+ 参数)
5. **Config & Code**(展开式)

### 8.4 Compare 视图

完全复用现有 `render_compare`(equity overlay + metrics 透视表 + inputs diff)。WFA 的 `stitched_oos_curve` 与普通 run 的 `portfolio_values` 都是 date-indexed series,直接可叠;metrics 都是同一套 PerformanceMetrics 输出,直接可比较。`fingerprint.wfa_config_hash` 让 inputs diff 能 surface 出"WFA vs 普通"的差异。**不需要改 `compute_inputs_diff` 逻辑。**

### 8.5 Streamlit 状态管理

`st.session_state["wfa_last_result"]` 缓存结果,key = `(strategy_id, base_config_hash, wfa_config_hash, param_overrides_hash)`。用户切 tab 不重跑,改任何输入后失效。复用现有 backtest_page 的 caching 模式。

### 8.6 视觉一致

复用现有 widget / 调色板 / 卡片样式;只引入一个新 emoji `🚶`(WFA 标识)。新 component 文件控制在 2 个(`wfa_form.py` + `wfa_render.py`)。

---

## 9. 测试策略

### 9.1 总体目标

- ~35-40 个新测试 case
- 新增模块覆盖率 ≥ 80%(WFA 是核心算法,值得高覆盖)
- CI 时长增量 ≤ 5s(集成测试用合成数据)

### 9.2 单元测试清单

#### `tests/backtest/test_param_grid.py` (~14 test)

- `extract_params_dict`:基础 / 缺失 / 非 literal / 非 dict / 空 list / 非 str key / 语法错 / 非顶层
- `expand_grid`:Cartesian 正确 / 单参数 / overrides 窄化 / 未知 key / 超 cap / 类型保持

#### `tests/backtest/test_walk_forward_windows.py` (~6 test)

- Rolling 简单 / Anchored 简单 / 不完整 OOS 丢弃 / 不够一窗返回空 / step > oos / Anchored IS 长度递增

#### `tests/backtest/test_walk_forward_stitch.py` (~5 test)

- 双窗口连续性 / 单窗口 passthrough / 空窗口跳过 / 全空返回空 / drawdown 基于拼接曲线计算

#### `tests/backtest/test_walk_forward_config.py` (~5 test)

- 默认值 / 非法 scheme / step<oos / is_years=0 / 未知 objective

#### `tests/backtest/test_objective.py` (~6 test)

- Sharpe / Calmar / CAGR / Sortino / 缺 key 返回 -inf / 未知 raise

#### `tests/strategy/test_engine_params.py` (~3 test)

- 注入 ctx.params / 默认空 / 策略读未知 key 进 error 不杀回测

### 9.3 集成测试

#### `tests/backtest/test_walk_forward_integration.py` (~6 test)

- 端到端合成数据 / random_seed 可复现 / 首窗口全失败 raise / 后续窗口全失败用 fallback / OOS 失败记 warning / progress_callback 调用次数

#### `tests/backtest/test_history_wfa.py` (~8 test)

- save_wfa 返回 run_id / mode=="wfa" / wfa_summary block / detail.wfa block / load_wfa_detail roundtrip / 老 summary 兼容 / 失败返回 None / WFA + 普通 run 共存

### 9.4 关键 invariant 测试

- Stitched 曲线起点 == initial_capital
- Stitched 曲线在窗口边界连续
- 窗口 idx 严格递增
- Rolling 模式所有窗口 IS 长度相同
- Anchored 模式所有窗口 IS_start 相同
- fallback 不污染当前窗口的 grid_evaluations

### 9.5 显式不测

- Streamlit UI 渲染(延续项目惯例)
- Plotly 图表内容(只验证创建不报错)
- Form 输入校验(人工冒烟)

---

## 10. 边界情形与失败模式

| 情形 | 行为 |
|---|---|
| 策略缺 PARAMS,跑 WFA | 启动前 `WfaError` |
| `PARAMS` 用 `range()` 等非 literal | 启动前 `WfaError` |
| `param_overrides` 含未知 key | 启动前 `WfaError` |
| 组合数超 `max_combos_per_window` | 启动前 `WfaError` |
| 数据 span 不够一个完整窗口 | 返回 `success=False`(不抛) |
| 单个 combo 在 IS 中跑失败 | grid_evaluations 标记 failed, score=-inf, 不杀整个 WFA |
| 单个窗口 IS 全失败,有前序 winner | 沿用前序 winner,加 warning |
| 第 0 窗口 IS 全失败 | `WfaError`("无法启动") |
| 单个窗口 OOS 跑失败 | warning + 该窗口 oos_pv 为空,stitcher 跳过 |
| 策略读 `ctx.params` 中不存在的 key | KeyError 进 strategy `_backtest_warnings`,该 bar 跳过(走现有路径) |
| WFA 完成但 history 保存失败 | `st.warning`,不影响显示结果 |

---

## 11. 已知近似与限制

- **跨窗口持仓不延续**:每窗口 OOS 从 `initial_capital` 起跑,通过 stitching 数学保持权益连续。这意味着窗口边界处的"实际持仓"可能从 100% 股票直接切到 100% 现金而不产生交易成本。可接受的 v1 近似;v2 若需"真实持仓延续",需引入 cross-window position carry。
- **Step ≥ OOS 强制**:不支持 OOS 窗口重叠的"高分辨率"WFA(常用于参数稳定性细查)。v2 可考虑放开,但需要解决 stitching 的双计 bar 问题。
- **离散参数空间**:`PARAMS` 只支持 list literal。连续空间 (`IntRange(20, 100, 20)` 等) 推到 v2,届时需要白名单 helper 类型 + sandbox 注入。
- **同步执行**:WFA 跑的时候 UI 不能交互。可接受,典型 30s–2min 范围内。
- **PerformanceMetrics 的边界**:`objective_score` 依赖 `calculate_all` 输出的 metric 名(`"Sharpe Ratio"` / `"Calmar Ratio"` / `"CAGR (%)"` / `"Sortino Ratio"`)。如果未来 metric 重命名,`objective_score` 需要同步更新。

---

## 12. 与 #3 (run history) 的兼容性

- `schema_version` **不升级**(仍为 1),完全靠加字段扩展
- 老的 `*.summary.json` / `*.detail.json` 文件**不需要 migration**,继续可读
- 现有 `compute_inputs_diff` 不需要改
- 现有 `_prune` 不需要改
- WFA 详情页是新模块 `render_wfa_detail`,与现有 `render_detail` 通过 `mode` 字段分流

---

## 13. 后续工作 (v2 候选)

明确不在 v1 范围,但 spec 已经为这些预留了空间:

- **`search_algo: "random"` 或 `"bayesian"`**:`WfaConfig.search_algo` 字段已经预留
- **连续参数空间** (`IntRange` / `FloatChoices`):需要白名单 helper + sandbox 注入
- **WFA 父子记录** (`parent_run_id`, `schema_version=2`):允许每个窗口作为独立可对比的 run
- **跨窗口持仓延续**:替换 stitching 为真实 carry-forward
- **OOS 重叠窗口** (`step < oos_years`):用于参数稳定性细查
- **策略 compile 缓存**:`_compile_cache` dict,把当前 ~30% 的开销砍掉
- **Multiprocessing**:每个 combo 独立进程,~N 倍加速
- **Drill-down**:WFA detail 页"把这个窗口当成普通 run 重新跑"按钮

---

## 14. 实施分解(预览)

具体 task 由 `superpowers:writing-plans` 生成。预期粒度:

1. `param_grid.py`(extract + expand,纯函数,易 TDD)
2. `objective_score`(纯函数)
3. `WfaConfig` + 校验
4. `build_windows`(纯函数,大量边界测试)
5. `_stitch`(纯函数,关键 invariant 测试)
6. `engine.run_dynamic` 加 `prices` kwarg + 测试
7. `StrategyContext.params` + `execute(params=)` + 测试
8. `WalkForwardEngine.run` 端到端 + 集成测试
9. `RunHistoryStore.save_wfa` + `load_wfa_detail` + 测试
10. `run_compare.py: render_history_detail` 按 mode 分流(小改动)
11. `wfa_form.py` 表单 + 人工验证
12. `wfa_render.py` 详情页 + 人工验证
13. `backtest_page.py` 第 5 个 tab 接线
14. CHANGELOG 更新

每 task ≤ 半天,严格 TDD(RED commit + GREEN commit)。
