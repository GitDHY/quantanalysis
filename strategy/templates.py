"""
Built-in strategy templates for user reference.
"""

# Simple Moving Average Strategy
MA_CROSSOVER_TEMPLATE = '''"""
均线交叉策略 (Moving Average Crossover)
当短期均线上穿长期均线时增加仓位，下穿时减少仓位。
"""

def strategy():
    # 获取当前权重
    weights = ctx.get_current_weights()
    
    # 策略参数
    short_period = 20   # 短期均线周期
    long_period = 50    # 长期均线周期
    
    # 遍历所有标的
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        
        # 计算均线
        short_ma = ctx.ma(ticker, short_period)
        long_ma = ctx.ma(ticker, long_period)
        
        if len(short_ma) < 2 or len(long_ma) < 2:
            continue
        
        # 金叉: 增加仓位
        if ctx.ma_cross_up(ticker, short_period, long_period):
            weights[ticker] = min(current_weight + 10, 50)
            ctx.log(f"🟢 {ticker} 金叉信号, 增加仓位")
        
        # 死叉: 减少仓位
        elif ctx.ma_cross_down(ticker, short_period, long_period):
            weights[ticker] = max(current_weight - 10, 0)
            ctx.log(f"🔴 {ticker} 死叉信号, 减少仓位")
    
    # 设置目标权重
    ctx.set_target_weights(weights)
'''

# Momentum Strategy
MOMENTUM_TEMPLATE = '''"""
动量策略 (Momentum Strategy)
根据过去一段时间的涨幅调整仓位，追涨杀跌。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    lookback = 20       # 动量计算周期
    threshold = 5       # 动量阈值 (%)
    
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        
        # 计算动量
        mom = ctx.momentum(ticker, lookback)
        if mom.empty:
            continue
        
        current_momentum = mom.iloc[-1]
        
        # 正向动量: 增加仓位
        if current_momentum > threshold:
            weights[ticker] = min(current_weight + 5, 40)
            ctx.log(f"📈 {ticker} 动量 {current_momentum:.1f}% > {threshold}%, 增仓")
        
        # 负向动量: 减少仓位
        elif current_momentum < -threshold:
            weights[ticker] = max(current_weight - 5, 0)
            ctx.log(f"📉 {ticker} 动量 {current_momentum:.1f}% < -{threshold}%, 减仓")
    
    ctx.set_target_weights(weights)
'''

# VIX-Based Strategy
VIX_STRATEGY_TEMPLATE = '''"""
VIX 波动率策略 (Volatility Strategy)
根据 VIX 指数调整风险资产仓位。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    vix_low = 15        # 低波动阈值
    vix_high = 25       # 高波动阈值
    vix_panic = 35      # 恐慌阈值
    
    # 获取当前 VIX
    current_vix = ctx.current_vix()
    ctx.log(f"📊 当前 VIX: {current_vix:.1f}")
    
    # 定义风险资产和避险资产
    risk_assets = ['IWY', 'LVHI', 'G3B.SI']  # 根据你的组合调整
    safe_assets = ['GSD.SI', 'MBH.SI']       # 黄金、债券等
    
    if current_vix < vix_low:
        # 低波动: 激进配置
        ctx.log("🚀 低波动环境，增加风险资产")
        for ticker in risk_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 1.2
        for ticker in safe_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 0.8
    
    elif current_vix > vix_panic:
        # 恐慌: 避险配置
        ctx.log("🛡️ 恐慌环境，大幅减少风险资产")
        for ticker in risk_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 0.5
        for ticker in safe_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 1.5
    
    elif current_vix > vix_high:
        # 高波动: 谨慎配置
        ctx.log("⚠️ 高波动环境，适度减少风险资产")
        for ticker in risk_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 0.85
    
    ctx.set_target_weights(weights)
'''

# RSI Mean Reversion Strategy
RSI_STRATEGY_TEMPLATE = '''"""
RSI 均值回归策略 (Mean Reversion)
RSI 超买/超卖时反向操作。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    rsi_period = 14
    oversold = 30       # 超卖阈值
    overbought = 70     # 超买阈值
    
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        
        # 计算 RSI
        rsi = ctx.rsi(ticker, rsi_period)
        if rsi.empty:
            continue
        
        current_rsi = rsi.iloc[-1]
        
        # 超卖: 买入信号
        if current_rsi < oversold:
            weights[ticker] = min(current_weight + 10, 50)
            ctx.log(f"🟢 {ticker} RSI={current_rsi:.0f} 超卖，增仓")
        
        # 超买: 卖出信号
        elif current_rsi > overbought:
            weights[ticker] = max(current_weight - 10, 5)
            ctx.log(f"🔴 {ticker} RSI={current_rsi:.0f} 超买，减仓")
    
    ctx.set_target_weights(weights)
'''

# Trend Following Strategy
TREND_FOLLOWING_TEMPLATE = '''"""
趋势跟踪策略 (Trend Following)
只持有处于上升趋势的资产（价格在均线上方）。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    ma_period = 200     # 长期均线
    trend_ma = 50       # 趋势确认均线
    
    total_weight = 100
    trending_assets = []
    
    # 识别趋势资产
    for ticker in ctx.tickers:
        if ctx.price_above_ma(ticker, ma_period):
            trending_assets.append(ticker)
    
    ctx.log(f"📊 趋势向上的资产: {trending_assets}")
    
    if not trending_assets:
        # 没有趋势资产，保守配置
        ctx.log("⚠️ 无趋势资产，保持现有配置")
        return
    
    # 平均分配权重给趋势资产
    weight_per_asset = total_weight / len(trending_assets)
    
    for ticker in ctx.tickers:
        if ticker in trending_assets:
            # 趋势资产: 分配权重
            old_weight = weights.get(ticker, 0)
            weights[ticker] = weight_per_asset
            if weights[ticker] > old_weight:
                ctx.log(f"🟢 {ticker} 趋势向上，增仓至 {weight_per_asset:.1f}%")
        else:
            # 非趋势资产: 清仓
            if weights.get(ticker, 0) > 0:
                ctx.log(f"🔴 {ticker} 趋势转弱，清仓")
            weights[ticker] = 0
    
    ctx.set_target_weights(weights)
'''

# Risk Parity Inspired Strategy
RISK_PARITY_TEMPLATE = '''"""
风险平价策略 (Simplified Risk Parity)
根据波动率反比调整仓位，低波动资产配置更多。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    vol_period = 20     # 波动率计算周期
    target_vol = 0.15   # 目标波动率 15%
    
    volatilities = {}
    
    # 计算各资产波动率
    for ticker in ctx.tickers:
        vol = ctx.volatility(ticker, vol_period, annualize=True)
        if not vol.empty and vol.iloc[-1] > 0:
            volatilities[ticker] = vol.iloc[-1]
    
    if not volatilities:
        ctx.log("⚠️ 无法计算波动率")
        return
    
    # 计算反波动率权重
    inv_vol = {t: 1/v for t, v in volatilities.items()}
    total_inv_vol = sum(inv_vol.values())
    
    # 归一化权重
    for ticker in ctx.tickers:
        if ticker in inv_vol:
            weights[ticker] = (inv_vol[ticker] / total_inv_vol) * 100
            ctx.log(f"📊 {ticker}: 波动率={volatilities[ticker]:.1%}, 权重={weights[ticker]:.1f}%")
        else:
            weights[ticker] = 0
    
    ctx.set_target_weights(weights)
'''

# Basic Rebalance Strategy
REBALANCE_TEMPLATE = '''"""
定期再平衡策略 (Periodic Rebalancing)
保持目标配置比例，超过阈值时触发再平衡。
注意：此模板会自动使用当前组合中的标的进行等权重分配。
你可以修改 target 字典来自定义目标配置。
"""

def strategy():
    # 获取当前权重作为基础
    current = ctx.get_current_weights()
    
    # 目标配置 - 你可以自定义每个标的的目标权重
    # 如果不在下面定义，会使用等权重分配
    custom_target = {
        # 例如:
        # 'IWY': 40,      # 美股成长 40%
        # 'LVHI': 15,     # 美股红利 15%
    }
    
    # 如果没有自定义目标，使用等权重分配
    if not custom_target:
        n_assets = len(ctx.tickers)
        if n_assets > 0:
            equal_weight = 100.0 / n_assets
            target = {ticker: equal_weight for ticker in ctx.tickers}
            ctx.log(f"📊 使用等权重分配: {equal_weight:.1f}% x {n_assets} 个标的")
        else:
            ctx.log("⚠️ 组合中没有标的")
            return
    else:
        target = custom_target
    
    # 再平衡阈值
    rebalance_threshold = 5  # 偏离超过 5% 触发
    
    needs_rebalance = False
    
    # 检查是否需要再平衡
    for ticker in ctx.tickers:
        target_weight = target.get(ticker, 0)
        current_weight = current.get(ticker, 0)
        deviation = abs(current_weight - target_weight)
        
        if deviation > rebalance_threshold:
            needs_rebalance = True
            ctx.log(f"⚖️ {ticker}: 当前 {current_weight:.1f}% vs 目标 {target_weight:.1f}%, 偏离 {deviation:.1f}%")
    
    if needs_rebalance:
        ctx.log("🔄 触发再平衡")
        ctx.set_target_weights(target)
    else:
        ctx.log("✅ 无需再平衡，配置在容忍范围内")
'''

# Dual Momentum Strategy
DUAL_MOMENTUM_TEMPLATE = '''"""
双动量策略 (Dual Momentum)
结合绝对动量（与无风险收益比较）和相对动量（资产间比较）。
Gary Antonacci 提出的经典策略。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    lookback = 252  # 12个月动量
    safe_asset = 'GSD.SI'  # 避险资产（如黄金或债券）
    
    risk_assets = [t for t in ctx.tickers if t != safe_asset]
    
    # 计算各资产动量
    momentums = {}
    for ticker in risk_assets:
        mom = ctx.momentum(ticker, lookback)
        if not mom.empty:
            momentums[ticker] = mom.iloc[-1]
    
    if not momentums:
        ctx.log("⚠️ 无法计算动量")
        return
    
    # 找出最强动量资产
    best_asset = max(momentums, key=momentums.get)
    best_momentum = momentums[best_asset]
    
    ctx.log(f"📊 最强动量: {best_asset} ({best_momentum:.1f}%)")
    
    # 绝对动量检查：最强资产动量必须为正
    if best_momentum > 0:
        # 相对动量选择：投资最强资产
        for ticker in ctx.tickers:
            weights[ticker] = 100 if ticker == best_asset else 0
        ctx.log(f"🚀 绝对动量为正，全仓 {best_asset}")
    else:
        # 负动量：转入避险资产
        for ticker in ctx.tickers:
            weights[ticker] = 100 if ticker == safe_asset else 0
        ctx.log(f"🛡️ 绝对动量为负，转入避险资产 {safe_asset}")
    
    ctx.set_target_weights(weights)
'''

# MACD Trend Strategy
MACD_STRATEGY_TEMPLATE = '''"""
MACD 趋势策略
基于 MACD 金叉死叉和柱状图变化调整仓位。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        
        # 获取 MACD 数据
        macd_data = ctx.macd(ticker)
        if macd_data.empty or len(macd_data) < 2:
            continue
        
        macd_line = macd_data['macd'].iloc[-1]
        signal_line = macd_data['signal'].iloc[-1]
        histogram = macd_data['histogram'].iloc[-1]
        prev_histogram = macd_data['histogram'].iloc[-2]
        
        # MACD 金叉 + 柱状图放大
        if macd_line > signal_line and histogram > prev_histogram:
            weights[ticker] = min(current_weight + 15, 50)
            ctx.log(f"🟢 {ticker} MACD金叉+柱状图扩张，增仓")
        
        # MACD 死叉 + 柱状图缩小
        elif macd_line < signal_line and histogram < prev_histogram:
            weights[ticker] = max(current_weight - 15, 0)
            ctx.log(f"🔴 {ticker} MACD死叉+柱状图收缩，减仓")
        
        # 零轴上方强势
        elif macd_line > 0 and signal_line > 0:
            ctx.log(f"📈 {ticker} MACD零轴上方，维持仓位")
    
    ctx.set_target_weights(weights)
'''

# Bollinger Breakout Strategy
BOLLINGER_BREAKOUT_TEMPLATE = '''"""
布林带突破策略 (Bollinger Breakout)
价格突破上轨做多，跌破下轨减仓，中轨作为趋势参考。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    bb_period = 20
    bb_std = 2.0
    
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        price = ctx.current_price(ticker)
        
        # 获取布林带
        bb = ctx.bollinger(ticker, bb_period, bb_std)
        if bb.empty:
            continue
        
        upper = bb['upper'].iloc[-1]
        middle = bb['middle'].iloc[-1]
        lower = bb['lower'].iloc[-1]
        
        # 计算 %B 指标 (价格在布林带中的位置)
        pct_b = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
        
        if price > upper:
            # 突破上轨：强势信号
            weights[ticker] = min(current_weight + 10, 40)
            ctx.log(f"🚀 {ticker} 突破布林上轨 ({price:.2f} > {upper:.2f})")
        
        elif price < lower:
            # 跌破下轨：可能超卖或继续下跌
            weights[ticker] = max(current_weight - 10, 5)
            ctx.log(f"⚠️ {ticker} 跌破布林下轨 ({price:.2f} < {lower:.2f})")
        
        elif price > middle:
            # 在中轨上方：偏多
            ctx.log(f"📊 {ticker} 布林中轨上方，%B={pct_b:.2f}")
        
        else:
            # 在中轨下方：偏空
            ctx.log(f"📉 {ticker} 布林中轨下方，%B={pct_b:.2f}")
    
    ctx.set_target_weights(weights)
'''

# Yield Curve / Macro Strategy
YIELD_CURVE_TEMPLATE = '''"""
收益率曲线策略 (宏观风险策略)
通过 VIX 和市场状态模拟宏观环境判断。
高 VIX + 趋势向下 = 类似利率倒挂的风险环境。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 获取 VIX 和市场状态
    current_vix = ctx.current_vix()
    vix_series = ctx.vix(20)
    
    # VIX 趋势判断
    vix_ma = vix_series.mean() if not vix_series.empty else 20
    vix_trending_up = current_vix > vix_ma
    
    # 风险等级评估
    risk_assets = ['IWY', 'LVHI']  # 根据组合调整
    safe_assets = ['GSD.SI', 'MBH.SI']
    
    if current_vix > 30 and vix_trending_up:
        # 类似衰退预警：大幅减少风险敞口
        ctx.log(f"🔴 VIX={current_vix:.1f} 且上升趋势，衰退预警模式")
        for ticker in risk_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 0.3
        for ticker in safe_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 1.5
    
    elif current_vix > 20:
        # 风险环境：谨慎配置
        ctx.log(f"⚠️ VIX={current_vix:.1f}，谨慎模式")
        for ticker in risk_assets:
            if ticker in weights:
                weights[ticker] = weights.get(ticker, 0) * 0.8
    
    else:
        # 正常/低风险环境
        ctx.log(f"✅ VIX={current_vix:.1f}，正常配置")
    
    ctx.set_target_weights(weights)
'''

# Tactical Asset Allocation Strategy
TACTICAL_ALLOCATION_TEMPLATE = '''"""
动态资产配置策略 (Tactical Asset Allocation)
综合趋势、动量、波动率多维度信号动态调整。
以当前组合配置为基础，根据多维度信号进行动态调整。
"""

def strategy():
    # 使用当前组合配置作为基础配置
    base_allocation = ctx.get_current_weights()
    
    # 如果当前组合为空，使用等权重
    if not base_allocation or sum(base_allocation.values()) == 0:
        n = len(ctx.tickers)
        base_allocation = {t: 100/n for t in ctx.tickers}
        ctx.log("📋 当前组合为空，使用等权重作为基础配置")
    else:
        ctx.log("📋 使用当前组合配置作为基础")
    
    weights = base_allocation.copy()
    
    # 获取市场环境
    vix = ctx.current_vix()
    
    # 信号评分系统
    for ticker in ctx.tickers:
        score = 0
        
        # 1. 趋势信号 (+/-1)
        if ctx.price_above_ma(ticker, 200):
            score = score + 1
            ctx.log(f"📈 {ticker}: 趋势向上 +1")
        else:
            score = score - 1
            ctx.log(f"📉 {ticker}: 趋势向下 -1")
        
        # 2. 动量信号 (+/-1)
        mom = ctx.momentum(ticker, 20)
        if not mom.empty:
            if mom.iloc[-1] > 0:
                score = score + 1
            else:
                score = score - 1
        
        # 3. RSI 信号 (+/-1)
        rsi = ctx.rsi(ticker)
        if not rsi.empty:
            current_rsi = rsi.iloc[-1]
            if 40 < current_rsi < 60:
                pass  # 中性
            elif current_rsi < 30:
                score = score + 1  # 超卖反弹机会
            elif current_rsi > 70:
                score = score - 1  # 超买风险
        
        # 根据评分调整权重
        base = weights.get(ticker, 0)
        adjustment = 1 + (score * 0.15)  # 每分±15%
        weights[ticker] = max(0, base * adjustment)
        
        ctx.log(f"📊 {ticker}: 基础={base:.1f}%, 评分={score}, 调整后={weights[ticker]:.1f}%")
    
    # VIX 整体调整
    if vix > 30:
        ctx.log(f"⚠️ VIX={vix:.1f}，整体降低风险敞口")
        weights = {k: v * 0.7 for k, v in weights.items()}
    
    ctx.set_target_weights(weights)
'''

# Seasonal Rotation Strategy
SEASONAL_ROTATION_TEMPLATE = '''"""
季节性轮动策略 (Seasonal Rotation)
基于"Sell in May"等季节性规律调整配置。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 获取当前月份
    month = ctx.current_date.month
    
    risk_assets = [t for t in ctx.tickers]  # 可自定义
    
    # 历史统计最佳月份: 11月-4月 (冬季)
    # 历史统计较弱月份: 5月-10月 (夏季)
    
    winter_months = [11, 12, 1, 2, 3, 4]
    summer_months = [5, 6, 7, 8, 9, 10]
    
    if month in winter_months:
        ctx.log(f"📅 {month}月: 冬季强势期，增加权益配置")
        for ticker in risk_assets:
            base = weights.get(ticker, 0)
            weights[ticker] = min(base * 1.2, 50)
    
    elif month in summer_months:
        ctx.log(f"📅 {month}月: 夏季弱势期，降低权益配置")
        for ticker in risk_assets:
            base = weights.get(ticker, 0)
            weights[ticker] = base * 0.8
    
    # 特别注意 9月和10月（历史统计最弱）
    if month in [9, 10]:
        ctx.log(f"⚠️ {month}月: 历史统计最弱月份，进一步降低")
        for ticker in risk_assets:
            weights[ticker] = weights.get(ticker, 0) * 0.9
    
    ctx.set_target_weights(weights)
'''

# Drawdown Control Strategy
DRAWDOWN_CONTROL_TEMPLATE = '''"""
最大回撤控制策略 (Drawdown Control)
当资产回撤超过阈值时自动减仓。
"""

def strategy():
    weights = ctx.get_current_weights()
    
    # 策略参数
    max_drawdown_threshold = 10  # 回撤超过10%触发
    severe_drawdown = 20         # 严重回撤
    
    for ticker in ctx.tickers:
        current_weight = weights.get(ticker, 0)
        
        # 获取回撤数据
        dd = ctx.drawdown(ticker)
        if dd.empty:
            continue
        
        current_dd = abs(dd['drawdown'].iloc[-1]) * 100  # 转为百分比
        
        if current_dd > severe_drawdown:
            # 严重回撤：大幅减仓
            weights[ticker] = max(current_weight * 0.3, 0)
            ctx.log(f"🔴 {ticker} 严重回撤 {current_dd:.1f}%，大幅减仓")
        
        elif current_dd > max_drawdown_threshold:
            # 中度回撤：适度减仓
            weights[ticker] = max(current_weight * 0.7, 0)
            ctx.log(f"⚠️ {ticker} 回撤 {current_dd:.1f}%，减仓")
        
        else:
            ctx.log(f"✅ {ticker} 回撤 {current_dd:.1f}%，在可控范围")
    
    ctx.set_target_weights(weights)
'''

# Multi-Factor Scoring Strategy
MULTI_FACTOR_TEMPLATE = '''"""
多因子评分策略 (Multi-Factor Scoring)
综合动量、波动率、趋势多个因子打分排序。
"""

def strategy():
    scores = {}
    
    for ticker in ctx.tickers:
        score = 0
        
        # 因子1: 动量 (20日)
        mom = ctx.momentum(ticker, 20)
        if not mom.empty:
            mom_score = mom.iloc[-1]
            score = score + mom_score * 2  # 权重2
        
        # 因子2: 趋势 (在200日均线上方)
        if ctx.price_above_ma(ticker, 200):
            score = score + 10
        
        # 因子3: 波动率 (低波动加分)
        vol = ctx.volatility(ticker, 20, annualize=True)
        if not vol.empty:
            vol_val = vol.iloc[-1]
            if vol_val < 0.15:
                score = score + 5  # 低波动
            elif vol_val > 0.30:
                score = score - 5  # 高波动
        
        # 因子4: RSI (避免极端)
        rsi = ctx.rsi(ticker)
        if not rsi.empty:
            rsi_val = rsi.iloc[-1]
            if 40 < rsi_val < 60:
                score = score + 3  # 健康区间
        
        scores[ticker] = score
        ctx.log(f"📊 {ticker} 综合评分: {score:.1f}")
    
    # 根据评分分配权重
    total_score = sum(max(s, 0) for s in scores.values())
    weights = {}
    
    if total_score > 0:
        for ticker, score in scores.items():
            if score > 0:
                weights[ticker] = (score / total_score) * 100
            else:
                weights[ticker] = 0
    else:
        # 全部负分，等权分配避险
        n = len(ctx.tickers)
        weights = {t: 100/n for t in ctx.tickers}
        ctx.log("⚠️ 所有资产评分为负，等权配置")
    
    ctx.set_target_weights(weights)
'''

# Strategy templates dictionary
STRATEGY_TEMPLATES = {
    "均线交叉策略": MA_CROSSOVER_TEMPLATE,
    "动量策略": MOMENTUM_TEMPLATE,
    "VIX 波动率策略": VIX_STRATEGY_TEMPLATE,
    "RSI 均值回归策略": RSI_STRATEGY_TEMPLATE,
    "趋势跟踪策略": TREND_FOLLOWING_TEMPLATE,
    "风险平价策略": RISK_PARITY_TEMPLATE,
    "定期再平衡策略": REBALANCE_TEMPLATE,
    "双动量策略": DUAL_MOMENTUM_TEMPLATE,
    "MACD 趋势策略": MACD_STRATEGY_TEMPLATE,
    "布林带突破策略": BOLLINGER_BREAKOUT_TEMPLATE,
    "收益率曲线策略": YIELD_CURVE_TEMPLATE,
    "动态资产配置策略": TACTICAL_ALLOCATION_TEMPLATE,
    "季节性轮动策略": SEASONAL_ROTATION_TEMPLATE,
    "最大回撤控制策略": DRAWDOWN_CONTROL_TEMPLATE,
    "多因子评分策略": MULTI_FACTOR_TEMPLATE,
}

# API Documentation for users
STRATEGY_API_DOCS = '''
# 策略 API 文档

## 上下文对象 `ctx`

### 数据获取

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `ctx.get_price(ticker, lookback)` | 获取价格序列 | pd.Series |
| `ctx.get_prices(tickers, lookback)` | 获取多个标的价格 | pd.DataFrame |
| `ctx.get_returns(ticker, lookback)` | 获取收益率序列 | pd.Series |
| `ctx.current_price(ticker)` | 获取当前价格 | float |
| `ctx.vix(lookback)` | 获取 VIX 序列 | pd.Series |
| `ctx.current_vix()` | 获取当前 VIX | float |

### 技术指标

| 方法 | 说明 | 参数 |
|------|------|------|
| `ctx.ma(ticker, period)` | 简单移动平均 | period: 周期 |
| `ctx.ema(ticker, period)` | 指数移动平均 | period: 周期 |
| `ctx.rsi(ticker, period)` | RSI 指标 | period: 默认 14 |
| `ctx.macd(ticker, fast, slow, signal)` | MACD | 默认 12, 26, 9 |
| `ctx.bollinger(ticker, period, std)` | 布林带 | 默认 20, 2.0 |
| `ctx.atr(ticker, period)` | 平均真实波幅 | period: 默认 14 |
| `ctx.volatility(ticker, period)` | 波动率 | 年化波动率 |
| `ctx.momentum(ticker, period)` | 动量 | 百分比变化 |
| `ctx.drawdown(ticker)` | 回撤分析 | 返回 DataFrame |

### 信号检测

| 方法 | 说明 |
|------|------|
| `ctx.price_above_ma(ticker, period)` | 价格是否在均线上方 |
| `ctx.price_below_ma(ticker, period)` | 价格是否在均线下方 |
| `ctx.ma_cross_up(ticker, short, long)` | 短均线是否上穿长均线 |
| `ctx.ma_cross_down(ticker, short, long)` | 短均线是否下穿长均线 |

### 仓位管理

| 方法 | 说明 |
|------|------|
| `ctx.get_current_weights()` | 获取当前权重 (dict) |
| `ctx.set_target_weights(weights)` | 设置目标权重 |
| `ctx.log(message)` | 记录信号/日志 |

### 属性

| 属性 | 说明 |
|------|------|
| `ctx.tickers` | 可用标的列表 |
| `ctx.current_date` | 当前日期 |

## 示例

```python
def strategy():
    weights = ctx.get_current_weights()
    
    # 获取 VIX
    vix = ctx.current_vix()
    
    # 检查均线
    if ctx.price_above_ma('IWY', 200):
        weights['IWY'] = 50
        ctx.log("IWY 在 200 日均线上方")
    
    # 设置目标权重
    ctx.set_target_weights(weights)
```
'''
