---
name: support-cn-hk-markets
overview: 在投资组合中扩展对中国大陆 A 股（.SS/.SZ）和香港股票（.HK）的支持，包括 UI 输入增强（市场下拉 + 后缀自动补全）、格式校验、模板组合和文档更新。
todos:
  - id: create-market-utils
    content: 创建 `ui/utils/market_utils.py`，实现市场常量、detect_market、normalize_ticker、validate_ticker_format 及港股/沪深300模板常量
    status: completed
  - id: integrate-validation
    content: 改造 `portfolio_page.py` 的 validate_ticker 与 validate_multiple_tickers，前置调用 normalize_ticker 与 validate_ticker_format，格式错误不走网络请求
    status: completed
    dependencies:
      - create-market-utils
  - id: update-add-ticker-ui
    content: 在"现有组合-添加标的"区块新增市场下拉框（默认自动识别），打通验证与添加流程，支持带/不带后缀两种输入
    status: completed
    dependencies:
      - integrate-validation
  - id: update-create-portfolio-ui
    content: 改造"新建组合"区块：新增港股核心、沪深300代表两个模板按钮；tickers_input 逗号解析时对每个 ticker 调用 normalize_ticker 并提示格式错误
    status: completed
    dependencies:
      - integrate-validation
  - id: update-examples-and-readme
    content: 更新 `data/portfolios.json.example` 增加多市场示例组合，并在 `README.md` 的"支持市场"章节补充港股与 A 股说明
    status: completed
    dependencies:
      - create-market-utils
---

## 产品概述

在 quant_platform 投资组合管理中扩展标的支持范围，新增中国大陆 A 股（沪市 `.SS` / 深市 `.SZ`）与香港股票（`.HK`）。保持与现有美股、新加坡股一致的使用体验，用户可在同一组合中自由混合全球多市场标的。

## 核心功能

- **多市场标的支持**：投资组合可纳入美股、新加坡（.SI）、香港（.HK）、上交所（.SS）、深交所（.SZ）五类标的。
- **灵活输入方式**：
- 用户输入带后缀的完整代码（如 `0700.HK`、`600519.SS`）时直接使用。
- 输入纯数字/字母代码时，通过"市场"下拉选择自动补全对应后缀。
- 新建组合场景的逗号分隔输入同样遵循该规则，逐个标的处理。
- **前置格式校验**：在调用 yfinance 验证前，先按市场规则校验代码格式，提前拦截明显错误：
- `.HK`：代码 4-5 位纯数字。
- `.SS` / `.SZ`：代码 6 位纯数字。
- `.SI`、美股：保持现状。
- **模板组合扩展**：在"新建组合"模板区新增两个按钮：
- 港股核心（腾讯、汇丰、建行、友邦等代表标的）。
- 沪深 300 代表（茅台、五粮液、招商、平安银行等代表标的）。
- **示例与文档同步**：`portfolios.json.example` 增加多市场示例，`README.md` 的"支持市场"章节补充 A 股与港股说明。

## 视觉效果

- "添加标的"区块在原"代码输入 + 权重输入"布局基础上新增一个"市场"下拉框（默认"自动识别"），整体保持现有 Streamlit 行内列布局风格。
- 模板按钮新增两个与现有模板同样式的按钮，一键填充对应 tickers。
- 校验失败时在原位展示中文报错（如"❌ A 股代码应为 6 位数字，你输入的是 `xxx`"），与现有错误提示样式一致。

## 技术栈

- 沿用项目现有技术栈：Python + Streamlit + pandas + yfinance。
- 不新增第三方依赖，不改动数据层 `data/fetcher.py`（yfinance 原生支持 `.HK`/`.SS`/`.SZ`，现有 `_normalize_prices` 与缓存机制天然兼容）。

## 实现思路

### 高层策略

通过**前置归一化 + 前置格式校验**两步，将多市场支持以最小改动融入现有流程：

1. 新增独立的 `market_utils` 模块，封装"后缀 ↔ 市场"映射、代码归一化、格式校验三类纯函数；不触碰数据层与回测层，确保 blast radius 最小。
2. `portfolio_page.py` 在原有 `validate_ticker` 前调用 `market_utils.normalize_ticker(raw, selected_market)` 得到最终 ticker，再走现有 yfinance 验证逻辑，保持与 `.SI` 完全一致的处理路径。
3. UI 侧在"添加标的"与"新建组合"两个入口旁增加市场下拉框；模板按钮区新增 2 个模板。

### 关键技术决策

- **纯函数工具模块**：`ui/utils/market_utils.py`（若 `ui/utils` 目录不存在则新建）提供无副作用的归一化与校验，便于单元测试与多处复用（新建组合 + 现有组合添加标的两处都会用到）。
- **归一化规则（单一数据源真相）**：
- 若输入已含已知后缀（`.HK`/`.SS`/`.SZ`/`.SI`，大小写不敏感）→ 统一转大写后使用，忽略下拉选项。
- 若不含后缀：按下拉选择补后缀；"美股"与"自动识别 + 纯字母"不补后缀；"自动识别 + 纯数字 6 位"保守地不自动补（避免 `.SS`/`.SZ` 二义性），提示用户显式选择市场。
- **校验分层**：
- Layer 1：`market_utils.validate_ticker_format(ticker)` 按后缀做格式校验（纯本地、零网络）。
- Layer 2：现有 `validate_ticker`（实际 yfinance 拉数）仅在 Layer 1 通过后执行，节省无效网络请求。
- **兼容性**：所有现有仅含美股/SGX 的组合无需迁移，`portfolios.json` 数据结构不变。

### 性能与可靠性

- 新增校验为纯字符串操作，O(1)；不影响现有缓存命中率（缓存 key 使用全量 ticker 字符串哈希，天然按市场隔离）。
- 批量新建组合时，Layer 1 先整体过滤掉格式非法项，减少 `fetch_prices` 调用次数，避免无谓的网络开销。
- 不改变交易日历处理：yfinance 各市场返回各自交易日索引，回测引擎按 index 自然对齐（已验证现有 `.SI` 的处理路径）。

### 避免技术债

- 不修改数据层、回测层、策略层、通知层；仅在 UI 层做归一化与前置校验。
- 不引入新状态管理或配置文件；市场映射与模板列表以模块级常量形式集中维护，便于未来扩展（如东京 `.T`、伦敦 `.L`）。

## 实现注意事项

- **复用既有模式**：沿用 `portfolio_page.py` 中 `ticker.strip().upper()` 的归一化习惯；沿用现有"模板按钮 → `st.session_state['template_tickers']`"的数据通道，港股 / A 股模板只需追加按钮并写入同一 session key。
- **日志与错误提示**：保持与项目现有风格一致（中文 + emoji 前缀），不新增 logger；错误信息要具体到"期望格式 vs 实际输入"，避免含糊。
- **向后兼容**：已存在的组合（仅含美股 / `.SI`）行为完全不变；`portfolios.json` schema 保持不变。
- **UI 复用**：尽量复用现有 `st.columns` 布局与 `st.text_input` / `st.selectbox` 组件，避免引入新的视觉元素破坏整体风格。
- **大小写/全角处理**：输入先 `strip().upper()`；建议同时去除全角字符（用户可能粘贴中文输入法下的数字/点号），将常见全角 `．` 替换为 `.`，提高鲁棒性。

## 目录结构

```
quant_platform/
├── ui/
│   ├── utils/
│   │   ├── __init__.py              # [NEW] 包初始化（若 utils 目录不存在）。
│   │   └── market_utils.py          # [NEW] 市场工具模块。导出：
│   │                                #   - MARKET_SUFFIXES 常量：{'US': '', 'SG': '.SI', 'HK': '.HK', 'SH': '.SS', 'SZ': '.SZ'}
│   │                                #   - MARKET_LABELS 常量：市场中文名映射（用于下拉框显示）
│   │                                #   - detect_market(ticker) -> str：根据后缀识别市场
│   │                                #   - normalize_ticker(raw, selected_market='AUTO') -> str：归一化为最终 ticker（含全角处理、后缀补全）
│   │                                #   - validate_ticker_format(ticker) -> (bool, str)：按市场规则校验位数
│   │                                #   - TEMPLATE_PORTFOLIOS 常量：港股核心、沪深300代表两个模板的 tickers 字符串
│   └── pages/
│       └── portfolio_page.py        # [MODIFY] 投资组合页面。改动点：
│                                    #   1) 导入 market_utils；
│                                    #   2) validate_ticker：调用前先执行 normalize_ticker + validate_ticker_format；格式失败直接返回中文错误，不走网络；
│                                    #   3) validate_multiple_tickers：循环内使用同一归一化路径；
│                                    #   4) 现有组合的"添加标的"区块（~第168-218行）：在 new_ticker 输入框旁新增 market selectbox（默认"自动识别"），验证与添加逻辑统一走 normalize_ticker；
│                                    #   5) 新建组合区块（~第326-395行）：模板按钮区追加"港股核心"、"沪深300代表"两个按钮，点击写入 st.session_state['template_tickers']；tickers_input 解析时对每个逗号分隔项调用 normalize_ticker（无后缀 + 未选市场时报错提示）；
│                                    #   6) 可选：在 tickers 输入框下方加一行 caption 提示："支持 US / .SI / .HK / .SS / .SZ；无后缀时请选择市场"。
├── data/
│   └── portfolios.json.example      # [MODIFY] 新增一个跨市场示例组合，包含 .HK 与 .SS 标的，展示多市场用法。
└── README.md                        # [MODIFY] "支持市场"章节补充：
                                     #   - 🇭🇰 香港 (HKEX) 后缀 .HK
                                     #   - 🇨🇳 中国大陆 A 股 (SSE/SZSE) 后缀 .SS / .SZ
                                     #   并补充代码示例说明。
```

## 关键接口定义

仅列出 `market_utils` 对外暴露的核心签名（实现细节见 todolist 执行阶段）：

```python
# ui/utils/market_utils.py
MARKET_SUFFIXES: dict[str, str]  # 市场代码 -> 后缀
MARKET_LABELS: dict[str, str]    # 市场代码 -> 中文标签（含 'AUTO' 自动识别）

def detect_market(ticker: str) -> str: ...
def normalize_ticker(raw: str, selected_market: str = 'AUTO') -> tuple[str, str]:
    """返回 (normalized_ticker, error_msg)。error_msg 为空字符串表示成功。"""

def validate_ticker_format(ticker: str) -> tuple[bool, str]:
    """按后缀规则做格式校验：.HK 4-5 位数字；.SS/.SZ 6 位数字；其他放行。"""
```