"""
市场工具模块。

封装"后缀 ↔ 市场"映射、代码归一化、格式校验三类纯函数，
供投资组合管理 UI 层使用，不依赖数据层/回测层。

yfinance 原生支持以下后缀：
- 美股（NYSE/NASDAQ）：无后缀
- 新加坡（SGX）：`.SI`
- 香港（HKEX）：`.HK`
- 上海证券交易所（SSE）：`.SS`
- 深圳证券交易所（SZSE）：`.SZ`
"""

from typing import Tuple


# 市场代码 -> yfinance 后缀
MARKET_SUFFIXES: dict = {
    'US': '',       # 美股
    'SG': '.SI',    # 新加坡
    'HK': '.HK',    # 香港
    'SH': '.SS',    # 上交所
    'SZ': '.SZ',    # 深交所
}

# 市场代码 -> 下拉框中文标签
MARKET_LABELS: dict = {
    'AUTO': '🌐 自动识别',
    'US': '🇺🇸 美股',
    'SG': '🇸🇬 新加坡 (.SI)',
    'HK': '🇭🇰 香港 (.HK)',
    'SH': '🇨🇳 沪市 (.SS)',
    'SZ': '🇨🇳 深市 (.SZ)',
}

# 下拉框可选项（有序）
MARKET_OPTIONS = ['AUTO', 'US', 'SG', 'HK', 'SH', 'SZ']

# 已知后缀集合（大写形式）
KNOWN_SUFFIXES = {'.SI', '.HK', '.SS', '.SZ'}

# 全角字符 -> 半角字符 映射（常见中文输入法可能产生）
FULLWIDTH_MAP = str.maketrans({
    '．': '.',
    '，': ',',
    '　': ' ',
    '．'.upper(): '.',
})


# ---------- 模板组合 ----------
# 港股核心：腾讯、汇丰、建行、友邦
TEMPLATE_HK_CORE_TICKERS = "0700.HK, 0005.HK, 0939.HK, 1299.HK"
TEMPLATE_HK_CORE_WEIGHTS = "30, 25, 25, 20"

# 沪深 300 代表：贵州茅台、五粮液、招商银行、平安银行
TEMPLATE_CN_CORE_TICKERS = "600519.SS, 000858.SZ, 600036.SS, 000001.SZ"
TEMPLATE_CN_CORE_WEIGHTS = "30, 25, 25, 20"


def _preclean(raw: str) -> str:
    """对用户输入做基础清洗：去空格、全角转半角、转大写。"""
    if not raw:
        return ''
    # 全角转半角
    cleaned = raw.translate(FULLWIDTH_MAP)
    return cleaned.strip().upper()


def detect_market(ticker: str) -> str:
    """
    根据后缀识别市场，返回市场代码（US/SG/HK/SH/SZ）。
    无已知后缀时返回 'US'（默认美股）。
    """
    t = _preclean(ticker)
    if t.endswith('.SI'):
        return 'SG'
    if t.endswith('.HK'):
        return 'HK'
    if t.endswith('.SS'):
        return 'SH'
    if t.endswith('.SZ'):
        return 'SZ'
    return 'US'


def _has_known_suffix(ticker: str) -> bool:
    """判断 ticker 是否已带已知后缀。"""
    t = _preclean(ticker)
    return any(t.endswith(suf) for suf in KNOWN_SUFFIXES)


def normalize_ticker(raw: str, selected_market: str = 'AUTO') -> Tuple[str, str]:
    """
    归一化用户输入为最终 ticker。

    规则：
    1. 输入为空 -> 返回错误。
    2. 输入已带已知后缀（.HK/.SS/.SZ/.SI，大小写不敏感）-> 忽略下拉，直接转大写使用。
    3. 输入不带后缀：
       - selected_market = 'US'   -> 不补后缀。
       - selected_market 在 SG/HK/SH/SZ -> 补对应后缀。
       - selected_market = 'AUTO' -> 若为纯字母按美股处理；若为纯数字则要求显式选择市场。

    Args:
        raw: 用户输入
        selected_market: 用户在下拉框选择的市场代码（AUTO/US/SG/HK/SH/SZ）

    Returns:
        (normalized_ticker, error_msg)。error_msg 为空字符串表示成功。
    """
    if not raw or not raw.strip():
        return '', '请输入有效的股票代码'

    cleaned = _preclean(raw)

    # 情况 1: 已带已知后缀，直接使用（忽略下拉选项）
    if _has_known_suffix(cleaned):
        return cleaned, ''

    # 情况 2: 不带后缀，根据 selected_market 处理
    market = (selected_market or 'AUTO').upper()

    if market == 'US':
        return cleaned, ''

    if market in ('SG', 'HK', 'SH', 'SZ'):
        suffix = MARKET_SUFFIXES[market]
        return f"{cleaned}{suffix}", ''

    # market == 'AUTO'
    if cleaned.isalpha():
        # 纯字母按美股处理
        return cleaned, ''

    if cleaned.isdigit():
        # 纯数字但未选择市场，存在二义性（A 股 6 位数字在 .SS 和 .SZ 都可能），
        # 为避免误判（如 600519 可能用户想要 .SS 但意外补成 .SZ），要求显式选择
        return '', (
            f"❌ 代码 `{cleaned}` 是纯数字，请在\"市场\"下拉中显式选择"
            f"（港股 / 沪市 / 深市），或输入带后缀的完整代码（如 `{cleaned}.SS`）"
        )

    # 其他情况（字母数字混合且无后缀）按美股处理
    return cleaned, ''


def validate_ticker_format(ticker: str) -> Tuple[bool, str]:
    """
    按市场后缀做本地格式校验（不走网络）。

    规则：
    - `.HK`：代码部分为 4-5 位纯数字。
    - `.SS` / `.SZ`：代码部分为 6 位纯数字。
    - `.SI`、美股：不做严格校验，放行（保持现状）。

    Args:
        ticker: 已归一化的 ticker（假定大写）

    Returns:
        (is_valid, error_msg)
    """
    if not ticker:
        return False, '请输入有效的股票代码'

    t = ticker.strip().upper()

    if t.endswith('.HK'):
        code = t[:-3]
        if not (code.isdigit() and 4 <= len(code) <= 5):
            return False, (
                f"❌ 港股代码应为 4-5 位数字 + `.HK`（如 `0700.HK`），"
                f"你输入的是 `{ticker}`"
            )
        return True, ''

    if t.endswith('.SS') or t.endswith('.SZ'):
        code = t[:-3]
        suffix = t[-3:]
        if not (code.isdigit() and len(code) == 6):
            market_name = '沪市' if suffix == '.SS' else '深市'
            return False, (
                f"❌ A 股{market_name}代码应为 6 位数字 + `{suffix}`"
                f"（如 `600519.SS`），你输入的是 `{ticker}`"
            )
        return True, ''

    # 其他（.SI、美股）保持现状，放行
    return True, ''
