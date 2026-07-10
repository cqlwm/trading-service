from __future__ import annotations
from typing import Any

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker


@dataclass
class StrategyAction:
    """策略执行动作记录，用于 API 响应反馈。"""

    type: str  # "open" | "add" | "close" | "skip"
    symbol: str
    detail: str = ""


@dataclass
class StrategyConfig:
    """策略配置基类。"""


class Strategy(ABC):
    """策略基类。"""

    def __init__(
        self,
        exchange: MockExchange,
        config: StrategyConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        self.exchange = exchange
        self.config = config
        self.symbol_picker = symbol_picker

    @abstractmethod
    async def execute(self) -> list[StrategyAction]:
        """执行策略，返回执行的动作列表。"""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
