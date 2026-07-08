from __future__ import annotations

import re


class Symbol:
    """交易对工具类。"""

    _BASE_QUOTE_RE = re.compile(r"^([A-Z0-9]+)[_/-]([A-Z0-9]+)$")

    def __init__(self, base: str, quote: str = "USDT") -> None:
        self.base = base.upper()
        self.quote = quote.upper()

    @classmethod
    def parse(cls, s: str) -> "Symbol":
        """解析交易对字符串。"""
        match = cls._BASE_QUOTE_RE.match(s.upper())
        if match:
            return cls(match.group(1), match.group(2))
        # 尝试常见的交易对
        if s.endswith("USDT"):
            return cls(s[:-4], "USDT")
        if s.endswith("BTC"):
            return cls(s[:-3], "BTC")
        if s.endswith("ETH"):
            return cls(s[:-3], "ETH")
        raise ValueError(f"Cannot parse symbol: {s}")

    def __str__(self) -> str:
        return f"{self.base}{self.quote}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.base == other.base and self.quote == other.quote


    def ccxt(self) -> str:
        """返回 ccxt 兼容的 symbol 格式。"""
        return str(self)
    def __hash__(self) -> int:
        return hash((self.base, self.quote))
