from __future__ import annotations

import re


class Symbol:
    """交易对工具类。

    由 base_asset 和 quote_asset 组成，对不同应用场景暴露不同的拼接方法：
    - binance(): 返回币安原生格式（无分隔符，如 "BTCUSDT"），DB 存储与币安 API 使用
    - ccxt(): 返回 ccxt 格式（斜杠分隔，如 "BTC/USDT"），ccxt 库交互使用
    """

    _BASE_QUOTE_RE = re.compile(r"^([A-Z0-9]+)[_/-]([A-Z0-9]+)$")

    def __init__(self, base: str, quote: str = "USDT") -> None:
        self.base = base.upper()
        self.quote = quote.upper()

    @classmethod
    def parse(cls, s: str) -> Symbol:
        """解析交易对字符串，支持 binance/ccxt/横杠/下划线等多种格式。"""
        match = cls._BASE_QUOTE_RE.match(s.upper())
        if match:
            return cls(match.group(1), match.group(2))
        # 尝试常见的无分隔符交易对后缀
        if s.endswith("USDT"):
            return cls(s[:-4], "USDT")
        if s.endswith("BTC"):
            return cls(s[:-3], "BTC")
        if s.endswith("ETH"):
            return cls(s[:-3], "ETH")
        raise ValueError(f"Cannot parse symbol: {s}")

    def binance(self) -> str:
        """返回币安原生格式（无分隔符），用于币安 API 与 DB 存储。"""
        return f"{self.base}{self.quote}"

    def ccxt(self) -> str:
        """返回 ccxt 兼容格式（斜杠分隔），用于 ccxt 库交互。"""
        return f"{self.base}/{self.quote}"

    def __str__(self) -> str:
        """默认返回币安原生格式（与 DB 存储格式一致）。"""
        return self.binance()

    def __repr__(self) -> str:
        return f"Symbol(base={self.base!r}, quote={self.quote!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.base == other.base and self.quote == other.quote

    def __hash__(self) -> int:
        return hash((self.base, self.quote))
