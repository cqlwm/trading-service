from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SymbolInfo:
    """币种信息。"""

    symbol: str
    price: float
    volume_24h: float
    market_cap: float
    price_change_pct_24h: float


class ISymbolPicker(ABC):
    """币种选择器接口。"""

    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:
        """选择符合条件的币种。"""


class StaticListSymbolPicker(ISymbolPicker):
    """静态列表币种选择器。"""

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        return [
            SymbolInfo(
                symbol=s,
                price=0.0,
                volume_24h=0.0,
                market_cap=0.0,
                price_change_pct_24h=0.0,
            )
            for s in self.symbols
        ]
