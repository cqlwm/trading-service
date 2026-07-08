from __future__ import annotations

import re


class Symbol:
    """交易对工具类。"""

    _BASE_QUOTE_RE = re.compile(r"^([A-Z0-9]+)[_-/]([A-Z0-9]+)$")

    def __init__(self, base: str, quote: str = "USDT") -> None:
        self.base = base.upper()
        self.quote = quote.upper()

    @classmethod
    def from_str(cls, s: str) -> Symbol:
        """从字符串解析交易对，支持 BTC/USDT、BTC_USDT、BTC-USDT 格式。"""
        s = s.upper().strip()
        match = cls._BASE_QUOTE_RE.match(s)
        if match:
            return cls(match.group(1), match.group(2))
        return cls(s)

    def ccxt(self) -> str:
        """转换为 ccxt 格式（BTC/USDT）。"""
        return f"{self.base}/{self.quote}"

    def binance(self) -> str:
        """转换为 Binance 格式（BTCUSDT）。"""
        return f"{self.base}{self.quote}"

    def __str__(self) -> str:
        return self.ccxt()

    def __repr__(self) -> str:
        return f"Symbol({self.base!r}, {self.quote!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return NotImplemented
        return self.base == other.base and self.quote == other.quote

    def __hash__(self) -> int:
        return hash((self.base, self.quote))
